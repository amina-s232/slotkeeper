from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Provider
from .serializers import ProviderSerializer, SlotQuerySerializer, SlotSerializer
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
