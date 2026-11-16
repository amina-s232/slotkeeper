from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

HealthSerializer = inline_serializer(
    "Health",
    {"status": serializers.CharField(), "database": serializers.CharField()},
)


@extend_schema(responses={200: HealthSerializer, 503: HealthSerializer}, auth=[])
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])  # a load balancer polls this constantly; it must never be rate limited
def health(request):
    """Liveness plus a database round trip. 200 when healthy, 503 when the database is down."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return Response({"status": "error", "database": "unavailable"}, status=503)
    return Response({"status": "ok", "database": "ok"}, status=status.HTTP_200_OK)
