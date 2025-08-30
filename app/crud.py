from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List, Optional
import uuid, time
from . import models, schemas

def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"

def get_or_create_tag(db: Session, name: str) -> models.Tag:
    tag = db.execute(select(models.Tag).where(models.Tag.name==name)).scalar_one_or_none()
    if tag:
        return tag
    tag = models.Tag(id=_gen_id("tag"), name=name)
    db.add(tag)
    db.flush()
    return tag

def create_task(db: Session, task_in: schemas.TaskCreate) -> models.Task:
    now_order = time.time()
    task = models.Task(
        id=_gen_id("task"),
        title=task_in.title,
        description=task_in.description,
        status=task_in.status or models.StatusEnum.backlog,
        size=task_in.size,
        effort_minutes=task_in.effort_minutes,
        hard_due_at=task_in.hard_due_at,
        soft_due_at=task_in.soft_due_at,
        energy=task_in.energy,
        project_id=task_in.project_id,
        goal_id=task_in.goal_id,
        sort_order=now_order if task_in.sort_order is None else task_in.sort_order,
    )
    db.add(task)
    if task_in.tags:
        tags = [get_or_create_tag(db, n) for n in task_in.tags]
        task.tags = tags
    db.flush()
    return task

def list_tasks(db: Session, status: Optional[List[str]] = None) -> List[models.Task]:
    query = db.query(models.Task)
    if status:
        query = query.filter(models.Task.status.in_(status))
    return query.order_by(models.Task.status, models.Task.sort_order.asc(), models.Task.created_at.asc()).all()

def update_task(db: Session, task: models.Task, data: dict) -> models.Task:
    for k, v in data.items():
        if v is None:
            continue
        if k == "tags":
            tags = [get_or_create_tag(db, n) for n in v]
            task.tags = tags
            continue
        else:
            setattr(task, k, v)
    db.flush()
    return task

def create_project(db: Session, project: schemas.ProjectCreate, id: str) -> models.Project:
    db_project = models.Project(**project.model_dump(), id=id)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def get_projects(db: Session, skip: int = 0, limit: int = 100) -> List[models.Project]:
    return db.query(models.Project).offset(skip).limit(limit).all()

def create_goal(db: Session, goal: schemas.GoalCreate, id: str) -> models.Goal:
    db_goal = models.Goal(**goal.model_dump(), id=id)
    db.add(db_goal)
    db.commit()
    db.refresh(db_goal)
    return db_goal

def get_goals(db: Session, skip: int = 0, limit: int = 100) -> List[models.Goal]:
    return db.query(models.Goal).offset(skip).limit(limit).all()
