"""Opt-in cross-process worker test. Requires an isolated migrated test database."""
import os
import subprocess
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select


@pytest.mark.skipif(os.getenv("RUN_CELERY_TESTS") != "1", reason="Requires local Redis and an isolated database")
def test_real_beat_delivers_watchdog_and_offline_tasks(tmp_path):
    from app.tasks.celery_app import celery_app
    from app.db.session import SessionLocal
    from app.db.base import utcnow
    from app.models.foundation import Organization, Agent, AuditEvent
    from app.models.test_cases import TestCase as Case
    from app.models.executions import TestRun as Run, RunEvent
    from app.services.snapshot_builder import compute_snapshot_sha256
    queue = "acceptance-" + uuid.uuid4().hex
    with SessionLocal() as db:
        org = Organization(name=queue, slug=queue)
        db.add(org); db.flush()
        agent = Agent(org_id=org.id, name=queue, api_key_hash=uuid.uuid4().hex,
                      status="IDLE", last_heartbeat=utcnow() - timedelta(days=1))
        case = Case(org_id=org.id, name=queue)
        db.add_all([agent, case]); db.flush()
        run = Run(org_id=org.id, test_case_id=case.id, test_case_version=1,
                  status="DISPATCHED", agent_id=agent.id, lease_id=uuid.uuid4(),
                  lease_expires_at=utcnow() - timedelta(seconds=1), dispatch_attempt_count=1,
                  execution_snapshot={}, execution_snapshot_sha256=compute_snapshot_sha256({}))
        deadline_run = Run(org_id=org.id, test_case_id=case.id, test_case_version=1,
                           status="RUNNING", agent_id=agent.id, lease_id=uuid.uuid4(),
                           started_at=utcnow() - timedelta(seconds=20),
                           deadline_at=utcnow() - timedelta(seconds=1),
                           lease_expires_at=utcnow() + timedelta(minutes=5),
                           execution_snapshot={}, execution_snapshot_sha256=compute_snapshot_sha256({}))
        db.add_all([run, deadline_run]); db.commit()
        run_id, agent_id, deadline_id = run.id, agent.id, deadline_run.id
    env = {**os.environ, "TESTING": "false"}
    with (tmp_path / "worker.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "app.tasks.celery_app:celery_app", "worker",
             "--pool=solo", "--concurrency=1", "--without-gossip", "--without-mingle",
             "--without-heartbeat", "--loglevel=WARNING", "-Q", queue, "-n", queue],
            cwd=Path(__file__).resolve().parents[1], env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        beat = None
        try:
            def call(name):
                result = celery_app.send_task(name, queue=queue)
                try:
                    return result.get(timeout=40, disable_sync_subtasks=False)
                finally:
                    result.forget()
            assert call("health.ping") == "pong"
            # Exercise the production Beat entries at a shortened test interval,
            # routing exclusively to this test's worker queue.
            helper = tmp_path / "beat.py"
            helper.write_text(
                "import sys\n"
                + "sys.path.insert(0, " + repr(str(Path(__file__).resolve().parents[1])) + ")\n"
                + "from app.tasks.celery_app import celery_app\n"
                + "celery_app.conf.beat_schedule = {name: {**entry, 'schedule': 1.0, 'options': {'queue': "
                + repr(queue) + "}} for name, entry in celery_app.conf.beat_schedule.items()}\n"
                + "celery_app.start(['beat', '--max-interval=1', '--loglevel=WARNING', '--schedule', "
                + repr(str(tmp_path / "beat-state")) + "])\n", encoding="utf-8")
            beat = subprocess.Popen([sys.executable, str(helper)], env=env, stdout=log, stderr=log,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            until = time.monotonic() + 30
            while time.monotonic() < until:
                with SessionLocal() as db:
                    if (db.get(Run, run_id).status == "QUEUED"
                            and db.get(Agent, agent_id).status == "OFFLINE"
                            and db.get(Run, deadline_id).status == "TIMED_OUT"):
                        break
                assert beat.poll() is None, "Beat exited before delivering tasks"
                time.sleep(0.2)
            with SessionLocal() as db:
                assert db.get(Run, run_id).status == "QUEUED"
                assert db.get(Run, run_id).dispatch_attempt_count == 1
                assert db.get(Agent, agent_id).status == "OFFLINE"
                assert db.get(Run, deadline_id).status == "TIMED_OUT"
                assert len(db.scalars(select(AuditEvent).where(AuditEvent.entity_id == agent_id)).all()) == 1
                events = db.scalars(select(RunEvent).where(RunEvent.run_id == run_id)).all()
                assert {e.event for e in events} == {"LEASE_EXPIRED", "RUN_REQUEUED"}
                assert len({e.sequence for e in events}) == 2
        finally:
            for child in (beat, process):
                if child is None:
                    continue
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait(timeout=10)
            with celery_app.connection_for_write() as connection:
                celery_app.amqp.queues[queue](connection.default_channel).delete()
