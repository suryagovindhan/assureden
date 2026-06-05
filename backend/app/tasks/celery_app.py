"""
tasks/celery_app.py — Celery application instance
"""

from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "assureden",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.health",
        # Phase 6+: app.tasks.execution, app.tasks.locator_health, app.tasks.watchdog
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,    # fair dispatch — one task at a time per worker
)
