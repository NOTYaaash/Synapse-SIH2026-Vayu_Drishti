import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "poll-live-bob-stream-every-15m": {
        "task": "apps.predictions.tasks.run_live_pipeline",
        "schedule": crontab(minute="*/15"),
        "kwargs": {"basin": "BOB"},
    },
    "poll-live-as-stream-every-15m": {
        "task": "apps.predictions.tasks.run_live_pipeline",
        "schedule": crontab(minute="*/15"),
        "kwargs": {"basin": "AS"},
    },
    # Refresh standing data (shelter/station metadata) every 6 hours.
    # Ensures Celery workers pick up any new station records without restart.
    "sync-standing-data-every-6h": {
        "task": "apps.predictions.tasks.sync_standing_data",
        "schedule": crontab(minute=0, hour="*/6"),
        "kwargs": {"api_url": None},  # set to MOSDAC API URL when available
    },
}
