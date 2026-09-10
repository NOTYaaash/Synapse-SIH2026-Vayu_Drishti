from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import ForecastTrackViewSet, AffectedAreaView, RainfallView, CycloneMapView, WindDataView

router = DefaultRouter()
router.register(r"tracks", ForecastTrackViewSet, basename="forecast-track")

urlpatterns = [
    path("", include(router.urls)),
    path("affected-area/", AffectedAreaView.as_view(), name="affected-area"),
    path("rainfall/", RainfallView.as_view(), name="district-rainfall"),
    path("map/", CycloneMapView.as_view(), name="cyclone-map"),
    path("wind-data/latest/", WindDataView.as_view(), name="wind-data-latest"),
]
