from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from app.db import get_db
from app import models, schemas
from app.api.v1.auth import get_current_user_dep
from app.repositories import TaskRepository
from app.services.recommendations import suggest_week
from app.services.recommendation_engine import RecommendationContext, get_recommendation_engine
from app.core.config import settings

router = APIRouter()

_VALID_ENERGIES = {"low", "medium", "high"}
_VALID_TIME_WINDOWS = {15, 30, 60, 120, 240}


def _parse_next_query(
    energy: Optional[str] = Query(None, description="Current energy level (low, medium, or high); influences task-size preference in ranking"),
    time_window: Optional[int] = Query(None, description="Available time in minutes; must be one of 15, 30, 60, 120, 240"),
    limit: int = Query(5),
    window: int = Query(30, deprecated=True, description="Deprecated: use time_window instead"),
) -> schemas.NextRecommendationQuery:
    if energy is not None and energy not in _VALID_ENERGIES:
        raise HTTPException(status_code=422, detail=f"energy must be one of {sorted(_VALID_ENERGIES)}")
    if time_window is not None and time_window not in _VALID_TIME_WINDOWS:
        raise HTTPException(status_code=422, detail=f"time_window must be one of {sorted(_VALID_TIME_WINDOWS)}")
    return schemas.NextRecommendationQuery(energy=energy, time_window=time_window, limit=limit, window=window)


def _get_engine():
    """Dependency: return the active recommendation engine based on config."""
    return get_recommendation_engine(settings.use_llm_prioritization)


@router.get("/next", response_model=schemas.RecommendationResponse)
def next_recommendations(
    query: schemas.NextRecommendationQuery = Depends(_parse_next_query),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    db: Session = Depends(get_db),
    engine=Depends(_get_engine),
):
    """Get next task recommendations with optional energy and time_window filtering."""
    user_id = current_user["user_id"]
    tasks: List[models.Task] = (
        db.query(models.Task)
        .filter(models.Task.user_id == user_id)
        .filter(models.Task.status.in_(['backlog', 'doing', 'today', 'week']))
        .all()
    )

    ctx = RecommendationContext(
        tasks=tasks,
        db=db,
        energy=query.energy,
        time_window=query.time_window,
        limit=query.limit,
    )
    ranked = engine.recommend(ctx)

    task_repo = TaskRepository(db)
    task_out_by_id = {
        task.id: task_out for task, task_out in zip(tasks, task_repo.to_schema_batch(tasks))
    }

    items: List[schemas.RecommendationItem] = [
        schemas.RecommendationItem(
            task=task_out_by_id[r.task.id],
            score=r.score,
            factors=r.factors,
            why=r.why,
        )
        for r in ranked
    ]

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
