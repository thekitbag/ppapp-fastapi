from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.db import get_db
from app import models, schemas
from app.api.v1.auth import get_current_user_dep
from app.repositories import TaskRepository
from app.services.recommendations import prioritize_tasks, suggest_week

router = APIRouter()


@router.get("/next", response_model=schemas.RecommendationResponse)
def next_recommendations(
    window: int = 30, 
    limit: int = 5, 
    energy: str = "high", 
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    db: Session = Depends(get_db),
):
    """Get next task recommendations."""
    user_id = current_user["user_id"]
    # Fetch candidate tasks
    tasks: List[models.Task] = (
        db.query(models.Task)
        .filter(models.Task.user_id == user_id)
        .filter(models.Task.status.in_(['backlog','doing','today', 'week']))
        .all()
    )
    ranked = prioritize_tasks(tasks, db=db)

    task_repo = TaskRepository(db)
    task_out_by_id = {
        task.id: task_out for task, task_out in zip(tasks, task_repo.to_schema_batch(tasks))
    }

    items: List[schemas.RecommendationItem] = []
    for r in ranked[: max(1, limit)]:  # always at least 1 if any task exists
        items.append(
            schemas.RecommendationItem(
                task=task_out_by_id[r.task.id],
                score=r.score,
                factors=r.factors,
                why=r.why,
            )
        )

    return schemas.RecommendationResponse(items=items)


class SuggestWeekBody(BaseModel):
    limit: int = 5


@router.post("/suggest-week", response_model=schemas.RecommendationResponse)
def suggest_week_api(
    body: SuggestWeekBody,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    db: Session = Depends(get_db),
):
    """Get week suggestions."""
    user_id = current_user["user_id"]
    tasks: List[models.Task] = (
        db.query(models.Task)
        .filter(models.Task.user_id == user_id)
        .filter(models.Task.status.in_(['backlog']))
        .all()
    )
    ranked = suggest_week(tasks, db=db, limit=body.limit)

    task_repo = TaskRepository(db)
    task_out_by_id = {
        task.id: task_out for task, task_out in zip(tasks, task_repo.to_schema_batch(tasks))
    }
    items = [
        schemas.RecommendationItem(task=task_out_by_id[r.task.id], score=r.score, factors=r.factors, why=r.why)
        for r in ranked
    ]
    return schemas.RecommendationResponse(items=items)
