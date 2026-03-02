from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime

from app.db import get_db
from app.services.reporting import ReportingService
from app.schemas import GoalReportResponse, SummaryReportResponse, BreakdownReportResponse
from app.api.v1.auth import get_current_user_dep

router = APIRouter()


def get_reporting_service(db: Session = Depends(get_db)) -> ReportingService:
    return ReportingService(db)


@router.get("/goals/{goal_id}", response_model=GoalReportResponse)
def get_goal_report(
    goal_id: str,
    start_date: Optional[datetime] = Query(None, description="Inclusive start (ISO8601)"),
    end_date: Optional[datetime] = Query(None, description="Inclusive end (ISO8601)"),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    reporting_service: ReportingService = Depends(get_reporting_service),
):
    """Return cumulative completed task size for a goal and all its descendants."""
    return reporting_service.goal_progress_report(
        goal_id,
        current_user["user_id"],
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/breakdown", response_model=BreakdownReportResponse)
def get_breakdown_report(
    start_date: datetime = Query(..., description="Inclusive start (ISO8601)"),
    end_date: datetime = Query(..., description="Inclusive end (ISO8601)"),
    parent_goal_id: Optional[str] = Query(None, description="Drill into children of this goal; omit for root view"),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    reporting_service: ReportingService = Depends(get_reporting_service),
):
    """Return hierarchical breakdown of completed task points by goal level."""
    return reporting_service.breakdown_report(
        current_user["user_id"],
        start_date=start_date,
        end_date=end_date,
        parent_goal_id=parent_goal_id,
    )


@router.get("/summary", response_model=SummaryReportResponse)
def get_summary_report(
    start_date: datetime = Query(..., description="Inclusive start (ISO8601)"),
    end_date: datetime = Query(..., description="Inclusive end (ISO8601)"),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    reporting_service: ReportingService = Depends(get_reporting_service),
):
    """Return period productivity totals grouped by top-level goal roots plus unlinked tasks."""
    return reporting_service.summary_report(
        current_user["user_id"],
        start_date=start_date,
        end_date=end_date,
    )
