"""
reports.py — /api/reports
Now powered by RunExecution and RunStepExecution (QA-first schema).
"""
import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from server.database import get_db
from server.models import RunExecution, RunStepExecution, TestCase
from server.routers.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/")
def list_runs(
    limit: int = Query(50, le=200),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user)
):
    q = (db.query(RunExecution)
           .options(joinedload(RunExecution.test_case))
           .order_by(RunExecution.start_time.desc()))
    if status:
        q = q.filter(RunExecution.status == status.upper())
    q = q.limit(limit)

    return [
        {
            "id": r.id,
            "test_case_id": r.test_case_id,
            "test_case_name": r.test_case.name if r.test_case else None,
            "agent_id": r.agent_id,
            "status": r.status,
            "failure_classification": r.failure_classification,
            "total_time_ms": r.total_time_ms,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
        }
        for r in q.all()
    ]


@router.get("/{run_id}")
def get_run_detail(run_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    run = (db.query(RunExecution)
             .options(
                 joinedload(RunExecution.steps),
                 joinedload(RunExecution.artifacts),
                 joinedload(RunExecution.test_case),
             )
             .filter(RunExecution.id == run_id)
             .first())
    if not run:
        from fastapi import HTTPException
        raise HTTPException(404, "Run not found.")

    return {
        "id": run.id,
        "test_case": {"id": run.test_case_id, "name": run.test_case.name if run.test_case else None},
        "agent_id": run.agent_id,
        "status": run.status,
        "failure_classification": run.failure_classification,
        "failure_signature": run.failure_signature,
        "total_time_ms": run.total_time_ms,
        "start_time": run.start_time.isoformat() if run.start_time else None,
        "end_time": run.end_time.isoformat() if run.end_time else None,
        "steps": [
            {
                "id": s.id,
                "step_id": s.step_id,
                "status": s.status,
                "is_healed": s.fallback_success,    # ← key QA metric
                "primary_success": s.primary_success,
                "failed_all": s.failed_all,
                "locators_attempted": json.loads(s.locators_attempted) if s.locators_attempted else [],
                "successful_locator": s.successful_locator,
                "retries_used": s.retries_used,
                "execution_time_ms": s.execution_time_ms,
                "input_masked": s.input_masked,
                "error_message": s.error_message,
                "stack_trace": s.stack_trace,
            }
            for s in sorted(run.steps, key=lambda x: x.id)
        ],
        "artifacts": [
            {"type": a.artifact_type, "url": a.storage_path,
             "step_execution_id": a.step_execution_id}
            for a in run.artifacts
        ]
    }


@router.patch("/{run_id}/classify")
def classify_run(
    run_id: str,
    classification: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user)
):
    """Allow QA to mark failure as: BUG | TEST_ISSUE | ENV_ISSUE | FLAKY"""
    valid = {"BUG", "TEST_ISSUE", "ENV_ISSUE", "FLAKY"}
    if classification.upper() not in valid:
        from fastapi import HTTPException
        raise HTTPException(400, f"Invalid classification. Must be one of: {valid}")
    run = db.query(RunExecution).filter(RunExecution.id == run_id).first()
    if not run:
        from fastapi import HTTPException
        raise HTTPException(404, "Run not found.")
    run.failure_classification = classification.upper()
    db.commit()
    return {"status": "classified", "classification": run.failure_classification}
