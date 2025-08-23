# app/services/recommendations.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple

from app import models

# Day-2 deterministic formula (Ledders):
# +10 if status=todo
# +5 if due within 24h (hard_due_at or soft_due_at)
# +2 if has a "goal" tag
# Break ties by sort_order (ascending)
# Normalize to 0..100

MAX_RAW = 10 + 5 + 2  # 17

@dataclass
class Factor:
    status_boost: int = 0
    due_proximity: int = 0
    goal_align: int = 0

@dataclass
class Ranked:
    task: models.Task
    raw: int
    score: int
    factors: Dict[str, int]
    why: str

def _due_within_24h(task: models.Task, now: datetime) -> bool:
    due = task.hard_due_at or task.soft_due_at
    if not due:
        return False
    # ensure naive vs aware consistency
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due <= (now + timedelta(hours=24))

def _has_goal_tag(task: models.Task) -> bool:
    return any(t.name.lower() == "goal" for t in task.tags or [])

def _normalize(raw: int) -> int:
    if MAX_RAW == 0:
        return 0
    return int(round((raw / MAX_RAW) * 100))

def _why_from_factors(f: Factor) -> str:
    bits = []
    if f.due_proximity:
        bits.append("due soon")
    if f.goal_align:
        bits.append("aligned with a goal")

    trailing = []
    if f.status_boost:
        trailing.append("ready to start")

    # Nothing at all
    if not bits and not trailing:
        return "No strong signals (baseline order)"

    # If no main bits but we have trailing, just join trailing nicely
    if not bits and trailing:
        # e.g., "Ready to start"
        return ", ".join(t.capitalize() for t in trailing)

    # Build the main reasons from bits
    if len(bits) == 1:
        main = bits[0].capitalize()
    elif len(bits) == 2:
        main = f"{bits[0].capitalize()} and {bits[1]}"
    else:
        main = (", ".join(b.capitalize() for b in bits[:-1]) + f" and {bits[-1]}")

    # Add trailing secondary reasons with a semicolon
    if trailing:
        return f"{main}; " + ", ".join(trailing)
    return main



def prioritize_tasks(tasks: List[models.Task]) -> List[Ranked]:
    now = datetime.now(timezone.utc)
    ranked: List[Ranked] = []

    for t in tasks:
        f = Factor()
        if getattr(t.status, "value", str(t.status)) == "todo":
            f.status_boost = 1
        if _due_within_24h(t, now):
            f.due_proximity = 1
        if _has_goal_tag(t):
            f.goal_align = 1

        raw = (10 * f.status_boost) + (5 * f.due_proximity) + (2 * f.goal_align)
        score = _normalize(raw)
        ranked.append(
            Ranked(
                task=t,
                raw=raw,
                score=score,
                factors={
                    "status_boost": f.status_boost,
                    "due_proximity": f.due_proximity,
                    "goal_align": f.goal_align,
                },
                why=_why_from_factors(f),
            )
        )

    # primary: score desc; tie-breaker: sort_order asc; final: created_at asc (stable)
    ranked.sort(key=lambda r: (-r.score, r.task.sort_order, r.task.created_at))
    return ranked
