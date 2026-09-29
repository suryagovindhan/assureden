"""
tasks/agent_offline_detector.py — Phase 4: Mark stale agents OFFLINE.

Runs every 60 s via Celery beat.
Agents that have not sent a heartbeat within AGENT_OFFLINE_THRESHOLD_SECONDS
are transitioned to OFFLINE status and an AuditEvent is written.
"""

from celery import shared_task
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.base import utcnow
from app.db.repositories.foundation import AuditEventRepository
from app.models.foundation import Agent
from app.core.config import settings
from datetime import timedelta


@shared_task(name="app.tasks.agent_offline_detector.detect_offline_agents",
             bind=True, max_retries=0)
def detect_offline_agents(self) -> dict:
    """
    Scan agents that have not sent a heartbeat recently and mark them OFFLINE.
    Emits one AuditEvent per newly offline agent.
    """
    db: Session = SessionLocal()
    marked_offline: int = 0

    try:
        now = utcnow()
        threshold = now - timedelta(seconds=settings.AGENT_OFFLINE_THRESHOLD_SECONDS)

        # Find agents that are still considered online/idle/running but haven't heartbeated
        stale_agents = (
            db.query(Agent)
            .filter(
                Agent.status.in_(["ONLINE", "IDLE", "RUNNING"]),
                Agent.last_heartbeat < threshold,
                Agent.deleted_at.is_(None),
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        audit_repo = AuditEventRepository(db)
        for agent in stale_agents:
            agent.status = "OFFLINE"
            audit_repo.write(
                org_id=agent.org_id,
                entity_type="Agent",
                entity_id=agent.id,
                action="AGENT_OFFLINE",
                actor_id=None,  # system action
            )
            marked_offline += 1

        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"marked_offline": marked_offline}
