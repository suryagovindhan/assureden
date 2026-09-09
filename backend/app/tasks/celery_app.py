"""
tasks/celery_app.py — Celery application instance

Phase 4 additions:
  - Beat schedule: lease watchdog, job scheduler, offline detector
  - TESTING mode: task_always_eager=True (no broker required in tests)
"""

from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "assureden",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.health",
        # Phase 4
        "app.tasks.watchdog",
        "app.tasks.auto_retry",
        "app.tasks.scheduler",
        "app.tasks.agent_offline_detector",
        # Phase 6+: app.tasks.webhooks, app.tasks.notifications
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

# ── Celery Beat schedule ──────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "reap-expired-leases": {
        "task": "app.tasks.watchdog.reap_expired_leases",
        "schedule": settings.WATCHDOG_INTERVAL_SECONDS,  # default 30s
    },
    "fire-scheduled-jobs": {
        "task": "app.tasks.scheduler.fire_scheduled_jobs",
        "schedule": 60.0,
    },
    "detect-offline-agents": {
        "task": "app.tasks.agent_offline_detector.detect_offline_agents",
        "schedule": 60.0,
    },
}

# ── Test mode: run tasks synchronously without a broker ───────────────────────
if settings.TESTING:
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,  # re-raise exceptions in tests
    )
