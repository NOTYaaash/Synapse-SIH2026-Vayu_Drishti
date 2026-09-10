from django.contrib.gis.db import models
from apps.cyclones.models import StormEvent


class ForecastTrack(models.Model):
  storm = models.ForeignKey(
      StormEvent,
      on_delete=models.CASCADE,
      related_name="forecast_tracks",
      null=True,
      blank=True,
  )
  basin = models.CharField(max_length=8, default="BOB")
  generated_at = models.DateTimeField(auto_now_add=True)
  current_point = models.PointField(srid=4326)
  msw_knots = models.FloatField()
  msw_10min = models.FloatField(default=0.0)
  msw_1min = models.FloatField(default=0.0)
  primary_category = models.CharField(max_length=64)
  imd_category = models.CharField(max_length=64, blank=True, default="")
  south_pacific_category = models.CharField(max_length=64, blank=True, default="")
  satellite_source = models.CharField(max_length=64, default="INSAT-3D/3DS")
  forecast_timeline = models.JSONField(default=list)
  is_active = models.BooleanField(default=True)
  central_pressure_hpa = models.FloatField(default=1013.0)
  eye_confidence = models.FloatField(default=0.0)
  eye_confidence_label = models.CharField(max_length=64, blank=True, default="")

  def __str__(self):
    return (
        f"Forecast [{self.basin}] {self.primary_category} "
        f"@ {self.central_pressure_hpa} hPa ({self.generated_at})"
    )



class PincodeLocation(models.Model):
  pincode = models.CharField(max_length=6, db_index=True)
  district = models.CharField(max_length=128, db_index=True)
  state = models.CharField(max_length=128)
  point = models.PointField(srid=4326)

  class Meta:
    indexes = [models.Index(fields=["district", "state"])]

  def __str__(self):
    return f"{self.pincode} — {self.district}, {self.state}"
