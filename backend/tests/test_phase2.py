"""
tests/test_phase2.py — Phase 2 Test Case Management integration tests

Follows the same fixture pattern as test_phase1.py:
  - module-scoped TestClient (no DB override; uses live seeded database)
  - module-scoped db fixture using SessionLocal()
  - _login() helper returns a JWT access token
  - _headers() wraps the token

9 tests:
  1. test_suite_org_scoped                 — suite visible to its creator's org
  2. test_case_soft_delete                 — case excluded from list; GET → 404
  3. test_step_soft_delete_and_renumber    — step hidden; remaining steps renumbered 1..N
  4. test_step_create_and_reorder          — positions correct; duplicates/missing IDs → 422
  5. test_assertion_soft_delete_vs_disable — is_enabled=False keeps row; deleted_at hides it
  6. test_case_version_increment           — version increments on step add / update / delete
  7. test_optimistic_locking               — stale version → 409 VERSION_CONFLICT; correct version → 200
  8. test_audit_event_via_db               — AuditEvent row created in DB after case create
  9. test_case_search                      — keyword search returns matching cases
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.foundation import AuditEvent


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def db():
    from app.db.session import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _login(client: TestClient,
           email: str = "admin@assureden.com",
           password: str = "Admin@1234",
           org_slug: str = "default") -> str:
    r = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "org_slug": org_slug},
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_suite(client, headers, name=None) -> dict:
    r = client.post(
        "/api/suites",
        json={"name": name or f"Suite-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert r.status_code == 201, f"create_suite failed: {r.text}"
    return r.json()


def _create_case(client, headers, suite_id, name=None) -> dict:
    r = client.post(
        "/api/cases",
        json={"name": name or f"Case-{uuid.uuid4().hex[:6]}", "suite_id": suite_id},
        headers=headers,
    )
    assert r.status_code == 201, f"create_case failed: {r.text}"
    return r.json()


def _add_step(client, headers, case_id, action="CLICK") -> dict:
    r = client.post(
        f"/api/cases/{case_id}/steps",
        json={"action": action},
        headers=headers,
    )
    assert r.status_code == 201, f"add_step failed: {r.text}"
    return r.json()


def _add_assertion(client, headers, step_id, atype="VISIBLE") -> dict:
    r = client.post(
        f"/api/steps/{step_id}/assertions",
        json={"assertion_type": atype},
        headers=headers,
    )
    assert r.status_code == 201, f"add_assertion failed: {r.text}"
    return r.json()


def _get_case(client, headers, case_id) -> dict:
    r = client.get(f"/api/cases/{case_id}", headers=headers)
    return r


# ─── Test 1: Suite org isolation ──────────────────────────────────────────────

def test_suite_org_scoped(client: TestClient):
    """Suite created by admin is visible in its own org's list; org_ids match."""
    token = _login(client)
    h = _headers(token)

    unique_name = f"OrgScopeTest-{uuid.uuid4().hex[:8]}"
    suite = _create_suite(client, h, name=unique_name)

    r = client.get("/api/suites", headers=h)
    assert r.status_code == 200
    names = [s["name"] for s in r.json()]
    assert unique_name in names, "Created suite must appear in list"

    all_suites = r.json()
    # All suites returned must belong to the same org as the created one
    suite_org = suite["org_id"]
    assert all(s["org_id"] == suite_org for s in all_suites), \
        "All suites must share the authenticated user's org_id"


# ─── Test 2: Case soft-delete ─────────────────────────────────────────────────

def test_case_soft_delete(client: TestClient):
    """Soft-deleting a case removes it from list and returns 404 on GET."""
    token = _login(client)
    h = _headers(token)

    suite = _create_suite(client, h)
    case = _create_case(client, h, suite["id"])

    # Verify it appears in the suite's case list
    r = client.get(f"/api/suites/{suite['id']}/cases", headers=h)
    assert any(c["id"] == case["id"] for c in r.json()), \
        "Case must appear in suite's case list before deletion"

    # Soft-delete
    r = client.delete(f"/api/cases/{case['id']}", headers=h)
    assert r.status_code == 204, f"Expected 204, got {r.status_code}: {r.text}"

    # Must no longer appear in list
    r2 = client.get(f"/api/suites/{suite['id']}/cases", headers=h)
    assert r2.status_code == 200
    assert not any(c["id"] == case["id"] for c in r2.json()), \
        "Soft-deleted case must not appear in suite's case list"

    # GET by ID must return 404
    r3 = _get_case(client, h, case["id"])
    assert r3.status_code == 404, f"Expected 404 after soft-delete, got {r3.status_code}"


# ─── Test 3: Step soft-delete and renumber ────────────────────────────────────

def test_step_soft_delete_and_renumber(client: TestClient):
    """
    After soft-deleting step1, remaining steps are renumbered to 1..N.
    Deleted step does not appear in GET /cases/{id} steps list.
    """
    token = _login(client)
    h = _headers(token)

    suite = _create_suite(client, h)
    case = _create_case(client, h, suite["id"])

    step1 = _add_step(client, h, case["id"], "CLICK")
    step2 = _add_step(client, h, case["id"], "TYPE")
    step3 = _add_step(client, h, case["id"], "NAVIGATE")

    assert step1["position"] == 1
    assert step2["position"] == 2
    assert step3["position"] == 3

    # Soft-delete step1 (middle would leave a gap; delete first = cleanest renumber test)
    r = client.delete(f"/api/steps/{step1['id']}", headers=h)
    assert r.status_code == 204, f"Expected 204, got {r.status_code}: {r.text}"

    # Remaining steps must be renumbered 1..N
    r2 = _get_case(client, h, case["id"])
    assert r2.status_code == 200
    steps = r2.json()["steps"]
    assert len(steps) == 2, f"Expected 2 remaining steps, got {len(steps)}"

    step_ids = [s["id"] for s in steps]
    assert step1["id"] not in step_ids, "Soft-deleted step must not appear in GET /cases/{id}"

    positions = [s["position"] for s in steps]
    assert positions == [1, 2], f"Expected renumbered positions [1, 2], got {positions}"


# ─── Test 4: Reorder ──────────────────────────────────────────────────────────

def test_step_create_and_reorder(client: TestClient):
    """
    Reorder produces correct positions.
    Duplicate IDs → 422.
    Missing IDs → 422.
    Case version increments after reorder.
    """
    token = _login(client)
    h = _headers(token)

    suite = _create_suite(client, h)
    case = _create_case(client, h, suite["id"])

    s1 = _add_step(client, h, case["id"], "NAVIGATE")
    s2 = _add_step(client, h, case["id"], "TYPE")
    s3 = _add_step(client, h, case["id"], "CLICK")

    version_before = _get_case(client, h, case["id"]).json()["version"]

    # Reorder: s3 → s1 → s2
    r = client.put(
        f"/api/cases/{case['id']}/steps/reorder",
        json={"step_ids": [s3["id"], s1["id"], s2["id"]]},
        headers=h,
    )
    assert r.status_code == 200, f"Reorder failed: {r.text}"
    reordered = r.json()

    assert reordered[0]["id"] == s3["id"] and reordered[0]["position"] == 1
    assert reordered[1]["id"] == s1["id"] and reordered[1]["position"] == 2
    assert reordered[2]["id"] == s2["id"] and reordered[2]["position"] == 3

    # Step IDs must be immutable
    assert reordered[0]["id"] == s3["id"]

    # Case version must have incremented
    version_after = _get_case(client, h, case["id"]).json()["version"]
    assert version_after > version_before, \
        f"Case version must increment after reorder: before={version_before}, after={version_after}"

    # Duplicate IDs → 422
    r_dup = client.put(
        f"/api/cases/{case['id']}/steps/reorder",
        json={"step_ids": [s1["id"], s1["id"], s2["id"]]},
        headers=h,
    )
    assert r_dup.status_code == 422, f"Expected 422 for duplicate IDs, got {r_dup.status_code}"

    # Missing ID → 422
    r_missing = client.put(
        f"/api/cases/{case['id']}/steps/reorder",
        json={"step_ids": [s1["id"], s2["id"]]},  # s3 omitted
        headers=h,
    )
    assert r_missing.status_code == 422, f"Expected 422 for missing ID, got {r_missing.status_code}"


# ─── Test 5: Assertion soft-delete vs is_enabled ──────────────────────────────

def test_assertion_soft_delete_vs_disable(client: TestClient):
    """
    is_enabled=False: assertion retained and visible in GET /cases/{id} (editor view).
    deleted_at set:   assertion excluded from all live queries.
    These are two independent states.
    """
    token = _login(client)
    h = _headers(token)

    suite = _create_suite(client, h)
    case = _create_case(client, h, suite["id"])
    step = _add_step(client, h, case["id"])

    a1 = _add_assertion(client, h, step["id"], "VISIBLE")
    a2 = _add_assertion(client, h, step["id"], "TEXT_CONTAINS")

    # Disable a1 (is_enabled=False)
    r = client.put(f"/api/assertions/{a1['id']}", json={"is_enabled": False}, headers=h)
    assert r.status_code == 200
    assert r.json()["is_enabled"] is False

    # a1 must still appear in editor GET /cases/{id}
    case_data = _get_case(client, h, case["id"]).json()
    step_data = next(s for s in case_data["steps"] if s["id"] == step["id"])
    assertion_ids = [a["id"] for a in step_data["assertions"]]
    assert a1["id"] in assertion_ids, \
        "Disabled (but not deleted) assertion must still appear in editor view"
    disabled_a = next(a for a in step_data["assertions"] if a["id"] == a1["id"])
    assert disabled_a["is_enabled"] is False

    # Soft-delete a2
    r = client.delete(f"/api/assertions/{a2['id']}", headers=h)
    assert r.status_code == 204

    # a2 must NOT appear in any live query
    case_data2 = _get_case(client, h, case["id"]).json()
    step_data2 = next(s for s in case_data2["steps"] if s["id"] == step["id"])
    assertion_ids2 = [a["id"] for a in step_data2["assertions"]]
    assert a2["id"] not in assertion_ids2, \
        "Soft-deleted assertion must be excluded from all live queries"
    assert a1["id"] in assertion_ids2, \
        "Disabled (but not deleted) assertion must remain visible after a2 deletion"


# ─── Test 6: Case version increments on structural changes ────────────────────

def test_case_version_increment(client: TestClient):
    """
    version=1 at creation.
    version increments on: step add, step update, step delete.
    """
    token = _login(client)
    h = _headers(token)

    suite = _create_suite(client, h)
    case = _create_case(client, h, suite["id"])

    v1 = _get_case(client, h, case["id"]).json()["version"]
    assert v1 == 1, f"Initial version must be 1, got {v1}"

    # Add a step → version must increment
    step = _add_step(client, h, case["id"])
    v2 = _get_case(client, h, case["id"]).json()["version"]
    assert v2 == v1 + 1, f"Version after step add: expected {v1 + 1}, got {v2}"

    # Update step → version must increment
    r = client.put(
        f"/api/steps/{step['id']}",
        json={"description": "updated description"},
        headers=h,
    )
    assert r.status_code == 200
    v3 = _get_case(client, h, case["id"]).json()["version"]
    assert v3 == v2 + 1, f"Version after step update: expected {v2 + 1}, got {v3}"

    # Delete step → version must increment
    client.delete(f"/api/steps/{step['id']}", headers=h)
    v4 = _get_case(client, h, case["id"]).json()["version"]
    assert v4 == v3 + 1, f"Version after step delete: expected {v3 + 1}, got {v4}"


# ─── Test 7: Optimistic locking ───────────────────────────────────────────────

def test_optimistic_locking(client: TestClient):
    """
    PUT /cases/{id} with correct version → 200, version increments.
    PUT /cases/{id} with stale version  → 409 VERSION_CONFLICT.
    409 body must contain: error, current_version, submitted_version.
    """
    token = _login(client)
    h = _headers(token)

    suite = _create_suite(client, h)
    case = _create_case(client, h, suite["id"])

    current_version = _get_case(client, h, case["id"]).json()["version"]
    assert current_version == 1

    # Correct version → success
    r = client.put(
        f"/api/cases/{case['id']}",
        json={"version": current_version, "name": case["name"] + " (updated)"},
        headers=h,
    )
    assert r.status_code == 200, f"Expected 200 with correct version, got {r.status_code}: {r.text}"
    new_version = r.json()["version"]
    assert new_version == current_version + 1, \
        f"Version must increment on successful update: expected {current_version + 1}, got {new_version}"

    # Stale version → 409
    r_conflict = client.put(
        f"/api/cases/{case['id']}",
        json={"version": current_version, "name": "Stale update"},  # old version
        headers=h,
    )
    assert r_conflict.status_code == 409, \
        f"Expected 409 VERSION_CONFLICT with stale version, got {r_conflict.status_code}: {r_conflict.text}"

    detail = r_conflict.json()["detail"]
    assert detail["error"] == "VERSION_CONFLICT", \
        f"Expected error=VERSION_CONFLICT, got: {detail}"
    assert detail["current_version"] == new_version, \
        f"current_version in 409 body must be {new_version}, got {detail['current_version']}"
    assert detail["submitted_version"] == current_version, \
        f"submitted_version in 409 body must be {current_version}, got {detail['submitted_version']}"


# ─── Test 8: AuditEvent written to DB on case create ─────────────────────────

def test_audit_event_via_db(client: TestClient, db):
    """
    Creating a test case must produce an AuditEvent row in the database with
    action=CREATED and entity_id matching the new case's UUID.
    AuditEvent model stores: org_id, actor_id, entity_type, entity_id (UUID), action.
    """
    from sqlalchemy import select
    token = _login(client)
    h = _headers(token)

    suite = _create_suite(client, h)
    unique_name = f"AuditCase-{uuid.uuid4().hex[:8]}"
    case = _create_case(client, h, suite["id"], name=unique_name)
    case_uuid = uuid.UUID(case["id"])

    # Verify audit event in DB — query by entity_id (UUID) and action
    stmt = select(AuditEvent).where(
        AuditEvent.entity_id == case_uuid,
        AuditEvent.action == "CREATED",
    )
    event = db.scalar(stmt)
    assert event is not None, (
        f"AuditEvent with action=CREATED must exist for case {case['id']}"
    )
    assert event.entity_type == "test_case", (
        f"entity_type must be 'test_case', got {event.entity_type!r}"
    )


# ─── Test 9: Case keyword search ─────────────────────────────────────────────

def test_case_search(client: TestClient):
    """GET /cases/search?q=... returns cases matching by name substring."""
    token = _login(client)
    h = _headers(token)

    suite = _create_suite(client, h)
    unique = f"SearchableCase-{uuid.uuid4().hex[:8]}"
    _create_case(client, h, suite["id"], name=unique)

    # Use a distinctive prefix (≥ 3 chars)
    q = unique[:16]
    r = client.get(f"/api/cases/search?q={q}", headers=h)
    assert r.status_code == 200, f"Search returned {r.status_code}: {r.text}"
    names = [c["name"] for c in r.json()]
    assert any(unique in n for n in names), \
        f"Expected '{unique}' in search results, got: {names}"
