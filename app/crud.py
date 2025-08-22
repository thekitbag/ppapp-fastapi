
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List
import uuid, time
from . import models

def _gen_id() -> str:
    return str(uuid.uuid4())

def get_or_create_tag(db: Session, name: str) -> models.Tag:
    tag = db.execute(select(models.Tag).where(models.Tag.name==name)).scalar_one_or_none()
    if tag:
        return tag
    tag = models.Tag(id=_gen_id(), name=name)
    db.add(tag)
    db.flush()
    return tag

def create_task(db: Session, title: str, tag_names: List[str]) -> models.Task:
    now_order = time.time()
    task = models.Task(id=_gen_id(), title=title, sort_order=now_order)
    db.add(task)
    tags = [get_or_create_tag(db, n) for n in tag_names]
    task.tags = tags
    db.flush()
    return task

def list_tasks(db: Session) -> List[models.Task]:
    return db.query(models.Task).order_by(models.Task.sort_order.asc()).all()

def update_task(db: Session, task: models.Task, data: dict) -> models.Task:
    for k, v in data.items():
        if v is None: 
            continue
        if k == "tags":
            tags = [get_or_create_tag(db, n) for n in v]
            task.tags = tags
        else:
            setattr(task, k, v)
    db.flush()
    return task
