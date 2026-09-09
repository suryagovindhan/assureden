"""Execute report queries on the supported database, rather than mocking SQL."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.models.foundation import Organization, Agent
from app.models.test_cases import TestCase as Case
from app.models.executions import TestRun as Run
from app.services.report_service import ReportService, _trunc_fn


@pytest.fixture
def report_data(db):
    org = Organization(name="Report integration", slug=f"report-{uuid4().hex}")
    db.add(org)
    db.flush()
    case = Case(org_id=org.id, name="Alternating result")
    agent = Agent(org_id=org.id, name="Report agent", api_key_hash=uuid4().hex)
    db.add_all([case, agent])
    db.flush()
    monday = datetime(2026, 9, 7, 10)
    for index, duration in enumerate([10, 10, 10, 90]):
        db.add(Run(
            id=uuid4(), org_id=org.id, test_case_id=case.id, test_case_version=1,
            agent_id=agent.id, triggered_at=monday + timedelta(seconds=index),
            started_at=monday + timedelta(minutes=1),
            completed_at=monday + timedelta(minutes=1, seconds=duration),
            status="COMPLETED" if index % 2 == 0 else "FAILED", priority="NORMAL",
        ))
    db.flush()
    return org.id, monday


@pytest.mark.parametrize("days,granularity", [(1, "hour"), (7, "day"), (60, "week")])
def test_all_reports_execute_on_postgres(db, report_data, days, granularity):
    org, monday = report_data
    since, until = monday - timedelta(hours=1), monday + timedelta(days=days) - timedelta(hours=1)
    runs = ReportService.runs_report(db, org, since, until)
    assert runs["granularity"] == granularity
    assert runs["data"]["total"] == 4
    if granularity == "week":
        assert runs["data"]["trend"][0]["date"].startswith("2026-09-07")
    queue = ReportService.queue_report(db, org, since, until)
    assert queue["data"][0]["avg_wait_seconds"] == 58.5
    duration = ReportService.duration_report(db, org, since, until)
    assert duration["data"][0]["avg_duration_seconds"] == 30
    assert duration["data"][0]["p95_duration_seconds"] == 90
    agents = ReportService.agents_report(db, org, since, until)
    assert agents["data"][0]["run_count"] == 4
    assert agents["data"][0]["avg_duration_seconds"] == 30
    assert agents["data"][0]["p95_duration_seconds"] == 90
    assert ReportService.flakiness_report(db, org, since, until)["data"][0]["flakiness_score"] == 1
    assert ReportService.pass_rate_report(db, org, since, until)["data"][0]["pass_rate"] == .5
    assert ReportService.schedules_report(db, org, since, until)["data"] == []
    assert ReportService.runs_report(db, uuid4(), since, until)["data"]["total"] == 0


def test_sqlite_week_keeps_monday_in_current_week():
    import sqlite3
    with sqlite3.connect(":memory:") as db:
        expression = _trunc_fn("week", "sqlite")("'2026-09-07'")
        assert db.execute(f"SELECT {expression}").fetchone()[0] == "2026-09-07"
