import csv
import os
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from apps.cyclones.models import CycloneShelter


class Command(BaseCommand):
  help = "Load cyclone shelters from CSV into the database"

  def add_arguments(self, parser):
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "data", "cyclone_shelters.csv"),
    )

  def handle(self, *args, **options):
    path = os.path.normpath(options["csv_path"])
    if not os.path.exists(path):
      self.stderr.write(f"File not found: {path}")
      return

    CycloneShelter.objects.all().delete()

    shelters = []
    with open(path, newline="", encoding="utf-8") as f:
      reader = csv.DictReader(f)
      for row in reader:
        shelters.append(
            CycloneShelter(
                name=row["name"],
                state=row["state"],
                district=row["district"],
                point=Point(float(row["lon"]), float(row["lat"]), srid=4326),
                capacity=int(row["capacity"]),
                shelter_type=row["shelter_type"],
                data_source=row["data_source"],
            )
        )

    CycloneShelter.objects.bulk_create(shelters, batch_size=500)
    self.stdout.write(f"Loaded {len(shelters)} shelters.")
