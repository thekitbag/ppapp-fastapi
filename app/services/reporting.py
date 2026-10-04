from typing import Optional, List
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from app.exceptions import NotFoundError, ValidationError
from app.schemas import (
    GoalReportResponse,
    GoalGroupEntry,
    SummaryReportResponse,
    BreakdownRow,
    BreakdownReportResponse,
    TrendBucket,
    TrendSeries,
    TrendStats,
    TrendsReportResponse,
)
from app.models import Goal, Task, TaskGoal
from .base import BaseService

BUCKET_GRANULARITIES = ("day", "week", "month")

# Guard against a request like "one year, by day" blowing up the payload and the
# chart. The frontend picks a granularity to fit the range; this is the backstop.
MAX_TREND_BUCKETS = 400

_MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


@dataclass
class _Attribution:
    """Result of resolving a period's completed tasks onto goal rows."""
    goal_map: dict
    children_map: dict
    ordered_row_ids: List[str]
    attributions: List[tuple] = field(default_factory=list)  # (Task, row_id | None)
    is_root_view: bool = True


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalise to naive UTC — task timestamps are stored without a tzinfo."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _floor_to_bucket(dt: datetime, granularity: str) -> datetime:
    """Snap a timestamp down to the start of its UTC bucket."""
    day = datetime(dt.year, dt.month, dt.day)
    if granularity == "day":
        return day
    if granularity == "week":
        return day - timedelta(days=day.weekday())  # ISO weeks start Monday
    return datetime(dt.year, dt.month, 1)


def _advance_bucket(bucket_start: datetime, granularity: str) -> datetime:
    """Start of the bucket after this one."""
    if granularity == "day":
        return bucket_start + timedelta(days=1)
    if granularity == "week":
        return bucket_start + timedelta(days=7)
    if bucket_start.month == 12:
        return datetime(bucket_start.year + 1, 1, 1)
    return datetime(bucket_start.year, bucket_start.month + 1, 1)


def _generate_buckets(start: datetime, end: datetime, granularity: str) -> List[tuple]:
    """Dense list of (bucket_start, bucket_end) covering [start, end] inclusive."""
    bounds: List[tuple] = []
    cursor = _floor_to_bucket(start, granularity)
    while cursor <= end:
        nxt = _advance_bucket(cursor, granularity)
        bounds.append((cursor, nxt - timedelta(seconds=1)))
        cursor = nxt
    return bounds


def _bucket_label(bucket_start: datetime, bucket_end: datetime, granularity: str) -> str:
    """Axis label. Built server-side so UTC buckets never get re-dated by a browser."""
    month = _MONTH_ABBR[bucket_start.month - 1]
    if granularity == "day":
        return f"{month} {bucket_start.day}"
    if granularity == "month":
        return f"{month} {bucket_start.year}"
    end_month = _MONTH_ABBR[bucket_end.month - 1]
    if bucket_end.month == bucket_start.month:
        return f"{month} {bucket_start.day}–{bucket_end.day}"
    return f"{month} {bucket_start.day}–{end_month} {bucket_end.day}"


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

    # ------------------------------------------------------------------
    # Shared goal attribution
    # ------------------------------------------------------------------

    def _attribute_period_tasks(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        parent_goal_id: Optional[str] = None,
    ) -> "_Attribution":
        """Resolve every completed task in the period to one goal row.

        Shared by ``breakdown_report`` and ``trends_report`` so the two views can
        never disagree about which goal a task's points belong to.

        A "row" is one of the goals shown at the current drill level: the user's
        root goals when ``parent_goal_id`` is None, otherwise the immediate
        children of that goal. ``None`` as a row id means the No Goal bucket,
        which only exists in the root view.
        """
        # 1. Load all user goals; build tree maps
        all_goals = self.db.query(Goal).filter(Goal.user_id == user_id).all()
        goal_map: dict = {g.id: g for g in all_goals}
        parent_map: dict = {g.id: g.parent_goal_id for g in all_goals}
        children_map: dict = {}
        for g in all_goals:
            children_map.setdefault(g.parent_goal_id, []).append(g.id)

        # 2. Validate parent_goal_id when provided
        if parent_goal_id is not None and parent_goal_id not in goal_map:
            raise NotFoundError("Goal", parent_goal_id)

        # 3. Compute goal depths via BFS from roots
        depth_map: dict = {}
        roots = [g.id for g in all_goals if g.parent_goal_id is None]
        bfs: list = [(r, 0) for r in roots]
        while bfs:
            gid, depth = bfs.pop(0)
            depth_map[gid] = depth
            for child_id in children_map.get(gid, []):
                bfs.append((child_id, depth + 1))

        # 4. Determine scope (which goals are candidates) and target rows
        if parent_goal_id is None:
            target_ids = set(roots)
            scope_ids = set(goal_map.keys())
        else:
            immediate_children = children_map.get(parent_goal_id, [])
            target_ids = set(immediate_children)
            # Scope = all descendants of parent_goal_id (not the parent itself)
            scope_ids: set = set()
            queue = list(immediate_children)
            while queue:
                cur = queue.pop()
                scope_ids.add(cur)
                queue.extend(children_map.get(cur, []))

        def _find_row(goal_id: str):
            """Climb from goal_id upward until we reach a target row."""
            current = goal_id
            visited: set = set()
            while current not in target_ids:
                if current is None or current in visited:
                    return None
                visited.add(current)
                current = parent_map.get(current)
            return current

        # 5. Query qualifying completed tasks in date range
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

        # 6. Build task → linked goal IDs from both link sources
        task_ids = [t.id for t in tasks]
        task_goal_ids: dict = {}

        if task_ids:
            # Source A: TaskGoal rows (don't filter by user_id to preserve NULL rows)
            tg_links = (
                self.db.query(TaskGoal.task_id, TaskGoal.goal_id)
                .filter(TaskGoal.task_id.in_(task_ids))
                .all()
            )
            for tid, gid in tg_links:
                task_goal_ids.setdefault(tid, set()).add(gid)

            # Source B: legacy Task.goal_id
            for task in tasks:
                if task.goal_id:
                    task_goal_ids.setdefault(task.id, set()).add(task.goal_id)

        # 7. Attribute each task to a target-row bucket
        attributions: List[tuple] = []  # (task, row_id | None)

        for task in tasks:
            all_linked = task_goal_ids.get(task.id, set())
            # Keep only goals in scope that belong to this user (isolation guard)
            in_scope = [gid for gid in all_linked if gid in scope_ids and gid in goal_map]

            if not in_scope:
                if parent_goal_id is None:
                    # Root view: task goes to No Goal bucket
                    attributions.append((task, None))
                # Child view: task is outside this subtree — exclude
                continue

            # Deepest-link attribution: pick goal with max depth; tie-break by min goal_id
            best_depth = max(depth_map.get(gid, 0) for gid in in_scope)
            candidates = [gid for gid in in_scope if depth_map.get(gid, 0) == best_depth]
            deepest = min(candidates)  # deterministic: lexicographically smallest id

            row_id = _find_row(deepest)
            if row_id is None:
                continue  # malformed data — skip

            attributions.append((task, row_id))

        # Stable row order: title, then id so same-titled goals never swap places
        ordered_row_ids = sorted(target_ids, key=lambda x: (goal_map[x].title, x))

        return _Attribution(
            goal_map=goal_map,
            children_map=children_map,
            ordered_row_ids=ordered_row_ids,
            attributions=attributions,
            is_root_view=parent_goal_id is None,
        )

    def breakdown_report(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        parent_goal_id: Optional[str] = None,
    ) -> BreakdownReportResponse:
        attr = self._attribute_period_tasks(user_id, start_date, end_date, parent_goal_id)

        bucket_sizes: dict = {}  # target_row_id (or None = No Goal) → total points
        for task, row_id in attr.attributions:
            bucket_sizes[row_id] = bucket_sizes.get(row_id, 0) + task.size

        total_impact = sum(bucket_sizes.values())

        rows: List[BreakdownRow] = []
        for target_id in attr.ordered_row_ids:
            g = attr.goal_map[target_id]
            points = bucket_sizes.get(target_id, 0)
            percentage = round(points * 100 / total_impact) if total_impact > 0 else 0
            has_children = bool(attr.children_map.get(target_id))
            rows.append(BreakdownRow(
                goal_id=target_id,
                goal_title=g.title,
                goal_type=g.type.value if g.type else None,
                points=points,
                percentage=percentage,
                has_children=has_children,
            ))

        # No Goal row is only shown at root level
        if attr.is_root_view:
            no_goal_points = bucket_sizes.get(None, 0)
            no_goal_pct = round(no_goal_points * 100 / total_impact) if total_impact > 0 else 0
            rows.append(BreakdownRow(
                goal_id=None,
                goal_title="No Goal",
                goal_type=None,
                points=no_goal_points,
                percentage=no_goal_pct,
                has_children=False,
            ))

        return BreakdownReportResponse(
            parent_id=parent_goal_id,
            total_impact=total_impact,
            breakdown=rows,
        )

    def trends_report(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "day",
        parent_goal_id: Optional[str] = None,
    ) -> TrendsReportResponse:
        """Completed points over time, split by goal row, plus period averages.

        Buckets are UTC calendar slots and are dense, so idle days show as gaps
        rather than being skipped. ``stats`` is always computed over calendar
        days regardless of ``granularity``, so the averages don't change meaning
        when the chart is rolled up to weeks or months.
        """
        if granularity not in BUCKET_GRANULARITIES:
            raise ValidationError(
                f"granularity must be one of {sorted(BUCKET_GRANULARITIES)}",
                details={"granularity": granularity},
            )

        start = _as_naive_utc(start_date)
        end = _as_naive_utc(end_date)
        if end < start:
            raise ValidationError(
                "end_date must not be earlier than start_date",
                details={"start_date": start.isoformat(), "end_date": end.isoformat()},
            )

        bucket_bounds = _generate_buckets(start, end, granularity)
        if len(bucket_bounds) > MAX_TREND_BUCKETS:
            raise ValidationError(
                f"period produces {len(bucket_bounds)} '{granularity}' buckets, "
                f"which exceeds the {MAX_TREND_BUCKETS} limit — use a coarser granularity",
                details={
                    "granularity": granularity,
                    "bucket_count": len(bucket_bounds),
                    "max_buckets": MAX_TREND_BUCKETS,
                },
            )

        attr = self._attribute_period_tasks(user_id, start, end, parent_goal_id)
        bucket_index = {b_start: i for i, (b_start, _) in enumerate(bucket_bounds)}
        n = len(bucket_bounds)

        bucket_points = [0] * n
        bucket_tasks = [0] * n
        row_values: dict = {}   # row_id (None = No Goal) → list of points per bucket
        daily_points: dict = {}  # date → points

        for task, row_id in attr.attributions:
            completed = _as_naive_utc(task.completed_at)
            idx = bucket_index.get(_floor_to_bucket(completed, granularity))
            if idx is None:
                # completed_at outside the generated axis — can only happen if the
                # caller's range and the stored timestamp disagree; skip rather than
                # silently fold it into an adjacent bucket.
                continue
            bucket_points[idx] += task.size
            bucket_tasks[idx] += 1
            row_values.setdefault(row_id, [0] * n)[idx] += task.size
            day = completed.date()
            daily_points[day] = daily_points.get(day, 0) + task.size

        buckets: List[TrendBucket] = [
            TrendBucket(
                bucket_start=b_start,
                bucket_end=b_end,
                label=_bucket_label(b_start, b_end, granularity),
                points=bucket_points[i],
                task_count=bucket_tasks[i],
            )
            for i, (b_start, b_end) in enumerate(bucket_bounds)
        ]

        # order_index is the row's stable position at this drill level, so the
        # frontend can key a colour to a goal rather than to its current rank.
        order_index_of = {row_id: i for i, row_id in enumerate(attr.ordered_row_ids)}
        series: List[TrendSeries] = []
        for row_id in attr.ordered_row_ids:
            values = row_values.get(row_id)
            if not values:
                continue  # no points this period — nothing to plot
            series.append(TrendSeries(
                goal_id=row_id,
                goal_title=attr.goal_map[row_id].title,
                is_no_goal=False,
                order_index=order_index_of[row_id],
                points=sum(values),
                values=values,
            ))

        no_goal_values = row_values.get(None)
        if no_goal_values:
            series.append(TrendSeries(
                goal_id=None,
                goal_title="No Goal",
                is_no_goal=True,
                order_index=len(attr.ordered_row_ids),
                points=sum(no_goal_values),
                values=no_goal_values,
            ))

        total_points = sum(bucket_points)
        task_count = sum(bucket_tasks)
        days_in_period = max((end.date() - start.date()).days + 1, 1)
        active_days = sum(1 for v in daily_points.values() if v > 0)
        best_day = None
        best_day_points = 0
        if daily_points:
            # max by points, earliest day wins a tie
            best_day, best_day_points = min(
                daily_points.items(), key=lambda kv: (-kv[1], kv[0])
            )

        stats = TrendStats(
            total_points=total_points,
            task_count=task_count,
            days_in_period=days_in_period,
            active_days=active_days,
            avg_points_per_day=round(total_points / days_in_period, 2),
            avg_points_per_active_day=round(total_points / active_days, 2) if active_days else 0.0,
            avg_points_per_week=round(total_points * 7 / days_in_period, 2),
            best_day=datetime(best_day.year, best_day.month, best_day.day) if best_day else None,
            best_day_points=best_day_points,
        )

        return TrendsReportResponse(
            start_date=start,
            end_date=end,
            granularity=granularity,
            parent_id=parent_goal_id,
            total_points=total_points,
            buckets=buckets,
            series=series,
            stats=stats,
        )
