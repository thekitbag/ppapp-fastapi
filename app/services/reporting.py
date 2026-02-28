from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from app.exceptions import NotFoundError
from app.schemas import GoalReportResponse, GoalGroupEntry, SummaryReportResponse
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

    def summary_report(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> SummaryReportResponse:
        # 1. Build ancestry and title maps for all user goals
        all_goals = self.db.query(Goal).filter(Goal.user_id == user_id).all()
        parent_map: dict = {g.id: g.parent_goal_id for g in all_goals}
        title_map: dict = {g.id: g.title for g in all_goals}

        def _find_root(goal_id: str) -> str:
            """Walk parent chain to find root goal id."""
            current = goal_id
            visited: set = set()
            while True:
                if current in visited:
                    # Cycle guard — treat current node as root
                    break
                visited.add(current)
                parent = parent_map.get(current)
                if not parent:
                    break
                current = parent
            return current

        # 2. Query qualifying tasks for the user in the date range
        tasks = (
            self.db.query(Task)
            .filter(
                Task.user_id == user_id,
                Task.completed_at.isnot(None),
                Task.size.isnot(None),
                Task.completed_at >= start_date,
                Task.completed_at <= end_date,
            )
            .all()
        )

        if not tasks:
            return SummaryReportResponse(
                start_date=start_date,
                end_date=end_date,
                impact_score=0,
                groups=[GoalGroupEntry(goal_id=None, goal_title="No Goal", total_size=0, is_no_goal=True)],
            )

        # 3. Build task_id → set(goal_id) from both link sources
        task_ids = [t.id for t in tasks]

        # Source A: TaskGoal rows — filter only by task ownership, NOT TaskGoal.user_id,
        # so that older rows with user_id=NULL are not silently dropped.
        tg_links = (
            self.db.query(TaskGoal.task_id, TaskGoal.goal_id)
            .filter(TaskGoal.task_id.in_(task_ids))
            .all()
        )
        task_goal_ids: dict = {}
        for tid, gid in tg_links:
            task_goal_ids.setdefault(tid, set()).add(gid)

        # Source B: legacy Task.goal_id field
        for task in tasks:
            if task.goal_id:
                task_goal_ids.setdefault(task.id, set()).add(task.goal_id)

        # Resolve goal_ids to roots; skip goals not owned by this user (isolation guard)
        task_roots: dict = {}
        for tid, goal_ids in task_goal_ids.items():
            for gid in goal_ids:
                if gid not in parent_map:
                    # Goal not in this user's goal set — discard to prevent leakage
                    continue
                root = _find_root(gid)
                task_roots.setdefault(tid, []).append(root)

        # 4. Accumulate sizes: each task assigned to one bucket (min root_id, deterministic)
        bucket_sizes: dict = {}   # root_id (or None) → total size

        for task in tasks:
            roots = task_roots.get(task.id)
            if roots:
                chosen_root = min(roots)   # deterministic: lexicographically smallest root
            else:
                chosen_root = None         # no-goal bucket
            bucket_sizes[chosen_root] = bucket_sizes.get(chosen_root, 0) + task.size

        # 5. Build groups — sort root goals by title, no-goal last
        groups: List[GoalGroupEntry] = []
        for root_id, total in sorted(
            ((k, v) for k, v in bucket_sizes.items() if k is not None),
            key=lambda kv: title_map.get(kv[0], ""),
        ):
            groups.append(GoalGroupEntry(
                goal_id=root_id,
                goal_title=title_map.get(root_id, root_id),
                total_size=total,
                is_no_goal=False,
            ))

        # Always include No Goal entry
        no_goal_size = bucket_sizes.get(None, 0)
        groups.append(GoalGroupEntry(goal_id=None, goal_title="No Goal", total_size=no_goal_size, is_no_goal=True))

        impact_score = sum(t.size for t in tasks if t.size is not None)

        return SummaryReportResponse(
            start_date=start_date,
            end_date=end_date,
            impact_score=impact_score,
            groups=groups,
        )
