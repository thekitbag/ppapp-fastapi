from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

from app.db import get_db
from app.services import TaskService
from app.schemas import TaskCreate, TaskOut, TaskUpdate
from app.api.v1.auth import get_current_user_dep


router = APIRouter()


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    """Dependency to get TaskService instance."""
    return TaskService(db)


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    payload: TaskCreate,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    task_service: TaskService = Depends(get_task_service)
):
    """Create a new task for authenticated user."""
    return task_service.create_task(payload, current_user["user_id"])


@router.get("", response_model=List[TaskOut])
def list_tasks(
    status: List[str] = Query(None),
    project_id: Optional[str] = Query(None),
    goal_id: Optional[str] = Query(None),
    tag: List[str] = Query(None),
    due_before: Optional[datetime] = Query(None),
    due_after: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(None, ge=1, le=1000),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    task_service: TaskService = Depends(get_task_service)
):
    """List tasks for authenticated user with filtering support.

    Filters:
    - status: List of status values to include
    - project_id: Filter by project UUID
    - goal_id: Filter by goal UUID (searches both goal_id field and goal links)
    - tag: List of tag names (tasks must have all specified tags)
    - due_before: Show tasks due before this datetime (checks both hard_due_at and soft_due_at)
    - due_after: Show tasks due after this datetime (checks both hard_due_at and soft_due_at)
    - search: Free-text search across task title and description
    """
    return task_service.list_tasks(
        user_id=current_user["user_id"],
        status=status,
        project_id=project_id,
        goal_id=goal_id,
        tags=tag,
        due_before=due_before,
        due_after=due_after,
        search=search,
        skip=skip,
        limit=limit
    )


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    task_service: TaskService = Depends(get_task_service)
):
    """Get a specific task by ID for authenticated user."""
    return task_service.get_task(task_id, current_user["user_id"])


@router.put("/{task_id}", response_model=TaskOut)
@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    update_data: TaskUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    task_service: TaskService = Depends(get_task_service)
):
    """Update a task for authenticated user (supports both PUT and PATCH for compatibility)."""
    # Convert pydantic model to dict, excluding None values
    update_dict = update_data.model_dump(exclude_unset=True)
    return task_service.update_task(task_id, current_user["user_id"], update_dict)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    task_service: TaskService = Depends(get_task_service)
):
    """Delete a task for authenticated user."""
    task_service.delete_task(task_id, current_user["user_id"])
    return None


class PromoteWeekBody(BaseModel):
    task_ids: List[str]


@router.post("/promote-week")
def promote_week(
    body: PromoteWeekBody,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    task_service: TaskService = Depends(get_task_service)
):
    """Promote tasks to week status for authenticated user."""
    updated_ids = task_service.promote_tasks_to_week(body.task_ids, current_user["user_id"])
    return {"updated": len(updated_ids), "ids": updated_ids}