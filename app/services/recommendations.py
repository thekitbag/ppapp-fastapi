# app/services/recommendations.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
import math
from sqlalchemy.orm import Session

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
    project_due_proximity: float = 0.0
    goal_linked: int = 0

@dataclass
class Ranked:
    task: models.Task
    raw: float
    score: float
    factors: Dict[str, float]
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

def _why_from_factors(f: Factor, project: models.Project = None, days_until_project_due: int = 0, goal_titles: List[str] = None) -> str:
    bits = []
    if f.due_proximity:
        bits.append("due soon")
    if f.goal_align:
        bits.append("aligned with a goal")
    if f.project_due_proximity > 0.3 and project and project.milestone_title:
        if days_until_project_due <= 1:
            bits.append(f"Project {project.name} milestone in 1 day")
        else:
            bits.append(f"Project {project.name} milestone in {days_until_project_due} days")
    
    if f.goal_linked and goal_titles:
        if len(goal_titles) == 1:
            bits.append(f"Linked to goal '{goal_titles[0]}'")
        else:
            bits.append(f"Linked to {len(goal_titles)} goals")

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


def _calculate_project_due_proximity(project: models.Project, now: datetime) -> Tuple[float, int]:
    """
    Calculate project milestone proximity score and days until due.
    Returns (score, days_until_due) where score is 0-1 and days_until_due is positive integer.
    """
    if not project or not project.milestone_due_at:
        return 0.0, 0
    
    milestone_due = project.milestone_due_at
    # Treat naive datetime as UTC (not local time)
    if milestone_due.tzinfo is None:
        milestone_due = milestone_due.replace(tzinfo=timezone.utc)
    
    # If milestone is in the past, set score to 0
    if milestone_due <= now:
        return 0.0, 0
    
    days_delta = (milestone_due - now).days
    
    # Use sigmoid curve: score = 1 / (1 + exp((days - 7) / 2.0))
    # This gives ~0.88 at 1 day, ~0.5 at 7 days, ~0.12 at 14 days
    score = 1 / (1 + math.exp((days_delta - 7) / 2.0))
    
    return score, days_delta



def prioritize_tasks(
    tasks: List[models.Task],
    db: Session = None,
    *,
    due_within_hours: int = 24,
    weights: Dict[str, float] = None,
) -> List[Ranked]:
    if weights is None:
        weights = {'status_boost': 10, 'due_proximity': 5, 'goal_align': 2, 'project_due_proximity': 0.12, 'goal_linked': 0.10}
    
    now = datetime.now(timezone.utc)
    ranked: List[Ranked] = []
    
    # Fetch projects in batch to avoid N+1 queries
    project_ids = list({t.project_id for t in tasks if t.project_id})
    projects_dict = {}
    if db and project_ids:
        projects = db.query(models.Project).filter(models.Project.id.in_(project_ids)).all()
        projects_dict = {p.id: p for p in projects}
    
    # Fetch task-goal links in batch to avoid N+1 queries
    task_ids = [t.id for t in tasks]
    task_goals_dict = {}
    if db and task_ids:
        from app.models import TaskGoal  # Import here to avoid circular imports
        task_goal_links = db.query(TaskGoal).filter(TaskGoal.task_id.in_(task_ids)).all()
        
        # Group by task_id
        for link in task_goal_links:
            if link.task_id not in task_goals_dict:
                task_goals_dict[link.task_id] = []
            task_goals_dict[link.task_id].append(link.goal_id)
        
        # Fetch goals for explanations
        goal_ids = list({goal_id for goal_list in task_goals_dict.values() for goal_id in goal_list})
        goals_dict = {}
        if goal_ids:
            goals = db.query(models.Goal).filter(models.Goal.id.in_(goal_ids)).all()
            goals_dict = {g.id: g for g in goals}
    
    # Calculate max possible raw score
    max_raw = sum(weights.values())
    if max_raw == 0:
        max_raw = 1

    for t in tasks:
        f = Factor()
        project = projects_dict.get(t.project_id) if t.project_id else None
        days_until_project_due = 0
        
        # Get linked goals for this task
        linked_goal_ids = task_goals_dict.get(t.id, [])
        linked_goals = [goals_dict.get(goal_id) for goal_id in linked_goal_ids if goal_id in goals_dict] if db else []
        goal_titles = [g.title for g in linked_goals if g]
        
        # Status boost
        if getattr(t.status, "value", str(t.status)) == "todo":
            f.status_boost = 1
        
        # Due proximity
        if _due_within_24h(t, now) if due_within_hours == 24 else _due_within_hours(t, now, due_within_hours):
            f.due_proximity = 1
        
        # Goal alignment
        if _has_goal_tag(t):
            f.goal_align = 1
        
        # Project due proximity
        if project:
            f.project_due_proximity, days_until_project_due = _calculate_project_due_proximity(project, now)
        
        # Goal linked factor
        if len(linked_goal_ids) > 0:
            f.goal_linked = 1
        
        # Calculate weighted raw score
        raw = (weights['status_boost'] * f.status_boost) + \
              (weights['due_proximity'] * f.due_proximity) + \
              (weights['goal_align'] * f.goal_align) + \
              (weights['project_due_proximity'] * f.project_due_proximity) + \
              (weights['goal_linked'] * f.goal_linked)
        
        score = (raw / max_raw) * 100
        
        ranked.append(
            Ranked(
                task=t,
                raw=raw,
                score=score,
                factors={
                    "status_boost": float(f.status_boost),
                    "due_proximity": float(f.due_proximity),
                    "goal_align": float(f.goal_align),
                    "project_due_proximity": f.project_due_proximity,
                    "goal_linked": float(f.goal_linked),
                },
                why=_why_from_factors(f, project, days_until_project_due, goal_titles),
            )
        )

    ranked.sort(key=lambda r: (-r.score, (r.task.sort_order or 0.0), r.task.created_at))
    return ranked

def suggest_week(tasks: List[models.Task], db: Session = None, limit: int = 5) -> List[Ranked]:
    # Day-3 tweak: due within 7 days, same other weights for now
    ranked = prioritize_tasks(
        tasks,
        db=db,
        due_within_hours=7*24,
        weights={'status_boost': 10, 'due_proximity': 5, 'goal_align': 2, 'project_due_proximity': 0.12, 'goal_linked': 0.10}
    )
    return ranked[:limit]
