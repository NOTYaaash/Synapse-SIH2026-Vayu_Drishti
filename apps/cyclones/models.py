from django.contrib.gis.db import models


class StormEvent(models.Model):
  BASIN_CHOICES = [
      ("BOB", "Bay of Bengal"),
      ("AS", "Arabian Sea"),
      ("SP", "South Pacific"),
      ("SI", "South Indian Ocean"),
  ]
  name = models.CharField(max_length=64, unique=True)
  basin = models.CharField(max_length=8, choices=BASIN_CHOICES, default="BOB")
  started_at = models.DateTimeField(auto_now_add=True)
  is_active = models.BooleanField(default=True)

  def __str__(self):
    return f"{self.name} ({self.basin})"


class SatelliteObservation(models.Model):
  storm = models.ForeignKey(
      StormEvent, on_delete=models.CASCADE, related_name="observations"
  )
  timestamp = models.DateTimeField(auto_now_add=True)
  center_point = models.PointField(srid=4326)
  estimated_msw = models.FloatField(help_text="Maximum Sustained Wind in Knots")
  imd_category = models.CharField(max_length=64)
  basin_category = models.CharField(max_length=64, blank=True, default="")
  satellite_source = models.CharField(max_length=64, default="INSAT-3D/3DS")

  def __str__(self):
    cat = self.basin_category or self.imd_category
    return f"{self.storm.name} - {cat} at {self.timestamp}"


class CycloneShelter(models.Model):
  name = models.CharField(max_length=256)
  state = models.CharField(max_length=128, db_index=True)
  district = models.CharField(max_length=128, db_index=True)
  point = models.PointField(srid=4326)
  capacity = models.IntegerField(default=0)
  shelter_type = models.CharField(max_length=64, default="MPCS")
  data_source = models.CharField(max_length=128, blank=True)

  class Meta:
    indexes = [models.Index(fields=["state", "district"])]

  def __str__(self):
    return f"{self.name} ({self.district}, {self.state}) — cap {self.capacity}"