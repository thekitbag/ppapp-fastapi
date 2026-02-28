import pytest
import uuid
from datetime import datetime, timezone
from app.services.reporting import ReportingService
from app.models import User, Goal, Task, TaskGoal, ProviderEnum, StatusEnum
from app.exceptions import NotFoundError


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
