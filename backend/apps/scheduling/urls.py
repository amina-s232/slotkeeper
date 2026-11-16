from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AppointmentViewSet,
    AvailabilityRuleViewSet,
    OwnProviderView,
    ProviderViewSet,
    TimeOffViewSet,
)

router = SimpleRouter()
router.register("providers", ProviderViewSet, basename="provider")
router.register("me/availability-rules", AvailabilityRuleViewSet, basename="my-availability-rule")
router.register("me/time-off", TimeOffViewSet, basename="my-time-off")
router.register("appointments", AppointmentViewSet, basename="appointment")

urlpatterns = [path("me/provider/", OwnProviderView.as_view(), name="my-provider"), *router.urls]
