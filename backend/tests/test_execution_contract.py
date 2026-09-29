"""Database/API regressions for the canonical agent contract."""
import uuid
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.base import utcnow
from app.db.repositories.foundation import AgentRepository
from app.models.foundation import Organization, User, Agent
from app.models.test_cases import TestCase as Case, TestStep as Step, StepAssertion
from app.models.object_repository import Application, Module, Page, PageObject
from app.models.executions import TestRun as Run, StepResult, RunEvent
from app.services.snapshot_builder import build_snapshot, build_agent_payload, compute_snapshot_sha256


@pytest.fixture
def execution_data(db):
    org = Organization(name="Execution contract", slug=uuid.uuid4().hex)
    db.add(org); db.flush()
    user = User(org_id=org.id, username="operator", email="operator@example.test", hashed_password="unused", role="ADMIN")
    db.add(user)
    key = uuid.uuid4().hex
    agent = Agent(org_id=org.id, name="HTTP agent", api_key_hash=AgentRepository.hash_api_key(key),
                  capabilities={"protocol_version": 2, "supported_actions": ["NAVIGATE", "TYPE", "CLICK", "SCREENSHOT"]})
    db.add(agent)
    application = Application(org_id=org.id, name="Example")
    db.add(application); db.flush()
    module = Module(org_id=org.id, application_id=application.id, name="Example")
    db.add(module); db.flush()
    page = Page(org_id=org.id, module_id=module.id, name="Example")
    db.add(page); db.flush()
    obj = PageObject(org_id=org.id, page_id=page.id, name="Name", object_type="INPUT", locators=[
        {"type": "ID", "value": "missing", "is_primary": True, "priority": 1},
        {"type": "CSS_SELECTOR", "value": "#name", "priority": 2},
        {"type": "ID", "value": "disabled", "priority": 1, "is_active": False},
    ])
    case = Case(org_id=org.id, name="Example")
    db.add_all([obj, case]); db.flush()
    step = Step(org_id=org.id, test_case_id=case.id, position=1, action="NAVIGATE", target_url="about:blank")
    db.add(step); db.flush()
    return SimpleNamespace(org=org, user=user, agent=agent, key=key, obj=obj, case=case, step=step,
        headers={"Authorization": "Bearer " + create_access_token(user.id, org.id, user.role)},
        agent_headers={"X-Agent-Api-Key": key})


def queue_and_poll(client, data):
    response = client.post("/api/runs", headers=data.headers, json={"test_case_id": str(data.case.id)})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    poll = client.post("/api/agents/poll", headers=data.agent_headers)
    assert poll.status_code == 200, poll.text
    request = poll.json()["execute_request"]
    assert request["run_id"] == run_id
    return request


def result_for(step, status="PASSED"):
    return {**{k: step[k] for k in ("execution_step_id", "step_id", "step_version", "position", "action")}, "status": status}


def test_callback_replay_and_fencing(client, db, execution_data):
    data = execution_data
    request = queue_and_poll(client, data)
    path = f"/api/runs/{request['run_id']}/agent-update"
    body = {"lease_id": request["lease_id"], "status": "COMPLETED",
            "step_results": [result_for(request["execution_plan"]["steps"][0])]}
    first = client.post(path, headers=data.agent_headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post(path, headers=data.agent_headers, json=body)
    assert second.status_code == 200, second.text
    assert second.json()["passed_steps"] == 1
    assert second.json()["completed_at"] == first.json()["completed_at"]
    run_id = uuid.UUID(request["run_id"])
    assert len(db.scalars(select(StepResult).where(StepResult.run_id == run_id)).all()) == 1
    events = db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence)).all()
    assert [x.sequence for x in events] == [1, 2, 3, 4]
    assert [x.event for x in events].count("RUN_COMPLETED") == 1
    body["status"] = "FAILED"
    assert client.post(path, headers=data.agent_headers, json=body).status_code == 409


@pytest.mark.parametrize("mutation,expected", [("unknown_step", 422), ("wrong_agent", 409), ("stale_lease", 409), ("missing_results", 422), ("aborted", 409), ("expired", 409)])
def test_rejected_updates(client, db, execution_data, mutation, expected):
    data = execution_data
    request = queue_and_poll(client, data)
    run_id = uuid.UUID(request["run_id"])
    body = {"lease_id": request["lease_id"], "status": "COMPLETED",
            "step_results": [result_for(request["execution_plan"]["steps"][0])]}
    headers = data.agent_headers
    if mutation == "unknown_step":
        body["step_results"][0]["execution_step_id"] = str(uuid.uuid4())
    elif mutation == "wrong_agent":
        key = uuid.uuid4().hex
        db.add(Agent(org_id=data.org.id, name="Other", api_key_hash=AgentRepository.hash_api_key(key)))
        db.flush()
        headers = {"X-Agent-Api-Key": key}
    elif mutation == "stale_lease":
        body["lease_id"] = str(uuid.uuid4())
    elif mutation == "missing_results":
        body["step_results"] = []
    elif mutation == "aborted":
        assert client.post(f"/api/runs/{run_id}/abort", headers=data.headers).status_code == 204
    elif mutation == "expired":
        db.get(Run, run_id).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.flush()
    response = client.post(f"/api/runs/{run_id}/agent-update", headers=headers, json=body)
    assert response.status_code == expected, response.text


def test_heartbeat_renews_lease_and_viewer_cannot_trigger(client, db, execution_data):
    data = execution_data
    request = queue_and_poll(client, data)
    run = db.get(Run, uuid.UUID(request["run_id"]))
    old = run.lease_expires_at = utcnow() + timedelta(seconds=1)
    db.flush()
    response = client.post(f"/api/runs/{run.id}/agent-update", headers=data.agent_headers,
                           json={"lease_id": request["lease_id"], "status": "RUNNING"})
    assert response.status_code == 200, response.text
    assert run.lease_expires_at > old
    data.user.role = "VIEWER"; db.flush()
    assert client.post("/api/runs", headers=data.headers, json={"test_case_id": str(data.case.id)}).status_code == 403


def test_snapshot_preserves_authored_contract(db, execution_data):
    d = execution_data
    d.step.action = "TYPE"; d.step.page_object_id = d.obj.id
    d.step.input_value = "{{NAME}}"; d.step.timeout_ms = 1500; d.step.is_optional = True
    assertion = StepAssertion(org_id=d.org.id, step_id=d.step.id, position=1,
                              assertion_type="VALUE_EQUALS", expected_value="{{NAME}}")
    db.add(assertion); db.flush(); db.expire(d.step, ["assertions"])
    snapshot, report = build_snapshot(test_case=d.case, steps=[d.step], env_variables=[], run_variables={"NAME": "Ada"}, db=db)
    assert report.valid
    original_hash = compute_snapshot_sha256(snapshot)
    d.obj.locators[0]["value"] = "changed"
    payload = build_agent_payload(snapshot=snapshot, env_variables=[], run_variables={"NAME": "changed"},
        protocol_version=2, run_id="run", lease_id="lease", timeout_seconds=60, test_case_id=str(d.case.id), test_case_version=1)
    step = payload["execute_request"]["execution_plan"]["steps"][0]
    assert step["resolved_input"] == "Ada"
    assert step["locator"]["selector"] == "missing"
    assert step["locator"]["fallbacks"] == [{"strategy": "CSS_SELECTOR", "selector": "#name"}]
    assert step["assertions"][0]["expected_value"] == "Ada"
    assert step["timeout_ms"] == 1500 and step["is_optional"] is True
    assert compute_snapshot_sha256(snapshot) == original_hash


def test_secret_masking_and_recursive_validation(db, execution_data):
    d = execution_data
    d.step.input_value = "{{ALIAS}}"; d.step.target_url = None
    secret = SimpleNamespace(key="PASSWORD", value_encrypted="do-not-persist", key_id=None,
                             deleted_at=None, is_secret=True)
    environment = SimpleNamespace(id=uuid.uuid4(), version=1, base_url=None)
    kwargs = dict(test_case=d.case, steps=[d.step], environment=environment, env_variables=[secret], db=db)
    snapshot, report = build_snapshot(**kwargs, run_variables={"ALIAS": "{{PASSWORD}}"})
    assert report.valid and "do-not-persist" not in str(snapshot)
    assert snapshot["steps"][0]["display_value"] == "****"
    with pytest.raises(ValueError, match="Secret overrides"):
        build_snapshot(**kwargs, run_variables={"PASSWORD": "unsafe"})
    snapshot, report = build_snapshot(**kwargs, run_variables={"ALIAS": "{{LOOP}}", "LOOP": "{{ALIAS}}"})
    assert not report.valid and report.errors[0].issue == "CYCLE_DETECTED"


def test_cross_org_object_rejected(client, db, execution_data):
    d = execution_data
    d.obj.org_id = uuid.uuid4()
    d.step.page_object_id = d.obj.id
    db.flush()
    response = client.post("/api/runs", headers=d.headers, json={"test_case_id": str(d.case.id)})
    assert response.status_code == 422, response.text


def test_capacity_and_capability_matching(client, db, execution_data):
    d = execution_data
    queue_and_poll(client, d)
    assert client.post("/api/runs", headers=d.headers, json={"test_case_id": str(d.case.id)}).status_code == 201
    assert client.post("/api/agents/poll", headers=d.agent_headers).json() == {"status": "no_work"}
    # Another agent that cannot navigate must not claim the waiting run.
    key = uuid.uuid4().hex
    db.add(Agent(org_id=d.org.id, name="Unsupported", api_key_hash=AgentRepository.hash_api_key(key),
                 capabilities={"protocol_version": 2, "supported_actions": ["CLICK"]}))
    db.flush()
    assert client.post("/api/agents/poll", headers={"X-Agent-Api-Key": key}).json() == {"status": "no_work"}


def test_secret_payload_and_changed_environment(db, execution_data):
    d = execution_data
    d.step.target_url = "https://example.test/{{PASSWORD}}"
    secret = SimpleNamespace(key="PASSWORD", value_encrypted="transient-only", key_id=None,
                             deleted_at=None, is_secret=True)
    env = SimpleNamespace(id=uuid.uuid4(), version=1, base_url=None)
    snapshot, report = build_snapshot(test_case=d.case, steps=[d.step], environment=env,
                                     env_variables=[secret], run_variables={}, db=db)
    assert report.valid
    args = dict(snapshot=snapshot, env_variables=[secret], run_variables={}, environment=env,
                protocol_version=2, run_id="run", lease_id="lease", timeout_seconds=60,
                test_case_id=str(d.case.id), test_case_version=1)
    step = build_agent_payload(**args)["execute_request"]["execution_plan"]["steps"][0]
    assert step["resolved_input"] == "https://example.test/transient-only"
    assert step["display_value"] == "https://example.test/****"
    env.version = 2
    with pytest.raises(ValueError, match="changed"):
        build_agent_payload(**args)


def test_storage_rejects_sibling_prefix(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.storage.local import LocalStorageProvider
    monkeypatch.setattr(settings, "ARTIFACT_LOCAL_BASE_PATH", str(tmp_path / "artifacts"))
    provider = LocalStorageProvider()
    with pytest.raises(ValueError, match="Unsafe"):
        provider.save("../artifacts-other/escape.png", b"data")


def test_flow_snapshot_rejects_stale_version(db, execution_data):
    from app.models.flows import Flow, FlowStep
    d = execution_data
    flow = Flow(org_id=d.org.id, name="Reusable navigation", version=2)
    db.add(flow); db.flush()
    db.add(FlowStep(org_id=d.org.id, flow_id=flow.id, position=1, action="NAVIGATE",
                    target_url="{{URL}}", timeout_ms=2000, is_optional=True))
    d.step.action = "FLOW"; d.step.flow_id = flow.id; d.step.flow_version = 1
    d.step.target_url = None
    db.flush()
    args = dict(test_case=d.case, steps=[d.step], env_variables=[], run_variables={"URL": "about:blank"}, db=db)
    with pytest.raises(ValueError, match="Pinned flow version"):
        build_snapshot(**args)
    d.step.flow_version = 2
    snapshot, report = build_snapshot(**args)
    assert report.valid
    child = snapshot["steps"][0]
    assert child["display_value"] == "about:blank"
    assert child["timeout_ms"] == 2000 and child["is_optional"]
    assert child["from_flow_version"] == 2


def test_failed_callback_creates_one_delayed_retry(client, db, execution_data):
    from app.models.schedules import RetryRecord
    d = execution_data
    request = queue_and_poll(client, d)
    run = db.get(Run, uuid.UUID(request["run_id"]))
    run.run_variables = {"_retry_max_retries": 2, "_retry_on_failure": True,
                         "_retry_delay_seconds": 60}
    db.flush()
    body = {"lease_id": request["lease_id"], "status": "FAILED",
            "step_results": [result_for(request["execution_plan"]["steps"][0], "FAILED")]}
    path = f"/api/runs/{run.id}/agent-update"
    for _ in range(2):
        response = client.post(path, headers=d.agent_headers, json=body)
        assert response.status_code == 200, response.text
    records = db.scalars(select(RetryRecord).where(RetryRecord.original_run_id == run.id)).all()
    assert len(records) == 1
    retry = db.get(Run, records[0].retry_run_id)
    assert retry.available_after > utcnow()
    assert retry.total_steps == run.total_steps
    assert retry.execution_snapshot == run.execution_snapshot
    assert client.post("/api/agents/poll", headers=d.agent_headers).json() == {"status": "no_work"}
    retry.available_after = utcnow() - timedelta(seconds=1)
    db.flush()
    assert client.post("/api/agents/poll", headers=d.agent_headers).json()["execute_request"]["run_id"] == str(retry.id)


def test_watchdog_requeue_has_unique_events(client, db, execution_data, monkeypatch):
    from app.tasks import watchdog
    d = execution_data
    request = queue_and_poll(client, d)
    run = db.get(Run, uuid.UUID(request["run_id"]))
    run.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    attempts = run.dispatch_attempt_count
    monkeypatch.setattr(watchdog, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    result = watchdog.reap_expired_leases.run()
    assert result["dispatched_requeued"] == 1
    assert run.dispatch_attempt_count == attempts
    events = db.scalars(select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.sequence)).all()
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    assert [e.event for e in events][-2:] == ["LEASE_EXPIRED", "RUN_REQUEUED"]


def test_offline_detector_records_one_audit(db, execution_data, monkeypatch):
    from app.tasks import agent_offline_detector as detector
    from app.models.foundation import AuditEvent
    d = execution_data
    d.agent.status = "IDLE"
    d.agent.last_heartbeat = utcnow() - timedelta(days=1)
    db.flush()
    monkeypatch.setattr(detector, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    assert detector.detect_offline_agents.run()["marked_offline"] == 1
    assert detector.detect_offline_agents.run()["marked_offline"] == 0
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == d.agent.id)).all()
    assert len(events) == 1 and events[0].action == "AGENT_OFFLINE"


def test_deadline_is_fixed_and_late_completion_rejected(client, db, execution_data):
    d = execution_data
    request = queue_and_poll(client, d)
    run = db.get(Run, uuid.UUID(request["run_id"]))
    run.timeout_seconds = 20
    db.flush()
    path = f"/api/runs/{run.id}/agent-update"
    body = {"lease_id": request["lease_id"], "status": "RUNNING"}
    assert client.post(path, headers=d.agent_headers, json=body).status_code == 200
    deadline = run.deadline_at
    assert deadline == run.started_at + timedelta(seconds=20)
    assert client.post(path, headers=d.agent_headers, json=body).status_code == 200
    assert run.deadline_at == deadline and run.lease_expires_at <= deadline
    run.deadline_at = utcnow() - timedelta(seconds=1)
    run.lease_expires_at = utcnow() + timedelta(seconds=60)
    db.flush()
    body.update(status="COMPLETED", step_results=[result_for(request["execution_plan"]["steps"][0])])
    assert client.post(path, headers=d.agent_headers, json=body).status_code == 409
    assert run.status == "RUNNING" and run.passed_steps == 0
