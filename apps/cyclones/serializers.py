from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import StormEvent, SatelliteObservation, CycloneShelter


class SatelliteObservationSerializer(GeoFeatureModelSerializer):

  class Meta:
    model = SatelliteObservation
    geo_field = "center_point"
    fields = (
        "id",
        "center_point",
        "timestamp",
        "estimated_msw",
        "imd_category",
        "basin_category",
        "satellite_source",
    )


class StormEventSerializer(serializers.ModelSerializer):
  observations = SatelliteObservationSerializer(many=True, read_only=True)

  class Meta:
    model = StormEvent
    fields = ("id", "name", "basin", "started_at", "is_active", "observations")


class CycloneShelterSerializer(GeoFeatureModelSerializer):

  class Meta:
    model = CycloneShelter
    geo_field = "point"
    fields = (
        "id",
        "name",
        "state",
        "district",
        "point",
        "capacity",
        "shelter_type",
        "data_source",
    )