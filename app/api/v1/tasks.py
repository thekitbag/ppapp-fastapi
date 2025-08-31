from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from app.db import get_db
from app.services import TaskService
from app.schemas import TaskCreate, TaskOut


router = APIRouter()


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    """Dependency to get TaskService instance."""
    return TaskService(db)


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    payload: TaskCreate,
    task_service: TaskService = Depends(get_task_service)
):
    """Create a new task."""
    return task_service.create_task(payload)


@router.get("", response_model=List[TaskOut])
def list_tasks(
    status: List[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    task_service: TaskService = Depends(get_task_service)
):
    """List tasks with optional status filtering."""
    return task_service.list_tasks(status=status, skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    task_service: TaskService = Depends(get_task_service)
):
    """Get a specific task by ID."""
    return task_service.get_task(task_id)


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    update_data: dict,
    task_service: TaskService = Depends(get_task_service)
):
    """Update a task."""
    return task_service.update_task(task_id, update_data)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: str,
    task_service: TaskService = Depends(get_task_service)
):
    """Delete a task."""
    task_service.delete_task(task_id)
    return None


class PromoteWeekBody(BaseModel):
    task_ids: List[str]


@router.post("/promote-week")
def promote_week(
    body: PromoteWeekBody,
    task_service: TaskService = Depends(get_task_service)
):
    """Promote tasks to week status."""
    updated_ids = task_service.promote_tasks_to_week(body.task_ids)
    return {"updated": len(updated_ids), "ids": updated_ids}