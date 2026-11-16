from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsClientRole, IsProviderOrAdmin, IsProviderRole

from .filters import AppointmentFilter
from .models import Appointment, AvailabilityRule, Provider, TimeOff
from .serializers import (
    AppointmentCreateSerializer,
    AppointmentSerializer,
    AvailabilityRuleSerializer,
    OwnProviderSerializer,
    ProviderSerializer,
    RescheduleSerializer,
    SlotQuerySerializer,
    SlotSerializer,
    TimeOffSerializer,
)
from .services.booking import ClientConflict, InvalidSlot, SlotUnavailable, book_appointment
from .services.lifecycle import (
    DeadlinePassed,
    InvalidTransition,
    cancel_appointment,
    complete_appointment,
    mark_no_show,
    reschedule_appointment,
)
from .services.slots import free_slots


class ProviderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Provider.objects.filter(is_active=True)
    serializer_class = ProviderSerializer
    filterset_fields = ["specialty"]

    @extend_schema(parameters=[SlotQuerySerializer], responses=SlotSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def slots(self, request, pk=None):
        """Bookable slots for one provider on one day."""
        provider = self.get_object()
        query = SlotQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        slots = free_slots(provider, query.validated_data["date"])
        data = [{"starts_at": s.start, "ends_at": s.end} for s in slots]
        return Response(SlotSerializer(data, many=True).data)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Conflict."
    default_code = "conflict"


# ---- a provider managing their own schedule --------------------------------------------


class OwnProviderMixin:
    """Everything here belongs to the logged-in provider's own profile, never anyone else's."""

    permission_classes = [IsProviderRole]

    def get_provider(self) -> Provider:
        try:
            return self.request.user.provider_profile
        except ObjectDoesNotExist:
            raise NotFound("No provider profile is linked to this account.") from None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["provider"] = self.get_provider()
        return context


class AvailabilityRuleViewSet(OwnProviderMixin, viewsets.ModelViewSet):
    serializer_class = AvailabilityRuleSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AvailabilityRule.objects.none()
        return self.get_provider().rules.all()

    def perform_create(self, serializer):
        serializer.save(provider=self.get_provider())


class TimeOffViewSet(
    OwnProviderMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = TimeOffSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TimeOff.objects.none()
        return self.get_provider().time_off.all()

    def perform_create(self, serializer):
        serializer.save(provider=self.get_provider())


class AppointmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AppointmentSerializer
    filterset_class = AppointmentFilter

    def get_permissions(self):
        if self.action == "create":
            return [IsClientRole()]
        if self.action in ("complete", "no_show"):
            return [IsProviderOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = Appointment.objects.select_related("provider", "client")
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        user = self.request.user
        # Scope in the query, so someone else's appointment is a 404 rather than a leaky 403.
        if user.role == Role.ADMIN:
            return queryset
        if user.role == Role.PROVIDER:
            return queryset.filter(provider__user=user)
        return queryset.filter(client=user)

    @extend_schema(
        request=AppointmentCreateSerializer,
        responses={
            201: AppointmentSerializer,
            400: OpenApiResponse(
                description="Invalid input, or a time the provider does not offer."
            ),
            409: OpenApiResponse(
                description="Slot already taken, or the client is already booked."
            ),
        },
    )
    def create(self, request, *args, **kwargs):
        """Book an appointment. Concurrent requests for one slot: exactly one gets 201."""
        serializer = AppointmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            appointment = book_appointment(
                client=request.user,
                provider=data["provider"],
                starts_at=data["starts_at"],
                notes=data["notes"],
            )
        except InvalidSlot as exc:
            raise ValidationError({"starts_at": [str(exc)]}) from exc
        except SlotUnavailable as exc:
            raise Conflict(str(exc), code="slot_unavailable") from exc
        except ClientConflict as exc:
            raise Conflict(str(exc), code="client_conflict") from exc
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)

    # ---- lifecycle actions -------------------------------------------------------------
    # get_object() uses the role-scoped queryset above, so someone else's appointment is a 404.

    def _respond(self, call):
        """Run a lifecycle service call and translate its domain errors into HTTP errors."""
        try:
            appointment = call()
        except InvalidSlot as exc:
            raise ValidationError({"starts_at": [str(exc)]}) from exc
        except SlotUnavailable as exc:
            raise Conflict(str(exc), code="slot_unavailable") from exc
        except ClientConflict as exc:
            raise Conflict(str(exc), code="client_conflict") from exc
        except InvalidTransition as exc:
            raise Conflict(str(exc), code="invalid_transition") from exc
        except DeadlinePassed as exc:
            raise Conflict(str(exc), code="deadline_passed") from exc
        return Response(AppointmentSerializer(appointment).data)

    @extend_schema(
        request=None,
        responses={
            200: AppointmentSerializer,
            409: OpenApiResponse(description="Not cancellable now."),
        },
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a booked appointment. Clients must do so before the provider's cut-off."""
        appointment = self.get_object()
        return self._respond(
            lambda: cancel_appointment(appointment_id=appointment.pk, actor=request.user)
        )

    @extend_schema(
        request=RescheduleSerializer,
        responses={
            200: AppointmentSerializer,
            400: OpenApiResponse(description="Not a slot the provider offers."),
            409: OpenApiResponse(description="Slot taken, client busy, or too late to change."),
        },
    )
    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        """Move the appointment to another slot of the same provider."""
        appointment = self.get_object()
        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._respond(
            lambda: reschedule_appointment(
                appointment_id=appointment.pk,
                actor=request.user,
                new_starts_at=serializer.validated_data["starts_at"],
            )
        )

    @extend_schema(
        request=None,
        responses={
            200: AppointmentSerializer,
            409: OpenApiResponse(description="Not in a completable state."),
        },
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Provider or admin: mark a started appointment as completed."""
        appointment = self.get_object()
        return self._respond(lambda: complete_appointment(appointment_id=appointment.pk))

    @extend_schema(
        request=None,
        responses={
            200: AppointmentSerializer,
            409: OpenApiResponse(description="Not in a state that allows this."),
        },
    )
    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        """Provider or admin: record that the client did not turn up."""
        appointment = self.get_object()
        return self._respond(lambda: mark_no_show(appointment_id=appointment.pk))


class OwnProviderView(OwnProviderMixin, generics.RetrieveUpdateAPIView):
    """The logged-in provider's own profile and booking rules."""

    serializer_class = OwnProviderSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.get_provider()
