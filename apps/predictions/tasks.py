from celery import shared_task
from django.contrib.gis.geos import Point
from ml_engine.pipelines.predictor import CyclonePipeline
from ml_engine.utils.standing_data_loader import refresh_standing_data_cache
from apps.cyclones.models import StormEvent, SatelliteObservation
from .models import ForecastTrack, RainfallForecast


@shared_task
def run_live_pipeline(basin: str = "BOB"):
  pipeline = CyclonePipeline.get_instance()
  result = pipeline.run_full_inference(basin=basin)

  storm, _ = StormEvent.objects.get_or_create(
      name=f"LIVE-{basin.upper()}-STORM",
      defaults={"basin": basin.upper(), "is_active": True},
  )

  pt = Point(result["center_lon"], result["center_lat"], srid=4326)

  SatelliteObservation.objects.create(
      storm=storm,
      center_point=pt,
      estimated_msw=result["msw"],
      imd_category=result["imd_category"],
      basin_category=result["category"],
      satellite_source=result["satellite_source"],
  )

  track = ForecastTrack.objects.create(
      storm=storm,
      basin=result["basin"],
      current_point=pt,
      msw_knots=result["msw_3min"],
      msw_10min=result["msw_10min"],
      msw_1min=result["msw_1min"],
      primary_category=result["category"],
      imd_category=result["imd_category"],
      south_pacific_category=result["south_pacific_category"],
      satellite_source=result["satellite_source"],
      forecast_timeline=result["forecast_timeline"],
      central_pressure_hpa=result["central_pressure_hpa"],
      eye_confidence=result["eye_confidence"],
      eye_confidence_label=result["eye_confidence_label"],
  )

  for step in result["forecast_timeline"]:
    RainfallForecast.objects.create(
        storm=storm,
        forecast_track=track,
        forecast_hour=step["forecast_hour"],
        rainfall_grid=step["rainfall_grid"],
        max_rainfall_mm=step["max_rainfall_mm"],
        model_tier="parametric",
    )

  return result


@shared_task
def sync_standing_data(api_url: str | None = None):
  """
  Refresh the in-process standing data cache on all Celery workers.

  Scheduled by Celery Beat every 6 hours (configured in config/celery.py).
  Can also be triggered on-demand:
      from apps.predictions.tasks import sync_standing_data
      sync_standing_data.delay()

  Args:
      api_url: Optional MOSDAC / external API endpoint to pull fresh
               station metadata from. If None, reloads from the local
               cyclone_shelters.csv on disk.

  Returns:
      Summary dict: {"status": "ok"|"error", "rows_loaded": int, "source": str}
  """
  result = refresh_standing_data_cache(api_url=api_url)
  return result

