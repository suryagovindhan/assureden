from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from server.database import get_db
from server.models import Agent, TestReport

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])

@router.get("/dashboard")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    total_tests = db.query(TestReport).count()
    
    passed_tests = db.query(TestReport).filter(TestReport.status == "SUCCESS").count()
    pass_rate = round((passed_tests / total_tests * 100), 1) if total_tests > 0 else 0.0
    
    total_agents = db.query(Agent).count()
    online_agents = db.query(Agent).filter(Agent.status == "ONLINE").count()
    
    return {
        "total_tests": total_tests,
        "pass_rate": pass_rate,
        "total_agents": total_agents,
        "online_agents": online_agents
    }
