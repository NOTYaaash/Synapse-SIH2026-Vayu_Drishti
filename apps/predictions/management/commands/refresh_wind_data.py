"""
Management command: refresh_wind_data

Downloads the latest NOAA GFS wind GRIB2 for the Indian Ocean/Bay of Bengal
region, converts it to the JSON grid format expected by WindyParticleLayer,
and overwrites the single cached wind-data.json file (old GRIB2s are deleted).

Usage:
    python manage.py refresh_wind_data            # only downloads if cache is stale
    python manage.py refresh_wind_data --force    # force re-download regardless

Schedule this with cron (every 6 hours) or django-cron / celery beat:
    0 */6 * * * /path/to/.venv/bin/python /path/to/manage.py refresh_wind_data
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Fetch the latest NOAA GFS 10m wind data and update the cached wind-data.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Force re-download even if the cache is still current.",
        )

    def handle(self, *args, **options):
        from ml_engine.pipelines.fetch_wind_data import fetch_and_cache, is_cache_stale

        force = options["force"]

        if not force and not is_cache_stale():
            self.stdout.write(self.style.SUCCESS("Wind data cache is already up to date. Skipping."))
            return

        self.stdout.write("Fetching latest GFS wind data from NOAA NOMADS...")
        try:
            path = fetch_and_cache(force=force)
            self.stdout.write(self.style.SUCCESS(f"Wind data updated successfully: {path}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to update wind data: {e}"))
            raise
