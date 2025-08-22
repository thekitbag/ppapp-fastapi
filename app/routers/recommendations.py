
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Dict
from datetime import datetime
from app.db import SessionLocal
from app import models, schemas

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/next", response_model=schemas.RecommendationResponse)
def next_recommendations(window: int = 30, limit: int = 5, energy: str = "high", db: Session = Depends(get_db)):
    # Deterministic sort per Ledders: status (todo/doing first), then hard_due_at/soft_due_at, then sort_order.
    status_rank = { "todo": 0, "doing": 0, "inbox": 1, "done": 2 }
    tasks: List[models.Task] = db.query(models.Task).all()
    def due_key(t):
        d = t.hard_due_at or t.soft_due_at
        return d or datetime.max
    ranked = sorted(tasks, key=lambda t: (status_rank.get(t.status.value, 9), due_key(t), t.sort_order))
    items = []
    for t in ranked[:limit]:
        time_fit = 0
        if t.effort_minutes and window:
            # simplistic: 1.0 if fits, else 0
            time_fit = 1.0 if t.effort_minutes <= window else 0.0
        factors = {k: 0 for k in ["goal_align","urgency","due_date","energy_fit","time_fit","context_cost","size_fit","recent_neglect"]}
        factors["time_fit"] = time_fit
        items.append({
            "task": {
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "sort_order": t.sort_order,
                "tags": [tag.name for tag in t.tags],
                "effort_minutes": t.effort_minutes,
                "hard_due_at": t.hard_due_at,
                "soft_due_at": t.soft_due_at
            },
            "score": 50.0 + (10.0 * time_fit),
            "factors": factors
        })
    return {"items": items}
