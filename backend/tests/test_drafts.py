import uuid
import pytest
from sqlalchemy import select
from test_execution_contract import execution_data  # noqa: F401
from app.models.test_cases import TestCase as Case, TestStep as Step
from app.models.foundation import AssetRevision


def recording():
    return {"name": "Reviewed recording", "steps": [
        {"action": "NAVIGATE", "input_value": "https://example.test"},
        {"action": "TYPE", "input_value": "Ada", "locators": [{"type": "ID", "value": "name"}]},
    ]}


def test_promote_is_idempotent_and_keeps_provenance(client, db, execution_data):
    d = execution_data
    response = client.post("/api/drafts", headers=d.headers, json=recording())
    assert response.status_code == 201, response.text
    draft = response.json()
    body = {"expected_version": 1, "page_id": str(d.obj.page_id)}
    promoted = client.post(f"/api/drafts/{draft['id']}/promote", headers=d.headers, json=body)
    assert promoted.status_code == 200, promoted.text
    assert client.post(f"/api/drafts/{draft['id']}/promote", headers=d.headers, json=body).json() == promoted.json()
    case_id = uuid.UUID(promoted.json()["test_case_id"])
    assert db.get(Case, case_id).status == "DRAFT"
    steps = db.scalars(select(Step).where(Step.test_case_id == case_id).order_by(Step.position)).all()
    assert len(steps) == 2 and steps[1].page_object_id and steps[1].input_value == "Ada"
    revision = db.scalar(select(AssetRevision).where(AssetRevision.asset_id == uuid.UUID(draft["id"])))
    assert revision.snapshot["test_case_id"] == str(case_id)
    assert client.put(f"/api/drafts/{draft['id']}", headers=d.headers,
                      json={**recording(), "expected_version": 1}).status_code == 409


def test_draft_permissions_version_and_destination(client, db, execution_data):
    d = execution_data
    draft = client.post("/api/drafts", headers=d.headers, json=recording()).json()
    path = f"/api/drafts/{draft['id']}"
    assert client.put(path, headers=d.headers, json={**recording(), "expected_version": 1}).json()["version"] == 2
    assert client.put(path, headers=d.headers, json={**recording(), "expected_version": 1}).status_code == 409
    assert client.post(path + "/promote", headers=d.headers,
                       json={"expected_version": 2, "page_id": str(uuid.uuid4())}).status_code == 422
    d.user.role = "VIEWER"; db.flush()
    assert client.post("/api/drafts", headers=d.headers, json=recording()).status_code == 403
    assert client.post(path + "/promote", headers=d.headers,
                       json={"expected_version": 2, "page_id": str(d.obj.page_id)}).status_code == 403


@pytest.mark.parametrize("step", [
    {"action": "TYPE", "input_value": "plain-password", "is_secret": True,
     "locators": [{"type": "ID", "value": "password"}]},
    {"action": "CLICK", "locators": []},
    {"action": "EXECUTE_SCRIPT", "input_value": "arbitrary code"},
])
def test_unsafe_or_incomplete_recording_rejected(client, execution_data, step):
    response = client.post("/api/drafts", headers=execution_data.headers,
                           json={"name": "Invalid", "steps": [step]})
    assert response.status_code == 422


def test_promote_flow_preserves_revision_and_rejects_other_target(client, db, execution_data):
    from app.models.flows import Flow, FlowStep
    from app.services.flow_revisions import get_revision
    d = execution_data
    payload = {**recording(), "name": "Recorded flow " + uuid.uuid4().hex}
    draft = client.post("/api/drafts", headers=d.headers, json=payload).json()
    path = f"/api/drafts/{draft['id']}/promote"
    body = {"expected_version": 1, "page_id": str(d.obj.page_id), "target": "FLOW"}
    result = client.post(path, headers=d.headers, json=body)
    assert result.status_code == 200, result.text
    assert client.post(path, headers=d.headers, json=body).json() == result.json()
    flow = db.get(Flow, uuid.UUID(result.json()["flow_id"]))
    revision = get_revision(db, flow, 1)
    assert flow.version == 1 and len(flow.checksum) == 64
    assert len(revision["steps"]) == 2
    assert revision["steps"][0]["target_url"] == "https://example.test"
    assert revision["steps"][1]["input_value"] == "Ada"
    assert revision["steps"][1]["page_object_id"]
    assert client.post(path, headers=d.headers, json={**body, "target": "TEST_CASE"}).status_code == 409
    other = client.post("/api/drafts", headers=d.headers, json=payload).json()
    assert client.post(f"/api/drafts/{other['id']}/promote", headers=d.headers, json=body).status_code == 409
    assert client.post(path, headers=d.headers, json={**body, "expected_version": 2}).status_code == 409


def test_business_action_promotion_and_versioned_reuse(client, db, execution_data):
    from app.services.snapshot_builder import build_snapshot
    d = execution_data
    payload = {"name": "Login action " + uuid.uuid4().hex, "steps": [
        {"action": "NAVIGATE", "input_value": "{{BASE_URL}}/login"}]}
    draft = client.post("/api/drafts", headers=d.headers, json=payload).json()
    path = f"/api/drafts/{draft['id']}/promote"
    body = {"expected_version": 1, "page_id": str(d.obj.page_id), "target": "BUSINESS_ACTION"}
    result = client.post(path, headers=d.headers, json=body)
    assert result.status_code == 200, result.text
    fid = result.json()["flow_id"]
    assert client.post(path, headers=d.headers, json=body).json() == result.json()
    assert client.post(path, headers=d.headers, json={**body, "target": "FLOW"}).status_code == 409
    asset = client.get(f"/api/flows/{fid}", headers=d.headers).json()
    assert asset["kind"] == "BUSINESS_ACTION"
    clone = client.post(f"/api/flows/{fid}/duplicate", headers=d.headers, json={"new_name": payload["name"] + " copy"})
    assert clone.status_code == 201 and clone.json()["kind"] == "BUSINESS_ACTION"
    response = client.put(f"/api/steps/{d.step.id}", headers=d.headers, json={
        "action": "FLOW", "flow_id": fid, "flow_version": 1,
        "target_url": None, "input_value": None, "page_object_id": None})
    assert response.status_code == 200, response.text
    snapshot, report = build_snapshot(test_case=d.case, steps=[d.step], env_variables=[],
                                     run_variables={"BASE_URL": "https://example.test"}, db=db)
    assert report.valid
    assert snapshot["steps"][0]["display_value"] == "https://example.test/login"
    assert snapshot["steps"][0]["from_asset_kind"] == "BUSINESS_ACTION"
    history = client.get(f"/api/flows/{fid}/revisions/1", headers=d.headers).json()
    assert history["kind"] == "BUSINESS_ACTION"


def test_business_action_creation_and_invalid_kind(client, execution_data):
    headers = execution_data.headers
    result = client.post("/api/flows/", headers=headers, json={"name": uuid.uuid4().hex, "kind": "BUSINESS_ACTION"})
    assert result.status_code == 201 and result.json()["kind"] == "BUSINESS_ACTION"
    assert client.post("/api/flows/", headers=headers, json={"name": "Invalid", "kind": "UNKNOWN"}).status_code == 422
