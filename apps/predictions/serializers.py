from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import ForecastTrack


class ForecastTrackSerializer(GeoFeatureModelSerializer):

  class Meta:
    model = ForecastTrack
    geo_field = "current_point"
    fields = (
        "id",
        "storm",
        "basin",
        "generated_at",
        "current_point",
        "msw_knots",
        "msw_10min",
        "msw_1min",
        "primary_category",
        "imd_category",
        "south_pacific_category",
        "satellite_source",
        "forecast_timeline",
        "is_active",
        "central_pressure_hpa",
        "eye_confidence",
        "eye_confidence_label",
    )


