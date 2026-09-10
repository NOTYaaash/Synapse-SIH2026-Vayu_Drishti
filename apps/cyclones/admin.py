from django.contrib import admin
from .models import StormEvent, SatelliteObservation, CycloneShelter


@admin.register(StormEvent)
class StormEventAdmin(admin.ModelAdmin):
  list_display = ("name", "basin", "started_at", "is_active")
  list_filter = ("basin", "is_active")
  search_fields = ("name",)
  ordering = ("-started_at",)


@admin.register(SatelliteObservation)
class SatelliteObservationAdmin(admin.ModelAdmin):
  list_display = ("storm", "imd_category", "estimated_msw", "satellite_source", "timestamp")
  list_filter = ("imd_category", "satellite_source")
  search_fields = ("storm__name",)
  ordering = ("-timestamp",)


@admin.register(CycloneShelter)
class CycloneShelterAdmin(admin.ModelAdmin):
  list_display = ("name", "state", "district", "capacity", "shelter_type")
  list_filter = ("state", "shelter_type")
  search_fields = ("name", "district")
  ordering = ("state", "district")
