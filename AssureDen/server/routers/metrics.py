"""metrics.py — /api/metrics/dashboard  (QA-first schema)"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from server.database import get_db
from server.models import RunExecution, Agent, Project, TestCase
from server.routers.auth import get_current_user

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _=Depends(get_current_user)):
    total  = db.query(RunExecution).count()
    passed = db.query(RunExecution).filter(RunExecution.status == "SUCCESS").count()
    healed = db.query(RunExecution).filter(RunExecution.status == "SUCCESS").join(
        RunExecution.steps
    ).filter_by(fallback_success=True).count()
    rate   = round(passed / total * 100, 1) if total else 0.0
    return {
        "total_runs":      total,
        "pass_rate":       rate,
        "healed_runs":     healed,           # Runs that passed via locator fallback
        "total_agents":    db.query(Agent).filter(Agent.is_active == True).count(),
        "online_agents":   db.query(Agent).filter(Agent.status == "ONLINE").count(),
        "total_projects":  db.query(Project).count(),
        "total_cases":     db.query(TestCase).filter(TestCase.is_active == True).count(),
    }
