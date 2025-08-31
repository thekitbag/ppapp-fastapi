from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List

from app.db import get_db
from app.services import GoalService
from app.schemas import GoalCreate, Goal


router = APIRouter()


def get_goal_service(db: Session = Depends(get_db)) -> GoalService:
    """Dependency to get GoalService instance."""
    return GoalService(db)


@router.post("", response_model=Goal, status_code=201)
def create_goal(
    payload: GoalCreate,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Create a new goal."""
    return goal_service.create_goal(payload)


@router.get("", response_model=List[Goal])
def list_goals(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    goal_service: GoalService = Depends(get_goal_service)
):
    """List goals."""
    return goal_service.list_goals(skip=skip, limit=limit)


@router.get("/{goal_id}", response_model=Goal)
def get_goal(
    goal_id: str,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Get a specific goal by ID."""
    return goal_service.get_goal(goal_id)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(
    goal_id: str,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Delete a goal."""
    goal_service.delete_goal(goal_id)
    return None