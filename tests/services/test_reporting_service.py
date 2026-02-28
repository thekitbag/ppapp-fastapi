import pytest
import uuid
from datetime import datetime, timezone
from app.services.reporting import ReportingService
from app.models import User, Goal, Task, TaskGoal, ProviderEnum, StatusEnum
from app.exceptions import NotFoundError

_START = datetime(2025, 1, 1, tzinfo=timezone.utc)
_END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def _uid():
    return str(uuid.uuid4())


def _dt(year=2025, month=6, day=15):
    return datetime(year, month, day, tzinfo=timezone.utc)


class TestReportingService:

    @pytest.fixture
    def svc(self, test_db):
        return ReportingService(test_db)

    @pytest.fixture
    def user(self, test_db):
        u = User(
            id="rpt-user-1",
            provider=ProviderEnum.google,
            provider_sub="rpt-sub-1",
            email="rpt1@example.com",
            name="Report User",
        )
        test_db.add(u)
        test_db.commit()
        return u

    @pytest.fixture
    def other_user(self, test_db):
        u = User(
            id="rpt-user-2",
            provider=ProviderEnum.google,
            provider_sub="rpt-sub-2",
            email="rpt2@example.com",
            name="Other User",
        )
        test_db.add(u)
        test_db.commit()
        return u

    def _make_goal(self, db, user_id, title, parent_goal_id=None):
        g = Goal(
            id=f"goal_{_uid()}",
            title=title,
            user_id=user_id,
            parent_goal_id=parent_goal_id,
        )
        db.add(g)
        db.commit()
        return g

    def _make_task(self, db, user_id, title, size, completed_at):
        t = Task(
            id=f"task_{_uid()}",
            title=title,
            user_id=user_id,
            status=StatusEnum.done,
            sort_order=0.0,
            size=size,
            completed_at=completed_at,
        )
        db.add(t)
        db.commit()
        return t

    def _link(self, db, task, goal, user_id):
        tg = TaskGoal(
            id=f"tg_{_uid()}",
            task_id=task.id,
            goal_id=goal.id,
            user_id=user_id,
        )
        db.add(tg)
        db.commit()

    # ------------------------------------------------------------------
    def test_three_level_hierarchy(self, svc, user, test_db):
        """Annual → quarterly → weekly, tasks at each level."""
        annual = self._make_goal(test_db, user.id, "Annual")
        quarterly = self._make_goal(test_db, user.id, "Q1", parent_goal_id=annual.id)
        weekly = self._make_goal(test_db, user.id, "W1", parent_goal_id=quarterly.id)

        t1 = self._make_task(test_db, user.id, "T1", 5, _dt(2025, 1, 10))
        t2 = self._make_task(test_db, user.id, "T2", 3, _dt(2025, 3, 5))
        t3 = self._make_task(test_db, user.id, "T3", 2, _dt(2025, 7, 20))

        self._link(test_db, t1, annual, user.id)
        self._link(test_db, t2, quarterly, user.id)
        self._link(test_db, t3, weekly, user.id)

        result = svc.goal_progress_report(annual.id, user.id)

        assert result.goal_id == annual.id
        assert result.goal_title == "Annual"
        assert result.direct_size == 5
        assert result.descendant_size == 5   # 3 + 2
        assert result.total_size == 10
        assert result.start_date is None
        assert result.end_date is None

    def test_date_filter_includes_in_range(self, svc, user, test_db):
        """Tasks within window counted; outside excluded."""
        goal = self._make_goal(test_db, user.id, "Filtered Goal")

        t_in = self._make_task(test_db, user.id, "In range", 8, _dt(2025, 6, 15))
        t_out = self._make_task(test_db, user.id, "Out range", 5, _dt(2025, 1, 1))

        self._link(test_db, t_in, goal, user.id)
        self._link(test_db, t_out, goal, user.id)

        start = _dt(2025, 6, 1)
        end = _dt(2025, 6, 30)
        result = svc.goal_progress_report(goal.id, user.id, start_date=start, end_date=end)

        assert result.direct_size == 8
        assert result.total_size == 8

    def test_lifetime_no_date_filter(self, svc, user, test_db):
        """No date args → all completed tasks counted."""
        goal = self._make_goal(test_db, user.id, "Lifetime Goal")

        t1 = self._make_task(test_db, user.id, "T1", 1, _dt(2023, 1, 1))
        t2 = self._make_task(test_db, user.id, "T2", 2, _dt(2024, 6, 6))
        t3 = self._make_task(test_db, user.id, "T3", 3, _dt(2025, 12, 31))

        for t in (t1, t2, t3):
            self._link(test_db, t, goal, user.id)

        result = svc.goal_progress_report(goal.id, user.id)
        assert result.total_size == 6

    def test_goal_not_found(self, svc, user, test_db):
        with pytest.raises(NotFoundError):
            svc.goal_progress_report("nonexistent-goal", user.id)

    def test_user_isolation(self, svc, user, other_user, test_db):
        """Querying another user's goal raises NotFoundError."""
        goal = self._make_goal(test_db, other_user.id, "Other's Goal")

        with pytest.raises(NotFoundError):
            svc.goal_progress_report(goal.id, user.id)

    def test_task_deduplication(self, svc, user, test_db):
        """Task linked to both root and descendant counted once in direct_size."""
        root = self._make_goal(test_db, user.id, "Root")
        child = self._make_goal(test_db, user.id, "Child", parent_goal_id=root.id)

        t = self._make_task(test_db, user.id, "Dual-linked", 5, _dt(2025, 6, 1))
        self._link(test_db, t, root, user.id)
        self._link(test_db, t, child, user.id)

        result = svc.goal_progress_report(root.id, user.id)

        assert result.direct_size == 5
        assert result.descendant_size == 0   # excluded because already in direct
        assert result.total_size == 5

    def test_tasks_without_size_excluded(self, svc, user, test_db):
        """Tasks with size=None are not counted."""
        goal = self._make_goal(test_db, user.id, "No Size Goal")
        t = self._make_task(test_db, user.id, "No size", None, _dt(2025, 6, 1))
        self._link(test_db, t, goal, user.id)

        result = svc.goal_progress_report(goal.id, user.id)
        assert result.total_size == 0

    def test_incomplete_tasks_excluded(self, svc, user, test_db):
        """Tasks with completed_at=None are not counted."""
        goal = self._make_goal(test_db, user.id, "Incomplete Goal")
        t = Task(
            id=f"task_{_uid()}",
            title="Incomplete",
            user_id=user.id,
            status=StatusEnum.doing,
            sort_order=0.0,
            size=8,
            completed_at=None,
        )
        test_db.add(t)
        test_db.commit()
        self._link(test_db, t, goal, user.id)

        result = svc.goal_progress_report(goal.id, user.id)
        assert result.total_size == 0


class TestSummaryReport:
    """Tests for ReportingService.summary_report — including hotfix regression cases."""

    @pytest.fixture
    def svc(self, test_db):
        return ReportingService(test_db)

    @pytest.fixture
    def user(self, test_db):
        u = User(
            id="sum-user-1",
            provider=ProviderEnum.google,
            provider_sub="sum-sub-1",
            email="sum1@example.com",
            name="Summary User",
        )
        test_db.add(u)
        test_db.commit()
        return u

    def _make_goal(self, db, user_id, title, parent_goal_id=None):
        g = Goal(
            id=f"goal_{_uid()}",
            title=title,
            user_id=user_id,
            parent_goal_id=parent_goal_id,
        )
        db.add(g)
        db.commit()
        return g

    def _make_done_task(self, db, user_id, title, size, goal_id=None):
        t = Task(
            id=f"task_{_uid()}",
            title=title,
            user_id=user_id,
            status=StatusEnum.done,
            sort_order=0.0,
            size=size,
            completed_at=_dt(2025, 6, 1),
            goal_id=goal_id,
        )
        db.add(t)
        db.commit()
        return t

    def _make_task_goal(self, db, task_id, goal_id, user_id):
        tg = TaskGoal(
            id=f"tg_{_uid()}",
            task_id=task_id,
            goal_id=goal_id,
            user_id=user_id,
        )
        db.add(tg)
        db.commit()
        return tg

    # ------------------------------------------------------------------
    # HOTFIX: legacy Task.goal_id attribution
    # ------------------------------------------------------------------

    def test_legacy_goal_id_attributed_to_root(self, svc, user, test_db):
        """Task with only Task.goal_id (no TaskGoal row) rolls up to root, not No Goal."""
        root = self._make_goal(test_db, user.id, "Legacy Root")
        child = self._make_goal(test_db, user.id, "Legacy Child", parent_goal_id=root.id)

        # Task linked via legacy field to child — no TaskGoal row created
        t = self._make_done_task(test_db, user.id, "Legacy task", 5, goal_id=child.id)

        result = svc.summary_report(user.id, _START, _END)

        root_group = next((g for g in result.groups if g.goal_id == root.id), None)
        no_goal_group = next(g for g in result.groups if g.is_no_goal)

        assert root_group is not None, "Root group should exist for legacy-linked task"
        assert root_group.total_size == 5
        assert no_goal_group.total_size == 0

    # ------------------------------------------------------------------
    # HOTFIX: mixed legacy + TaskGoal links
    # ------------------------------------------------------------------

    def test_mixed_legacy_and_taskgoal_links(self, svc, user, test_db):
        """Tasks using both link sources roll up correctly."""
        root_a = self._make_goal(test_db, user.id, "Root A")
        root_b = self._make_goal(test_db, user.id, "Root B")

        # Task A: linked via TaskGoal
        t_a = self._make_done_task(test_db, user.id, "Modern task", 3)
        self._make_task_goal(test_db, t_a.id, root_a.id, user.id)

        # Task B: linked via legacy goal_id only (no TaskGoal row)
        t_b = self._make_done_task(test_db, user.id, "Legacy task", 8, goal_id=root_b.id)

        result = svc.summary_report(user.id, _START, _END)

        group_a = next((g for g in result.groups if g.goal_id == root_a.id), None)
        group_b = next((g for g in result.groups if g.goal_id == root_b.id), None)
        no_goal = next(g for g in result.groups if g.is_no_goal)

        assert group_a is not None and group_a.total_size == 3
        assert group_b is not None and group_b.total_size == 8
        assert no_goal.total_size == 0
        assert result.impact_score == 11

    # ------------------------------------------------------------------
    # HOTFIX: TaskGoal row with user_id=None still attributed
    # ------------------------------------------------------------------

    def test_taskgoal_null_user_id_still_attributed(self, svc, user, test_db):
        """TaskGoal row with user_id=NULL is not dropped; task is attributed to root."""
        root = self._make_goal(test_db, user.id, "Null UID Root")
        t = self._make_done_task(test_db, user.id, "Null UID task", 5)

        # Insert TaskGoal with user_id explicitly NULL (simulates old migrated data)
        tg = TaskGoal(
            id=f"tg_{_uid()}",
            task_id=t.id,
            goal_id=root.id,
            user_id=None,
        )
        test_db.add(tg)
        test_db.commit()

        result = svc.summary_report(user.id, _START, _END)

        root_group = next((g for g in result.groups if g.goal_id == root.id), None)
        no_goal = next(g for g in result.groups if g.is_no_goal)

        assert root_group is not None, "Root group missing — null user_id row was dropped"
        assert root_group.total_size == 5
        assert no_goal.total_size == 0
