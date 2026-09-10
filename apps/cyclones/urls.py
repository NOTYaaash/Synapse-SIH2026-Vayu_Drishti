from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import SatelliteObservationViewSet, StormEventViewSet, CycloneShelterViewSet

router = DefaultRouter()
router.register(r"events", StormEventViewSet, basename="storm-event")
router.register(r"observations", SatelliteObservationViewSet, basename="observation")
router.register(r"shelters", CycloneShelterViewSet, basename="shelter")

urlpatterns = [
    path("", include(router.urls)),
]