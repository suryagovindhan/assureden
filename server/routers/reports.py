from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from server.database import get_db
from server.models import TestReport

router = APIRouter(prefix="/api/reports", tags=["Reports"])

@router.get("/")
async def get_reports(db: Session = Depends(get_db)):
    """Fetch test execution reports"""
    reports = db.query(TestReport).order_by(TestReport.created_at.desc()).limit(50).all()
    return reports
