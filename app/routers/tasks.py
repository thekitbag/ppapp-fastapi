from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

import time

from app.db import get_db, Base, engine
from app import models, schemas, crud

Base.metadata.create_all(bind=engine)

router = APIRouter()

def _build_task_out(task: models.Task, db: Session) -> schemas.TaskOut:
    """Helper function to build TaskOut with goals populated."""
    # Get all goals for this task
    task_goal_links = db.query(models.TaskGoal).filter(models.TaskGoal.task_id == task.id).all()
    goal_ids = [link.goal_id for link in task_goal_links]
    task_goals = []
    if goal_ids:
        task_goals = db.query(models.Goal).filter(models.Goal.id.in_(goal_ids)).all()
    
    return schemas.TaskOut(
        id=task.id,
        title=task.title,
        status=task.status.value,
        sort_order=task.sort_order,
        tags=[tag.name for tag in task.tags],
        effort_minutes=task.effort_minutes,
        hard_due_at=task.hard_due_at,
        soft_due_at=task.soft_due_at,
        project_id=task.project_id,
        goal_id=task.goal_id,  # Keep for backward compatibility
        goals=[schemas.GoalSummary(id=g.id, title=g.title) for g in task_goals],
        created_at=task.created_at,
        updated_at=task.updated_at
    )

@router.post("", response_model=schemas.TaskOut)
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    task = crud.create_task(db, payload)
    db.commit()
    return _build_task_out(task, db)

@router.get("", response_model=List[schemas.TaskOut])
def list_tasks(status: List[str] = Query(None), db: Session = Depends(get_db)):
    tasks = crud.list_tasks(db, status=status)
    return [_build_task_out(task, db) for task in tasks]

@router.patch("/{task_id}", response_model=schemas.TaskOut)
def patch_task(task_id: str, payload: schemas.TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id==task_id).one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    updated = crud.update_task(db, task, payload.model_dump(exclude_unset=True))
    db.commit()
    return _build_task_out(updated, db)

class PromoteWeekBody(BaseModel):
    task_ids: list[str]

@router.post("/promote-week")
def promote_week(body: PromoteWeekBody, db: Session = Depends(get_db)):
    q = db.query(models.Task).filter(models.Task.id.in_(body.task_ids))
    updated_ids = []
    for t in q.all():
        t.status = models.StatusEnum.week
        updated_ids.append(t.id)
    db.commit()
    return {"updated": len(updated_ids), "ids": updated_ids}
