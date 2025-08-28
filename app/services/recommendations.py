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

def _max_raw(weights: dict) -> int:
    # weights example: {'status_boost':10, 'due_proximity':5, 'goal_align':2}
    return sum(weights.values())


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

def _due_within_hours(task: models.Task, now: datetime, hours: int) -> bool:
    due = task.hard_due_at or task.soft_due_at
    if not due:
        return False
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due <= (now + timedelta(hours=hours))



def prioritize_tasks(
    tasks: List[models.Task],
    *,
    due_within_hours: int = 24,
    weights: Dict[str, int] = None,
) -> List[Ranked]:
    if weights is None:
        weights = {'status_boost': 10, 'due_proximity': 5, 'goal_align': 2}  # Day-2 defaults
    now = datetime.now(timezone.utc)
    ranked: List[Ranked] = []
    max_raw = _max_raw(weights) or 1

    for t in tasks:
        f = Factor()
        if getattr(t.status, "value", str(t.status)) == "todo":
            f.status_boost = 1
        if _due_within_24h(t, now) if due_within_hours == 24 else _due_within_hours(t, now, due_within_hours):
            f.due_proximity = 1
        if _has_goal_tag(t):
            f.goal_align = 1

        raw = (weights['status_boost'] * f.status_boost) + \
              (weights['due_proximity'] * f.due_proximity) + \
              (weights['goal_align'] * f.goal_align)
        score = int(round((raw / max_raw) * 100))
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

    ranked.sort(key=lambda r: (-r.score, r.task.sort_order, r.task.created_at))
    return ranked

def suggest_week(tasks: List[models.Task], limit: int = 5) -> List[Ranked]:
    # Day-3 tweak: due within 7 days, same other weights for now
    ranked = prioritize_tasks(
        tasks,
        due_within_hours=7*24,
        weights={'status_boost': 10, 'due_proximity': 5, 'goal_align': 2}
    )
    return ranked[:max(1, min(limit, 5))]
