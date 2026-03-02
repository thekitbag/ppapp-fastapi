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


# ---------------------------------------------------------------------------
# ReportingService.breakdown_report tests (REPORT-005)
# ---------------------------------------------------------------------------


class TestBreakdownReport:
    """Unit tests for ReportingService.breakdown_report."""

    @pytest.fixture
    def svc(self, test_db):
        return ReportingService(test_db)

    @pytest.fixture
    def user(self, test_db):
        u = User(
            id="bd-svc-user-1",
            provider=ProviderEnum.google,
            provider_sub="bd-svc-sub-1",
            email="bdsvc1@example.com",
            name="BD SVC User",
        )
        test_db.add(u)
        test_db.commit()
        return u

    @pytest.fixture
    def other_user(self, test_db):
        u = User(
            id="bd-svc-user-2",
            provider=ProviderEnum.google,
            provider_sub="bd-svc-sub-2",
            email="bdsvc2@example.com",
            name="BD SVC Other",
        )
        test_db.add(u)
        test_db.commit()
        return u

    def _make_goal(self, db, user_id, title, goal_type=None, parent_goal_id=None):
        from app.models import GoalTypeEnum as GTE
        g = Goal(
            id=f"goal_{_uid()}",
            title=title,
            user_id=user_id,
            type=goal_type,
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
    # Root view tests
    # ------------------------------------------------------------------

    def test_root_view_has_no_goal_row(self, svc, user, test_db):
        """Root view always includes a No Goal row."""
        result = svc.breakdown_report(user.id, _START, _END)
        no_goal = next((r for r in result.breakdown if r.goal_id is None), None)
        assert no_goal is not None
        assert no_goal.goal_title == "No Goal"
        assert no_goal.has_children is False

    def test_root_view_shows_root_goals(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual")
        result = svc.breakdown_report(user.id, _START, _END)
        row_ids = [r.goal_id for r in result.breakdown]
        assert annual.id in row_ids

    def test_cascading_sum_to_root(self, svc, user, test_db):
        """Points from tasks linked to descendants roll up to the root annual row."""
        annual = self._make_goal(test_db, user.id, "Annual")
        quarterly = self._make_goal(test_db, user.id, "Q1", parent_goal_id=annual.id)
        weekly = self._make_goal(test_db, user.id, "W1", parent_goal_id=quarterly.id)

        t1 = self._make_task(test_db, user.id, "T1", 3, _dt(2025, 2, 1))
        t2 = self._make_task(test_db, user.id, "T2", 5, _dt(2025, 4, 1))
        self._link(test_db, t1, quarterly, user.id)
        self._link(test_db, t2, weekly, user.id)

        result = svc.breakdown_report(user.id, _START, _END)
        annual_row = next(r for r in result.breakdown if r.goal_id == annual.id)
        assert annual_row.points == 8

    def test_unlinked_tasks_go_to_no_goal(self, svc, user, test_db):
        t = self._make_task(test_db, user.id, "Unlinked", 5, _dt(2025, 6, 1))
        result = svc.breakdown_report(user.id, _START, _END)
        no_goal = next(r for r in result.breakdown if r.goal_id is None)
        assert no_goal.points == 5

    def test_total_impact_equals_sum_of_rows(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual TI")
        t1 = self._make_task(test_db, user.id, "T1", 3, _dt(2025, 6, 1))
        t2 = self._make_task(test_db, user.id, "T2", 2, _dt(2025, 6, 2))
        self._link(test_db, t1, annual, user.id)
        # t2 unlinked → No Goal bucket

        result = svc.breakdown_report(user.id, _START, _END)
        assert result.total_impact == sum(r.points for r in result.breakdown)

    def test_percentage_calculation(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual Pct")
        t = self._make_task(test_db, user.id, "T", 3, _dt(2025, 6, 1))
        self._link(test_db, t, annual, user.id)

        t_unlinked = self._make_task(test_db, user.id, "TU", 1, _dt(2025, 6, 1))

        result = svc.breakdown_report(user.id, _START, _END)
        annual_row = next(r for r in result.breakdown if r.goal_id == annual.id)
        no_goal = next(r for r in result.breakdown if r.goal_id is None)
        # total = 4; annual = 3 → 75%; no goal = 1 → 25%
        assert annual_row.percentage == 75
        assert no_goal.percentage == 25

    def test_has_children_flag(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual HC")
        self._make_goal(test_db, user.id, "Q1 HC", parent_goal_id=annual.id)

        result = svc.breakdown_report(user.id, _START, _END)
        annual_row = next(r for r in result.breakdown if r.goal_id == annual.id)
        assert annual_row.has_children is True

    def test_goal_type_propagated(self, svc, user, test_db):
        from app.models import GoalTypeEnum as GTE
        annual = self._make_goal(test_db, user.id, "Annual GT", goal_type=GTE.annual)

        result = svc.breakdown_report(user.id, _START, _END)
        annual_row = next(r for r in result.breakdown if r.goal_id == annual.id)
        assert annual_row.goal_type == "annual"

    # ------------------------------------------------------------------
    # Child/drill-down view tests
    # ------------------------------------------------------------------

    def test_child_view_shows_immediate_children(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual DV")
        q1 = self._make_goal(test_db, user.id, "Q1 DV", parent_goal_id=annual.id)
        q2 = self._make_goal(test_db, user.id, "Q2 DV", parent_goal_id=annual.id)

        result = svc.breakdown_report(user.id, _START, _END, parent_goal_id=annual.id)
        row_ids = {r.goal_id for r in result.breakdown}
        assert q1.id in row_ids
        assert q2.id in row_ids
        assert annual.id not in row_ids

    def test_child_view_no_no_goal_row(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual NG")
        self._make_goal(test_db, user.id, "Q NG", parent_goal_id=annual.id)

        result = svc.breakdown_report(user.id, _START, _END, parent_goal_id=annual.id)
        assert all(r.goal_id is not None for r in result.breakdown)

    def test_child_view_parent_id_set(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual PI")
        self._make_goal(test_db, user.id, "Q PI", parent_goal_id=annual.id)

        result = svc.breakdown_report(user.id, _START, _END, parent_goal_id=annual.id)
        assert result.parent_id == annual.id

    def test_child_view_cascading_sum(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual CS")
        quarterly = self._make_goal(test_db, user.id, "Q1 CS", parent_goal_id=annual.id)
        weekly = self._make_goal(test_db, user.id, "W1 CS", parent_goal_id=quarterly.id)

        t = self._make_task(test_db, user.id, "T", 5, _dt(2025, 4, 1))
        self._link(test_db, t, weekly, user.id)

        result = svc.breakdown_report(user.id, _START, _END, parent_goal_id=annual.id)
        q_row = next(r for r in result.breakdown if r.goal_id == quarterly.id)
        assert q_row.points == 5

    def test_child_view_excludes_out_of_subtree_tasks(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual EX")
        q = self._make_goal(test_db, user.id, "Q EX", parent_goal_id=annual.id)
        sibling = self._make_goal(test_db, user.id, "Sibling Annual")

        t = self._make_task(test_db, user.id, "T", 5, _dt(2025, 6, 1))
        self._link(test_db, t, sibling, user.id)  # outside annual's subtree

        result = svc.breakdown_report(user.id, _START, _END, parent_goal_id=annual.id)
        assert result.total_impact == 0

    def test_unknown_parent_raises_not_found(self, svc, user, test_db):
        with pytest.raises(NotFoundError):
            svc.breakdown_report(user.id, _START, _END, parent_goal_id="nonexistent")

    def test_other_user_parent_raises_not_found(self, svc, user, other_user, test_db):
        other_goal = self._make_goal(test_db, other_user.id, "Other Goal")
        with pytest.raises(NotFoundError):
            svc.breakdown_report(user.id, _START, _END, parent_goal_id=other_goal.id)

    # ------------------------------------------------------------------
    # Attribution algorithm tests
    # ------------------------------------------------------------------

    def test_deepest_link_in_same_branch(self, svc, user, test_db):
        """Task linked to both parent and child → attributed to child (deepest)."""
        annual = self._make_goal(test_db, user.id, "Annual DL")
        quarterly = self._make_goal(test_db, user.id, "Q DL", parent_goal_id=annual.id)
        weekly = self._make_goal(test_db, user.id, "W DL", parent_goal_id=quarterly.id)

        t = self._make_task(test_db, user.id, "T", 5, _dt(2025, 6, 1))
        self._link(test_db, t, quarterly, user.id)
        self._link(test_db, t, weekly, user.id)

        # In root view task should be counted exactly once under annual
        result = svc.breakdown_report(user.id, _START, _END)
        annual_row = next(r for r in result.breakdown if r.goal_id == annual.id)
        assert annual_row.points == 5
        assert result.total_impact == 5

    def test_no_double_counting_multi_link(self, svc, user, test_db):
        """Task linked to three goals in same branch counted once."""
        annual = self._make_goal(test_db, user.id, "Annual NDC")
        q = self._make_goal(test_db, user.id, "Q NDC", parent_goal_id=annual.id)
        w = self._make_goal(test_db, user.id, "W NDC", parent_goal_id=q.id)

        t = self._make_task(test_db, user.id, "T", 3, _dt(2025, 6, 1))
        self._link(test_db, t, annual, user.id)
        self._link(test_db, t, q, user.id)
        self._link(test_db, t, w, user.id)

        result = svc.breakdown_report(user.id, _START, _END)
        assert result.total_impact == 3

    def test_cross_branch_same_depth_counted_once(self, svc, user, test_db):
        """Task linked to two siblings (same depth) counted once — min goal_id wins."""
        annual = self._make_goal(test_db, user.id, "Annual CB")
        q1 = self._make_goal(test_db, user.id, "Q1 CB", parent_goal_id=annual.id)
        q2 = self._make_goal(test_db, user.id, "Q2 CB", parent_goal_id=annual.id)

        t = self._make_task(test_db, user.id, "T", 5, _dt(2025, 6, 1))
        self._link(test_db, t, q1, user.id)
        self._link(test_db, t, q2, user.id)

        result = svc.breakdown_report(user.id, _START, _END)
        annual_row = next(r for r in result.breakdown if r.goal_id == annual.id)
        assert annual_row.points == 5
        assert result.total_impact == 5  # no double-counting

    # ------------------------------------------------------------------
    # Date filtering tests
    # ------------------------------------------------------------------

    def test_date_filter_excludes_out_of_range(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual DF")
        t_in = self._make_task(test_db, user.id, "In", 5, _dt(2025, 6, 15))
        t_out = self._make_task(test_db, user.id, "Out", 3, _dt(2025, 1, 1))
        self._link(test_db, t_in, annual, user.id)
        self._link(test_db, t_out, annual, user.id)

        result = svc.breakdown_report(user.id, _dt(2025, 6, 1), _dt(2025, 6, 30))
        assert result.total_impact == 5

    def test_date_bounds_inclusive(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual INC")
        t_start = self._make_task(test_db, user.id, "On start", 2, _dt(2025, 6, 1))
        t_end = self._make_task(test_db, user.id, "On end", 3, _dt(2025, 6, 30))
        self._link(test_db, t_start, annual, user.id)
        self._link(test_db, t_end, annual, user.id)

        result = svc.breakdown_report(user.id, _dt(2025, 6, 1), _dt(2025, 6, 30))
        assert result.total_impact == 5

    # ------------------------------------------------------------------
    # Data quality tests
    # ------------------------------------------------------------------

    def test_tasks_without_size_excluded(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual NSZ")
        t = Task(
            id=f"task_{_uid()}",
            title="No size",
            user_id=user.id,
            status=StatusEnum.done,
            sort_order=0.0,
            size=None,
            completed_at=_dt(2025, 6, 1),
        )
        test_db.add(t)
        test_db.commit()
        self._link(test_db, t, annual, user.id)

        result = svc.breakdown_report(user.id, _START, _END)
        assert result.total_impact == 0

    def test_incomplete_tasks_excluded(self, svc, user, test_db):
        annual = self._make_goal(test_db, user.id, "Annual INC2")
        t = Task(
            id=f"task_{_uid()}",
            title="Not done",
            user_id=user.id,
            status=StatusEnum.doing,
            sort_order=0.0,
            size=8,
            completed_at=None,
        )
        test_db.add(t)
        test_db.commit()
        self._link(test_db, t, annual, user.id)

        result = svc.breakdown_report(user.id, _START, _END)
        annual_row = next((r for r in result.breakdown if r.goal_id == annual.id), None)
        assert annual_row is None or annual_row.points == 0

    def test_legacy_task_goal_id_counted(self, svc, user, test_db):
        """Task linked via legacy Task.goal_id (no TaskGoal row) is attributed."""
        annual = self._make_goal(test_db, user.id, "Annual LGC")
        t = Task(
            id=f"task_{_uid()}",
            title="Legacy",
            user_id=user.id,
            status=StatusEnum.done,
            sort_order=0.0,
            size=5,
            completed_at=_dt(2025, 6, 1),
            goal_id=annual.id,  # legacy field
        )
        test_db.add(t)
        test_db.commit()

        result = svc.breakdown_report(user.id, _START, _END)
        annual_row = next(r for r in result.breakdown if r.goal_id == annual.id)
        assert annual_row.points == 5
