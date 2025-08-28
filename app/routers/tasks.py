
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

import time

from app.db import SessionLocal, engine, Base
from app import models, schemas, crud

Base.metadata.create_all(bind=engine)

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("", response_model=schemas.TaskOut)
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    task = crud.create_task(db, title=payload.title, tag_names=payload.tags or [])
    db.commit()
    return schemas.TaskOut(
        id=task.id, title=task.title, status=task.status.value, sort_order=task.sort_order,
        tags=[t.name for t in task.tags], effort_minutes=task.effort_minutes,
        hard_due_at=task.hard_due_at, soft_due_at=task.soft_due_at,
        created_at=task.created_at, updated_at=task.updated_at 

    )

@router.get("", response_model=List[schemas.TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    tasks = crud.list_tasks(db)
    return [
        schemas.TaskOut(
            id=t.id, title=t.title, status=t.status.value, sort_order=t.sort_order,
            tags=[tag.name for tag in t.tags], effort_minutes=t.effort_minutes,
            hard_due_at=t.hard_due_at, soft_due_at=t.soft_due_at,
            created_at=t.created_at, updated_at=t.updated_at
        ) for t in tasks
    ]

@router.patch("/{task_id}", response_model=schemas.TaskOut)
def patch_task(task_id: str, payload: schemas.TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id==task_id).one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    updated = crud.update_task(db, task, payload.model_dump(exclude_unset=True))
    db.commit()
    return schemas.TaskOut(
        id=updated.id, title=updated.title, status=updated.status.value, sort_order=updated.sort_order,
        tags=[tag.name for tag in updated.tags], effort_minutes=updated.effort_minutes,
        hard_due_at=updated.hard_due_at, soft_due_at=updated.soft_due_at,
        created_at=task.created_at, updated_at=task.updated_at 

    )

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

