from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List

from app.db import get_db
from app.services import GoalService
from app.schemas import GoalCreate, GoalOut, GoalDetail, GoalUpdate, KRCreate, KROut, TaskGoalLink, TaskGoalLinkResponse

router = APIRouter()


def get_goal_service(db: Session = Depends(get_db)) -> GoalService:
    """Dependency to get GoalService instance."""
    return GoalService(db)


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(
    payload: GoalCreate,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Create a new goal."""
    return goal_service.create_goal(payload)


@router.get("", response_model=List[GoalOut])
def list_goals(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    goal_service: GoalService = Depends(get_goal_service)
):
    """List all goals."""
    return goal_service.list_goals(skip=skip, limit=limit)


@router.get("/{goal_id}", response_model=GoalDetail)
def get_goal(
    goal_id: str,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Get a goal with its key results and linked tasks."""
    return goal_service.get_goal_detail(goal_id)


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: str,
    goal_update: GoalUpdate,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Update a goal."""
    # TODO: Add update method to GoalService
    from app.models import Goal
    from app.exceptions import NotFoundError
    
    db = goal_service.db
    db_goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if not db_goal:
        raise NotFoundError("Goal", goal_id)
    
    update_data = goal_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_goal, field, value)
    
    db.commit()
    db.refresh(db_goal)
    return goal_service.goal_repo.to_schema(db_goal)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(
    goal_id: str,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Delete a goal."""
    goal_service.delete_goal(goal_id)
    return None


@router.post("/{goal_id}/krs", response_model=KROut, status_code=201)
def create_key_result(
    goal_id: str, 
    kr: KRCreate,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Create a key result for a goal."""
    return goal_service.create_key_result(goal_id, kr)


@router.delete("/{goal_id}/krs/{kr_id}", status_code=204)
def delete_key_result(
    goal_id: str,
    kr_id: str,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Delete a key result."""
    goal_service.delete_key_result(goal_id, kr_id)
    return None


@router.post("/{goal_id}/link-tasks", response_model=TaskGoalLinkResponse)
def link_tasks_to_goal(
    goal_id: str,
    link_data: TaskGoalLink,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Link tasks to a goal."""
    return goal_service.link_tasks_to_goal(goal_id, link_data)


@router.delete("/{goal_id}/link-tasks", response_model=TaskGoalLinkResponse)
def unlink_tasks_from_goal(
    goal_id: str,
    link_data: TaskGoalLink,
    goal_service: GoalService = Depends(get_goal_service)
):
    """Unlink tasks from a goal."""
    return goal_service.unlink_tasks_from_goal(goal_id, link_data)