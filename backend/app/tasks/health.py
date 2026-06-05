"""
tasks/health.py — Smoke-test Celery task for Phase 0 exit criteria verification
"""

from app.tasks.celery_app import celery_app


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"
