from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.accounts.permissions import IsProviderRole

from .models import AvailabilityRule, Provider, TimeOff
from .serializers import (
    AvailabilityRuleSerializer,
    ProviderSerializer,
    SlotQuerySerializer,
    SlotSerializer,
    TimeOffSerializer,
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
