from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
from app.db import SessionLocal
from app import models, schemas
from app.services.recommendations import prioritize_tasks, suggest_week

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/next", response_model=schemas.RecommendationResponse)
def next_recommendations(window: int = 30, limit: int = 5, energy: str = "high", db: Session = Depends(get_db)):
    # Fetch candidate tasks (for Day-2, consider non-done)
    tasks: List[models.Task] = (
        db.query(models.Task)
        .filter(models.Task.status.in_(['backlog','doing','today', 'week']))
        .all()
    )
    ranked = prioritize_tasks(tasks, db=db)

    items: List[schemas.RecommendationItem] = []
    for r in ranked[: max(1, limit)]:  # always at least 1 if any task exists
        items.append(
            schemas.RecommendationItem(
                task=schemas.TaskOut(
                    id=r.task.id,
                    title=r.task.title,
                    status=r.task.status.value,
                    sort_order=r.task.sort_order,
                    tags=[tag.name for tag in r.task.tags],
                    effort_minutes=r.task.effort_minutes,
                    hard_due_at=r.task.hard_due_at,
                    soft_due_at=r.task.soft_due_at,
                    project_id=r.task.project_id,
                    goal_id=r.task.goal_id,
                    created_at=r.task.created_at,
                    updated_at=r.task.updated_at,
                ),
                score=r.score,
                factors=r.factors,
                why=r.why,
            )
        )

    return schemas.RecommendationResponse(items=items)

class SuggestWeekBody(BaseModel):
    limit: int = 5

@router.post("/suggest-week", response_model=schemas.RecommendationResponse)
def suggest_week_api(body: SuggestWeekBody, db: Session = Depends(get_db)):
    tasks: List[models.Task] = (
        db.query(models.Task)
        .filter(models.Task.status.in_(['backlog']))
        .all()
    )
    ranked = suggest_week(tasks, db=db, limit=body.limit)
    items = [
        schemas.RecommendationItem(
            task=schemas.TaskOut(
                id=r.task.id,
                title=r.task.title,
                status=r.task.status.value,
                sort_order=r.task.sort_order,
                tags=[tag.name for tag in r.task.tags],
                effort_minutes=r.task.effort_minutes,
                hard_due_at=r.task.hard_due_at,
                soft_due_at=r.task.soft_due_at,
                project_id=r.task.project_id,
                goal_id=r.task.goal_id,
                created_at=r.task.created_at,
                updated_at=r.task.updated_at,
            ),
            score=r.score,
            factors=r.factors,
            why=r.why,
        )
        for r in ranked
    ]
    return schemas.RecommendationResponse(items=items)
