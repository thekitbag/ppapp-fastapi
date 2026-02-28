# app/services/recommendations.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional
import math
from sqlalchemy.orm import Session

from app import models

# SUGGEST-002 scoring weights (see docs/recommendations-logic.md for full spec)
# status_boost:             +10   task.status == today
# due_proximity:            +5    task due within horizon
# goal_align:               +2    task has "goal" tag
# project_due_proximity:    +0.12 sigmoid from project milestone date
# goal_linked:              +0.10 task linked to any goal
# energy_match:             +20   task.energy matches user energy (0 when param absent)
# time_fit:                 +15   task.size fits Fibonacci effort band (0 when param absent)
# goal_status_at_risk:      +10   always active; best linked goal is at_risk
# goal_status_off_target:   +15   always active; any linked goal is off_target (exclusive)
# goal_urgency:             +10   always active; sigmoid score from nearest goal end_date


def _max_raw(weights: dict) -> int:
    return sum(weights.values())


# Maps user-facing energy level → acceptable task.energy enum values
_ENERGY_TASK_MAP: Dict[str, set] = {
    "low":    {"low", "tired"},
    "medium": {"medium", "neutral"},
    "high":   {"high", "energized"},
}

_ENERGY_LEVELS = set(_ENERGY_TASK_MAP.keys())

# Fibonacci effort-band fit: time_window (minutes) → max task size that fits
# Policy: task.size is Fibonacci effort points; size=None → no boost (unknown effort)
_TIME_WINDOW_SIZE_THRESHOLD: Dict[int, int] = {15: 1, 30: 2, 60: 3, 120: 5, 240: 8}

# Goal status raw boost values
_GOAL_STATUS_BOOST_MAP: Dict[str, float] = {"at_risk": 10.0, "off_target": 15.0}


@dataclass
class Factor:
    status_boost: int = 0
    due_proximity: int = 0
    goal_align: int = 0
    project_due_proximity: float = 0.0
    goal_linked: int = 0
    energy_match: int = 0          # 1 if task.energy matches user energy; weight: 20
    time_fit: int = 0              # 1 if task.size fits time_window band; weight: 15
    goal_status_at_risk: int = 0   # 1 if best linked goal is at_risk (no off_target); weight: 10
    goal_status_off_target: int = 0  # 1 if any linked goal is off_target; weight: 15
    goal_urgency: float = 0.0     # 0-1 sigmoid from nearest goal end_date; weight: 10


@dataclass
class Ranked:
    task: models.Task
    raw: float
    score: float
    factors: Dict[str, float]
    why: str


def _due_within_24h(task, now: datetime) -> bool:
    due = task.hard_due_at or task.soft_due_at
    if not due:
        return False
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due <= (now + timedelta(hours=24))


def _has_goal_tag(task) -> bool:
    return any(t.name.lower() == "goal" for t in task.tags or [])


def _due_within_hours(task, now: datetime, hours: int) -> bool:
    due = task.hard_due_at or task.soft_due_at
    if not due:
        return False
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due <= (now + timedelta(hours=hours))


def _calculate_project_due_proximity(project, now: datetime) -> Tuple[float, int]:
    """
    Calculate project milestone proximity score and days until due.
    Returns (score, days_until_due) where score is 0-1 and days_until_due is positive integer.
    Uses sigmoid: ~0.88 at 1 day, ~0.5 at 7 days, ~0.12 at 14 days.
    """
    if not project or not project.milestone_due_at:
        return 0.0, 0

    milestone_due = project.milestone_due_at
    if milestone_due.tzinfo is None:
        milestone_due = milestone_due.replace(tzinfo=timezone.utc)

    if milestone_due <= now:
        return 0.0, 0

    days_delta = (milestone_due - now).days
    score = 1 / (1 + math.exp((days_delta - 7) / 2.0))
    return score, days_delta


def _goal_status_raw(goal) -> float:
    """Return the raw status boost for a single goal (0.0, 10.0, or 15.0)."""
    status = getattr(goal, "status", None)
    if status is None:
        return 0.0
    status_str = status.value if hasattr(status, "value") else str(status)
    return _GOAL_STATUS_BOOST_MAP.get(status_str, 0.0)


def _calculate_goal_urgency(goal, now: datetime) -> float:
    """
    Sigmoid urgency score based on goal.end_date.
    Returns 0-1: ~0.97 at 1 day, ~0.5 at 14 days, ~0.03 at 28 days.
    Returns 0.0 if goal has no end_date or end_date is in the past.
    """
    end_date = getattr(goal, "end_date", None)
    if not end_date:
        return 0.0
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    if end_date <= now:
        return 0.0
    days_delta = (end_date - now).days
    return 1 / (1 + math.exp((days_delta - 14) / 3.0))


def _why_from_factors(
    f: Factor,
    project=None,
    days_until_project_due: int = 0,
    goal_titles: List[str] = None,
    energy: Optional[str] = None,
    time_window: Optional[int] = None,
    days_until_goal_due: int = 0,
) -> str:
    bits = []

    # Energy and time fit — surface first as most actionable for user
    if f.energy_match and energy:
        bits.append(f"matches your {energy} energy level")
    if f.time_fit and time_window:
        bits.append(f"fits your {time_window}m window")

    if f.due_proximity:
        bits.append("due soon")
    if f.goal_align:
        bits.append("aligned with a goal")
    if f.project_due_proximity > 0.3 and project and project.milestone_title:
        if days_until_project_due <= 1:
            bits.append(f"Project {project.name} milestone in 1 day")
        else:
            bits.append(f"Project {project.name} milestone in {days_until_project_due} days")

    # Goal health
    if f.goal_status_off_target:
        bits.append("linked goal is off target")
    elif f.goal_status_at_risk:
        bits.append("linked goal is at risk")
    if f.goal_urgency > 0.5:
        if days_until_goal_due > 0:
            bits.append(f"goal due in {days_until_goal_due} days")
        else:
            bits.append("goal due soon")

    # Show linked goal title only when no status signals already mention the link
    if f.goal_linked and goal_titles and not (f.goal_status_at_risk or f.goal_status_off_target):
        if len(goal_titles) == 1:
            bits.append(f"Linked to goal '{goal_titles[0]}'")
        else:
            bits.append(f"Linked to {len(goal_titles)} goals")

    trailing = []
    if f.status_boost:
        trailing.append("ready to start")

    if not bits and not trailing:
        return "No strong signals (baseline order)"

    if not bits and trailing:
        return ", ".join(t.capitalize() for t in trailing)

    if len(bits) == 1:
        main = bits[0].capitalize()
    elif len(bits) == 2:
        main = f"{bits[0].capitalize()} and {bits[1]}"
    else:
        main = ", ".join(b.capitalize() for b in bits[:-1]) + f" and {bits[-1]}"

    if trailing:
        return f"{main}; " + ", ".join(trailing)
    return main


def prioritize_tasks(
    tasks: List[models.Task],
    db: Session = None,
    *,
    due_within_hours: int = 24,
    weights: Dict[str, float] = None,
    energy: Optional[str] = None,
    time_window: Optional[int] = None,
) -> List[Ranked]:
    if weights is None:
        weights = {
            'status_boost': 10,
            'due_proximity': 5,
            'goal_align': 2,
            'project_due_proximity': 0.12,
            'goal_linked': 0.10,
            'energy_match': 0,           # activated (+20) when energy param provided
            'time_fit': 0,               # activated (+15) when time_window param provided
            'goal_status_at_risk': 10,
            'goal_status_off_target': 15,
            'goal_urgency': 10,
        }
    else:
        weights.setdefault('energy_match', 0)
        weights.setdefault('time_fit', 0)
        weights.setdefault('goal_status_at_risk', 10)
        weights.setdefault('goal_status_off_target', 15)
        weights.setdefault('goal_urgency', 10)

    if energy in _ENERGY_LEVELS:
        weights['energy_match'] = 20

    if time_window is not None:
        weights['time_fit'] = 15

    now = datetime.now(timezone.utc)
    ranked: List[Ranked] = []

    user_ids = {t.user_id for t in tasks if getattr(t, "user_id", None)}

    # Batch-fetch projects (avoid N+1)
    project_ids = list({t.project_id for t in tasks if t.project_id})
    projects_dict = {}
    if db and project_ids:
        projects_query = db.query(models.Project).filter(models.Project.id.in_(project_ids))
        if user_ids:
            projects_query = projects_query.filter(models.Project.user_id.in_(user_ids))
        projects_dict = {p.id: p for p in projects_query.all()}

    # Batch-fetch task-goal links then goals (status + end_date included; avoid N+1)
    task_ids = [t.id for t in tasks]
    task_goals_dict: Dict[str, List[str]] = {}
    goals_dict: Dict[str, object] = {}
    if db and task_ids:
        from app.models import TaskGoal
        tg_query = db.query(TaskGoal).filter(TaskGoal.task_id.in_(task_ids))
        if user_ids:
            tg_query = tg_query.filter(TaskGoal.user_id.in_(user_ids))
        for link in tg_query.all():
            task_goals_dict.setdefault(link.task_id, []).append(link.goal_id)

        goal_ids = list({gid for gids in task_goals_dict.values() for gid in gids})
        if goal_ids:
            goals_query = db.query(models.Goal).filter(models.Goal.id.in_(goal_ids))
            if user_ids:
                goals_query = goals_query.filter(models.Goal.user_id.in_(user_ids))
            goals_dict = {g.id: g for g in goals_query.all()}

    max_raw = sum(weights.values())
    if max_raw == 0:
        max_raw = 1

    for t in tasks:
        f = Factor()
        project = projects_dict.get(t.project_id) if t.project_id else None
        days_until_project_due = 0

        linked_goal_ids = task_goals_dict.get(t.id, [])
        linked_goals = [goals_dict[gid] for gid in linked_goal_ids if gid in goals_dict] if db else []
        goal_titles = [g.title for g in linked_goals if g]

        # Status boost
        if getattr(t.status, "value", str(t.status)) == "today":
            f.status_boost = 1

        # Due proximity
        if _due_within_24h(t, now) if due_within_hours == 24 else _due_within_hours(t, now, due_within_hours):
            f.due_proximity = 1

        # Goal alignment (tag-based)
        if _has_goal_tag(t):
            f.goal_align = 1

        # Project due proximity
        if project:
            f.project_due_proximity, days_until_project_due = _calculate_project_due_proximity(project, now)

        # Goal linked
        if linked_goal_ids:
            f.goal_linked = 1

        # Energy match: compare task.energy field against user energy param.
        # Fallback policy: task.energy=None → no boost (unknown energy requirement).
        if energy in _ENERGY_TASK_MAP:
            task_energy = getattr(t, "energy", None)
            if task_energy is not None:
                task_energy_str = task_energy.value if hasattr(task_energy, "value") else str(task_energy)
                if task_energy_str in _ENERGY_TASK_MAP[energy]:
                    f.energy_match = 1

        # Time fit: task.size must be within the Fibonacci effort band for time_window.
        # Fallback policy: task.size=None → no boost (unknown effort).
        if time_window is not None:
            size = getattr(t, "size", None)
            if size is not None:
                size_threshold = _TIME_WINDOW_SIZE_THRESHOLD.get(time_window, 999)
                if size <= size_threshold:
                    f.time_fit = 1

        # Goal health: take max status boost across linked goals (off_target takes priority
        # over at_risk to prevent double-counting inflation on multi-goal tasks).
        days_until_goal_due = 0
        if linked_goals:
            max_status_raw = max((_goal_status_raw(g) for g in linked_goals if g), default=0.0)
            if max_status_raw >= 15.0:
                f.goal_status_off_target = 1
            elif max_status_raw >= 10.0:
                f.goal_status_at_risk = 1

            # Urgency: nearest-expiring linked goal drives the sigmoid score
            best_urgency = 0.0
            for g in linked_goals:
                if not g:
                    continue
                u = _calculate_goal_urgency(g, now)
                if u > best_urgency:
                    best_urgency = u
                    end_date = getattr(g, "end_date", None)
                    if end_date:
                        if end_date.tzinfo is None:
                            end_date = end_date.replace(tzinfo=timezone.utc)
                        days_until_goal_due = max(0, (end_date - now).days)
            f.goal_urgency = best_urgency

        raw = (
            weights['status_boost'] * f.status_boost
            + weights['due_proximity'] * f.due_proximity
            + weights['goal_align'] * f.goal_align
            + weights['project_due_proximity'] * f.project_due_proximity
            + weights['goal_linked'] * f.goal_linked
            + weights['energy_match'] * f.energy_match
            + weights['time_fit'] * f.time_fit
            + weights['goal_status_at_risk'] * f.goal_status_at_risk
            + weights['goal_status_off_target'] * f.goal_status_off_target
            + weights['goal_urgency'] * f.goal_urgency
        )

        score = (raw / max_raw) * 100

        ranked.append(Ranked(
            task=t,
            raw=raw,
            score=score,
            factors={
                "status_boost": float(f.status_boost),
                "due_proximity": float(f.due_proximity),
                "goal_align": float(f.goal_align),
                "project_due_proximity": f.project_due_proximity,
                "goal_linked": float(f.goal_linked),
                "energy_match": float(f.energy_match),
                "time_fit": float(f.time_fit),
                "goal_status_at_risk": float(f.goal_status_at_risk),
                "goal_status_off_target": float(f.goal_status_off_target),
                "goal_urgency": f.goal_urgency,
            },
            why=_why_from_factors(
                f, project, days_until_project_due, goal_titles,
                energy=energy, time_window=time_window,
                days_until_goal_due=days_until_goal_due,
            ),
        ))

    ranked.sort(key=lambda r: (-r.score, (r.task.sort_order or 0.0), r.task.created_at))
    return ranked


def suggest_week(tasks: List[models.Task], db: Session = None, limit: int = 5) -> List[Ranked]:
    ranked = prioritize_tasks(
        tasks,
        db=db,
        due_within_hours=7 * 24,
        weights={
            'status_boost': 10, 'due_proximity': 5, 'goal_align': 2,
            'project_due_proximity': 0.12, 'goal_linked': 0.10,
            'energy_match': 0, 'time_fit': 0,
            'goal_status_at_risk': 10, 'goal_status_off_target': 15, 'goal_urgency': 10,
        },
    )
    return ranked[:limit]
