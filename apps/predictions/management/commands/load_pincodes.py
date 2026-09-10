import csv
import os
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from apps.predictions.models import PincodeLocation


class Command(BaseCommand):
  help = "Load India Post pincodes with lat/lon from CSV"

  def add_arguments(self, parser):
    parser.add_argument(
        "csv_path",
        help="Path to pincodes CSV file (columns: pincode,district,state,lat,lon)",
    )

  def handle(self, *args, **options):
    path = os.path.normpath(options["csv_path"])
    if not os.path.exists(path):
      self.stderr.write(f"File not found: {path}")
      return

    PincodeLocation.objects.all().delete()

    batch = []
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
      reader = csv.DictReader(f)
      for row in reader:
        try:
          lat = float(row["lat"])
          lon = float(row["lon"])
        except (KeyError, ValueError):
          continue
        batch.append(
            PincodeLocation(
                pincode=row["pincode"].strip(),
                district=row.get("district", "").strip(),
                state=row.get("state", "").strip(),
                point=Point(lon, lat, srid=4326),
            )
        )
        if len(batch) >= 5000:
          PincodeLocation.objects.bulk_create(batch)
          count += len(batch)
          batch = []

    if batch:
      PincodeLocation.objects.bulk_create(batch)
      count += len(batch)

    self.stdout.write(f"Loaded {count} pincode records.")
