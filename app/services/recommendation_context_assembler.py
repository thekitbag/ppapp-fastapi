"""
Recommendation context assembler (SUGGEST-004).

Builds a structured JSON-serialisable dict describing the user's current task
and goal landscape. This context is sent as the user message to the LLM.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app import models


class RecommendationContextAssembler:
    """
    Assembles a user-scoped context dict for the LLM recommendation call.

    user_id is used to load goals; task-goal links are loaded without a user_id
    filter to preserve rows that have a NULL user_id (hotfix pattern).
    """

    def __init__(self, db: Session, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def assemble(
        self,
        tasks: List[models.Task],
        energy: Optional[str],
        time_window: Optional[int],
    ) -> dict:
        """
        Build and return the context dict.

        Structure:
        {
          "user_state": {"energy": ..., "time_window": ...},
          "tasks": [ {...}, ... ],
          "goals": [ {...}, ... ],
        }
        """
        task_ids = [t.id for t in tasks]
        task_goal_map: dict[str, list[str]] = {}
        goal_map: dict[str, models.Goal] = {}
        goal_rows: list = []

        if self._db is not None:
            # Batch load TaskGoal rows (no user_id filter — preserves NULL rows)
            tg_rows = (
                self._db.query(models.TaskGoal)
                .filter(models.TaskGoal.task_id.in_(task_ids))
                .all()
            )
            for tg in tg_rows:
                task_goal_map.setdefault(tg.task_id, []).append(tg.goal_id)

            # Batch load all active user goals
            goal_rows = (
                self._db.query(models.Goal)
                .filter(
                    models.Goal.user_id == self._user_id,
                    models.Goal.is_archived == False,  # noqa: E712
                    models.Goal.is_closed == False,    # noqa: E712
                )
                .all()
            )
            goal_map = {g.id: g for g in goal_rows}

        # Build task summaries
        task_summaries = []
        for t in tasks:
            linked_goal_ids = task_goal_map.get(t.id, [])
            linked_goals = []
            for gid in linked_goal_ids:
                # Isolation guard: skip goal IDs that don't belong to this user
                goal = goal_map.get(gid)
                if goal is None:
                    continue
                linked_goals.append({
                    "id": goal.id,
                    "title": goal.title,
                    "status": _enum_str(goal.status),
                    "end_date": _dt_str(goal.end_date),
                    "type": _enum_str(goal.type),
                })

            task_summaries.append({
                "id": t.id,
                "title": t.title,
                "status": _enum_str(t.status),
                "size": t.size,
                "energy": _enum_str(t.energy),
                "hard_due_at": _dt_str(t.hard_due_at),
                "soft_due_at": _dt_str(t.soft_due_at),
                "project_id": t.project_id,
                "linked_goals": linked_goals,
            })

        # Build goal summaries (all active user goals, not just linked ones)
        goal_summaries = [
            {
                "id": g.id,
                "title": g.title,
                "type": _enum_str(g.type),
                "status": _enum_str(g.status),
                "end_date": _dt_str(g.end_date),
                "parent_goal_id": g.parent_goal_id,
            }
            for g in goal_rows
        ]

        return {
            "user_state": {
                "energy": energy,
                "time_window": time_window,
            },
            "tasks": task_summaries,
            "goals": goal_summaries,
        }


def _enum_str(value) -> Optional[str]:
    """Convert a SQLAlchemy enum value (or None) to its string representation."""
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _dt_str(value) -> Optional[str]:
    """Convert a datetime to ISO 8601 string, or None."""
    if value is None:
        return None
    return value.isoformat()
