from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.exceptions import NotFoundError
from app.schemas import GoalReportResponse
from app.models import Goal, Task, TaskGoal
from .base import BaseService


class ReportingService(BaseService):

    def goal_progress_report(
        self,
        goal_id: str,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> GoalReportResponse:
        # 1. Verify goal exists and belongs to user
        goal = self.db.query(Goal).filter(
            Goal.id == goal_id, Goal.user_id == user_id
        ).first()
        if not goal:
            raise NotFoundError("Goal", goal_id)

        # 2. BFS to collect descendant goal IDs (excludes root)
        all_goals = self.db.query(Goal).filter(Goal.user_id == user_id).all()
        children_map: dict = {}
        for g in all_goals:
            children_map.setdefault(g.parent_goal_id, []).append(g.id)

        descendant_ids: list = []
        queue = list(children_map.get(goal_id, []))
        while queue:
            current = queue.pop()
            descendant_ids.append(current)
            queue.extend(children_map.get(current, []))

        # 3. Sum tasks for a list of goal IDs, skipping already-seen task IDs
        def _sum_tasks(goal_ids: list, exclude_task_ids: set) -> tuple:
            if not goal_ids:
                return 0, set()
            q = (
                self.db.query(Task.id, Task.size)
                .join(TaskGoal, TaskGoal.task_id == Task.id)
                .filter(
                    TaskGoal.goal_id.in_(goal_ids),
                    TaskGoal.user_id == user_id,
                    Task.user_id == user_id,
                    Task.completed_at.isnot(None),
                    Task.size.isnot(None),
                )
            )
            if start_date:
                q = q.filter(Task.completed_at >= start_date)
            if end_date:
                q = q.filter(Task.completed_at <= end_date)
            seen: set = set()
            total = 0
            for task_id, size in q.all():
                if task_id not in seen and task_id not in exclude_task_ids:
                    seen.add(task_id)
                    total += size
            return total, seen

        direct_size, direct_ids = _sum_tasks([goal_id], set())
        descendant_size, _ = _sum_tasks(descendant_ids, direct_ids)

        return GoalReportResponse(
            goal_id=goal_id,
            goal_title=goal.title,
            total_size=direct_size + descendant_size,
            direct_size=direct_size,
            descendant_size=descendant_size,
            start_date=start_date,
            end_date=end_date,
        )
