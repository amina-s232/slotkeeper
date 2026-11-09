from rest_framework.routers import SimpleRouter

from .views import AvailabilityRuleViewSet, ProviderViewSet, TimeOffViewSet

router = SimpleRouter()
router.register("providers", ProviderViewSet, basename="provider")

urlpatterns = router.urls

router.register("me/availability-rules", AvailabilityRuleViewSet, basename="my-availability-rule")
router.register("me/time-off", TimeOffViewSet, basename="my-time-off")
