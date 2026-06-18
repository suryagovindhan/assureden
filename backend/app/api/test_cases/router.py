"""
api/test_cases/router.py — Phase 2 Test Case Management — 19 endpoints

Auth: all routes require JWT. org_id injected from current_user.
Role enforcement:
  VIEWER  → GET routes
  TESTER  → create / update / step create / step update / assertions
  LEAD    → soft-delete suite / soft-delete case
  ADMIN   → inherits all

Optimistic locking: PUT /cases/{id} → 409 VERSION_CONFLICT on mismatch.
Reorder validation: all IDs must belong to same case, no dups, no missing.
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.db.repositories.test_cases import (
    TestSuiteRepository, TestCaseRepository,
    TestStepRepository, StepAssertionRepository,
)
from app.schemas.test_cases import (
    TestSuiteCreate, TestSuiteUpdate, TestSuiteRead,
    TestCaseCreate, TestCaseUpdate, TestCaseRead, TestCaseSummary,
    TestStepCreate, TestStepUpdate, TestStepRead,
    StepAssertionCreate, StepAssertionUpdate, StepAssertionRead,
    StepReorderRequest,
)
from app.models.foundation import User

router = APIRouter(tags=["Test Cases"])


# ─── dependency helpers ───────────────────────────────────────────────────────

def _suite_repo(db: Session = Depends(get_db)) -> TestSuiteRepository:
    return TestSuiteRepository(db)


def _case_repo(db: Session = Depends(get_db)) -> TestCaseRepository:
    return TestCaseRepository(db)


def _step_repo(db: Session = Depends(get_db)) -> TestStepRepository:
    return TestStepRepository(db)


def _assertion_repo(db: Session = Depends(get_db)) -> StepAssertionRepository:
    return StepAssertionRepository(db)


# ─────────────────────────────────────────────────────────────────────────────
# TestSuite endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/suites", response_model=list[TestSuiteRead])
def list_suites(
    status: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit:  int = Query(100, ge=1, le=500),
    repo:   TestSuiteRepository = Depends(_suite_repo),
    user:   User = Depends(get_current_user),
):
    suites = repo.list(user.org_id, status=status, offset=offset, limit=limit)
    result = []
    for s in suites:
        sr = TestSuiteRead.model_validate(s)
        sr.case_count = repo.get_case_count(s.id, user.org_id)
        result.append(sr)
    return result


@router.post("/suites", response_model=TestSuiteRead, status_code=201)
def create_suite(
    body: TestSuiteCreate,
    repo: TestSuiteRepository = Depends(_suite_repo),
    user: User = Depends(require_role("TESTER")),
):
    suite = repo.create(user.org_id, user.id, **body.model_dump())
    repo.db.commit()
    sr = TestSuiteRead.model_validate(suite)
    sr.case_count = 0
    return sr


@router.get("/suites/{suite_id}", response_model=TestSuiteRead)
def get_suite(
    suite_id: UUID,
    repo: TestSuiteRepository = Depends(_suite_repo),
    user: User = Depends(get_current_user),
):
    suite = repo.get(suite_id, user.org_id)
    if not suite:
        raise HTTPException(404, "Suite not found")
    sr = TestSuiteRead.model_validate(suite)
    sr.case_count = repo.get_case_count(suite_id, user.org_id)
    return sr


@router.put("/suites/{suite_id}", response_model=TestSuiteRead)
def update_suite(
    suite_id: UUID,
    body: TestSuiteUpdate,
    repo: TestSuiteRepository = Depends(_suite_repo),
    user: User = Depends(require_role("LEAD")),
):
    suite = repo.get(suite_id, user.org_id)
    if not suite:
        raise HTTPException(404, "Suite not found")
    suite = repo.update(suite, user.id, **body.model_dump(exclude_none=True))
    repo.db.commit()
    sr = TestSuiteRead.model_validate(suite)
    sr.case_count = repo.get_case_count(suite_id, user.org_id)
    return sr


@router.delete("/suites/{suite_id}", status_code=204)
def delete_suite(
    suite_id: UUID,
    repo: TestSuiteRepository = Depends(_suite_repo),
    user: User = Depends(require_role("LEAD")),
):
    suite = repo.get(suite_id, user.org_id)
    if not suite:
        raise HTTPException(404, "Suite not found")
    repo.soft_delete(suite, user.id)
    repo.db.commit()


@router.get("/suites/{suite_id}/cases", response_model=list[TestCaseSummary])
def list_cases_in_suite(
    suite_id: UUID,
    offset: int = Query(0, ge=0),
    limit:  int = Query(100, ge=1, le=500),
    suite_repo: TestSuiteRepository = Depends(_suite_repo),
    case_repo:  TestCaseRepository  = Depends(_case_repo),
    user: User = Depends(get_current_user),
):
    suite = suite_repo.get(suite_id, user.org_id)
    if not suite:
        raise HTTPException(404, "Suite not found")
    return case_repo.list_by_suite(suite_id, user.org_id, offset=offset, limit=limit)


# ─────────────────────────────────────────────────────────────────────────────
# TestCase endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/cases/search", response_model=list[TestCaseSummary])
def search_cases(
    q:      str  = Query(..., min_length=1),
    offset: int  = Query(0, ge=0),
    limit:  int  = Query(50, ge=1, le=200),
    repo:   TestCaseRepository = Depends(_case_repo),
    user:   User = Depends(get_current_user),
):
    return repo.search_by_name(q, user.org_id, offset=offset, limit=limit)


@router.get("/cases", response_model=list[TestCaseSummary])
def list_cases(
    status:         Optional[str]  = Query(None),
    priority:       Optional[str]  = Query(None),
    suite_id:       Optional[UUID] = Query(None),
    application_id: Optional[UUID] = Query(None),
    offset:         int            = Query(0, ge=0),
    limit:          int            = Query(100, ge=1, le=500),
    repo:           TestCaseRepository = Depends(_case_repo),
    user:           User = Depends(get_current_user),
):
    return repo.list_all(
        user.org_id,
        status=status, priority=priority,
        suite_id=suite_id, application_id=application_id,
        offset=offset, limit=limit,
    )


@router.post("/cases", response_model=TestCaseSummary, status_code=201)
def create_case(
    body: TestCaseCreate,
    repo: TestCaseRepository = Depends(_case_repo),
    user: User = Depends(require_role("TESTER")),
):
    case = repo.create(user.org_id, user.id, **body.model_dump())
    repo.db.commit()
    return case


@router.get("/cases/{case_id}", response_model=TestCaseRead)
def get_case(
    case_id:     UUID,
    case_repo:   TestCaseRepository    = Depends(_case_repo),
    step_repo:   TestStepRepository    = Depends(_step_repo),
    assert_repo: StepAssertionRepository = Depends(_assertion_repo),
    user:        User = Depends(get_current_user),
):
    case = case_repo.get_live(case_id, user.org_id)
    if not case:
        raise HTTPException(404, "Test case not found")

    # Build nested structure: steps + assertions per step (editor view = all live)
    steps = step_repo.list_all_live(case_id, user.org_id)
    step_reads = []
    for step in steps:
        assertions = assert_repo.list_by_step(step.id, user.org_id, active_only=False)
        sr = TestStepRead.model_validate(step)
        sr.assertions = [StepAssertionRead.model_validate(a) for a in assertions]
        step_reads.append(sr)

    cr = TestCaseRead.model_validate(case)
    cr.steps = step_reads
    return cr


@router.put("/cases/{case_id}", response_model=TestCaseSummary)
def update_case(
    case_id: UUID,
    body:    TestCaseUpdate,
    repo:    TestCaseRepository = Depends(_case_repo),
    user:    User = Depends(require_role("TESTER")),
):
    case = repo.get_live(case_id, user.org_id)
    if not case:
        raise HTTPException(404, "Test case not found")
    # Optimistic locking handled inside repo.update() — raises 409 on mismatch
    update_data = body.model_dump(exclude_none=True)
    submitted_version = update_data.pop("version")
    case = repo.update(case, user.id, submitted_version=submitted_version, **update_data)
    repo.db.commit()
    return case


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(
    case_id:   UUID,
    case_repo: TestCaseRepository = Depends(_case_repo),
    user:      User = Depends(require_role("LEAD")),
):
    case = case_repo.get_live(case_id, user.org_id)
    if not case:
        raise HTTPException(404, "Test case not found")
    case_repo.soft_delete(case, user.id)
    case_repo.db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# TestStep endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/steps", response_model=TestStepRead, status_code=201)
def add_step(
    case_id:     UUID,
    body:        TestStepCreate,
    case_repo:   TestCaseRepository  = Depends(_case_repo),
    step_repo:   TestStepRepository  = Depends(_step_repo),
    user:        User = Depends(require_role("TESTER")),
):
    case = case_repo.get_live(case_id, user.org_id)
    if not case:
        raise HTTPException(404, "Test case not found")
    step = step_repo.create(case, user.id, case_repo, **body.model_dump())
    case_repo.db.commit()
    sr = TestStepRead.model_validate(step)
    sr.assertions = []
    return sr


@router.put("/cases/{case_id}/steps/reorder", response_model=list[TestStepRead])
def reorder_steps(
    case_id:   UUID,
    body:      StepReorderRequest,
    case_repo: TestCaseRepository = Depends(_case_repo),
    step_repo: TestStepRepository = Depends(_step_repo),
    user:      User = Depends(require_role("TESTER")),
):
    case = case_repo.get_live(case_id, user.org_id)
    if not case:
        raise HTTPException(404, "Test case not found")
    steps = step_repo.reorder(case, body.step_ids, user.id, case_repo)
    case_repo.db.commit()
    return [TestStepRead.model_validate(s) for s in steps]


@router.put("/steps/{step_id}", response_model=TestStepRead)
def update_step(
    step_id:   UUID,
    body:      TestStepUpdate,
    case_repo: TestCaseRepository = Depends(_case_repo),
    step_repo: TestStepRepository = Depends(_step_repo),
    user:      User = Depends(require_role("TESTER")),
    db:        Session = Depends(get_db),
):
    step = step_repo.get_live(step_id, user.org_id)
    if not step:
        raise HTTPException(404, "Step not found")
    case = case_repo.get_live(step.test_case_id, user.org_id)
    if not case:
        raise HTTPException(404, "Parent test case not found")
    step = step_repo.update(step, case, user.id, case_repo, **body.model_dump(exclude_none=True))
    db.commit()
    sr = TestStepRead.model_validate(step)
    sr.assertions = []
    return sr


@router.delete("/steps/{step_id}", status_code=204)
def delete_step(
    step_id:   UUID,
    case_repo: TestCaseRepository = Depends(_case_repo),
    step_repo: TestStepRepository = Depends(_step_repo),
    user:      User = Depends(require_role("TESTER")),
    db:        Session = Depends(get_db),
):
    step = step_repo.get_live(step_id, user.org_id)
    if not step:
        raise HTTPException(404, "Step not found")
    case = case_repo.get_live(step.test_case_id, user.org_id)
    if not case:
        raise HTTPException(404, "Parent test case not found")
    step_repo.soft_delete(step, case, user.id, case_repo)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# StepAssertion endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/steps/{step_id}/assertions", response_model=StepAssertionRead, status_code=201)
def add_assertion(
    step_id:     UUID,
    body:        StepAssertionCreate,
    step_repo:   TestStepRepository      = Depends(_step_repo),
    assert_repo: StepAssertionRepository = Depends(_assertion_repo),
    user:        User = Depends(require_role("TESTER")),
    db:          Session = Depends(get_db),
):
    step = step_repo.get_live(step_id, user.org_id)
    if not step:
        raise HTTPException(404, "Step not found")
    assertion = assert_repo.create(step, user.id, **body.model_dump())
    db.commit()
    return assertion


@router.put("/assertions/{assertion_id}", response_model=StepAssertionRead)
def update_assertion(
    assertion_id: UUID,
    body:         StepAssertionUpdate,
    assert_repo:  StepAssertionRepository = Depends(_assertion_repo),
    user:         User = Depends(require_role("TESTER")),
    db:           Session = Depends(get_db),
):
    assertion = assert_repo.get_live(assertion_id, user.org_id)
    if not assertion:
        raise HTTPException(404, "Assertion not found")
    assertion = assert_repo.update(assertion, user.id, **body.model_dump(exclude_none=True))
    db.commit()
    return assertion


@router.delete("/assertions/{assertion_id}", status_code=204)
def delete_assertion(
    assertion_id: UUID,
    assert_repo:  StepAssertionRepository = Depends(_assertion_repo),
    user:         User = Depends(require_role("TESTER")),
    db:           Session = Depends(get_db),
):
    assertion = assert_repo.get_live(assertion_id, user.org_id)
    if not assertion:
        raise HTTPException(404, "Assertion not found")
    assert_repo.soft_delete(assertion, user.id)
    db.commit()
