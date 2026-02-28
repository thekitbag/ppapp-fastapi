"""Service-level tests for prioritize_tasks energy, time_window, and goal-health ranking."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models import Task, StatusEnum
from app.services.recommendations import prioritize_tasks


def _uid():
    return str(uuid.uuid4())


def _make_task(size=None, status="backlog", energy=None):
    return Task(
        id=f"task_{_uid()}",
        title=f"Task size={size} energy={energy}",
        user_id="svc-user-1",
        status=status,
        sort_order=0.0,
        size=size,
        energy=energy,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Energy match tests (SUGGEST-002: match task.energy field, not task.size)
# ---------------------------------------------------------------------------

class TestEnergyRanking:

    def test_energy_low_ranks_matching_task_higher(self):
        """energy=low boosts tasks with task.energy in {low, tired}."""
        low_task = _make_task(energy="low")
        high_task = _make_task(energy="high")

        ranked = prioritize_tasks([high_task, low_task], energy="low")

        ids = [r.task.id for r in ranked]
        assert ids.index(low_task.id) < ids.index(high_task.id)

    def test_energy_tired_matches_low(self):
        """task.energy=tired is treated as equivalent to user energy=low."""
        tired_task = _make_task(energy="tired")
        high_task = _make_task(energy="high")

        ranked = prioritize_tasks([high_task, tired_task], energy="low")

        ids = [r.task.id for r in ranked]
        assert ids.index(tired_task.id) < ids.index(high_task.id)
        assert ranked[0].factors["energy_match"] == 1.0

    def test_energy_medium_ranks_matching_task_higher(self):
        """energy=medium boosts tasks with task.energy in {medium, neutral}."""
        medium_task = _make_task(energy="medium")
        high_task = _make_task(energy="high")

        ranked = prioritize_tasks([high_task, medium_task], energy="medium")

        ids = [r.task.id for r in ranked]
        assert ids.index(medium_task.id) < ids.index(high_task.id)

    def test_energy_neutral_matches_medium(self):
        """task.energy=neutral matches user energy=medium."""
        neutral_task = _make_task(energy="neutral")
        low_task = _make_task(energy="low")

        ranked = prioritize_tasks([low_task, neutral_task], energy="medium")

        ids = [r.task.id for r in ranked]
        assert ids.index(neutral_task.id) < ids.index(low_task.id)

    def test_energy_high_ranks_matching_task_higher(self):
        """energy=high boosts tasks with task.energy in {high, energized}."""
        high_task = _make_task(energy="high")
        low_task = _make_task(energy="low")

        ranked = prioritize_tasks([low_task, high_task], energy="high")

        ids = [r.task.id for r in ranked]
        assert ids.index(high_task.id) < ids.index(low_task.id)

    def test_energized_matches_high(self):
        """task.energy=energized matches user energy=high."""
        energized_task = _make_task(energy="energized")
        low_task = _make_task(energy="low")

        ranked = prioritize_tasks([low_task, energized_task], energy="high")

        ids = [r.task.id for r in ranked]
        assert ids.index(energized_task.id) < ids.index(low_task.id)

    def test_task_without_energy_gets_no_boost(self):
        """task.energy=None → no energy_match boost (unknown energy requirement)."""
        no_energy_task = _make_task(energy=None)
        ranked = prioritize_tasks([no_energy_task], energy="low")
        assert ranked[0].factors["energy_match"] == 0.0

    def test_no_energy_param_no_match_boost(self):
        """Without energy query param, energy_match is always 0."""
        task = _make_task(energy="low")
        ranked = prioritize_tasks([task])
        assert ranked[0].factors["energy_match"] == 0.0

    def test_energy_match_factor_and_time_fit_present_in_output(self):
        """factors dict always includes energy_match and time_fit keys."""
        task = _make_task(energy="low", size=2)
        ranked = prioritize_tasks([task], energy="low", time_window=30)
        assert "energy_match" in ranked[0].factors
        assert "time_fit" in ranked[0].factors


# ---------------------------------------------------------------------------
# Time fit tests (SUGGEST-002: Fibonacci effort bands, size=None → no boost)
# ---------------------------------------------------------------------------

class TestTimeWindowRanking:

    def test_time_window_15_boosts_size_1_task(self):
        """time_window=15 boosts tasks with size<=1 (Fibonacci band: 15min → size 1)."""
        tiny = _make_task(size=1)
        large = _make_task(size=5)

        ranked = prioritize_tasks([large, tiny], time_window=15)

        ids = [r.task.id for r in ranked]
        assert ids.index(tiny.id) < ids.index(large.id)
        assert ranked[0].factors["time_fit"] == 1.0

    def test_time_window_120_includes_size_5_task(self):
        """time_window=120 boosts tasks with size<=5 (Fibonacci band)."""
        medium = _make_task(size=5)
        large = _make_task(size=8)

        ranked = prioritize_tasks([large, medium], time_window=120)

        ids = [r.task.id for r in ranked]
        assert ids.index(medium.id) < ids.index(large.id)

    def test_task_without_size_gets_no_time_fit_boost(self):
        """task.size=None → no time_fit boost (unknown effort)."""
        no_size = _make_task(size=None)
        ranked = prioritize_tasks([no_size], time_window=30)
        assert ranked[0].factors["time_fit"] == 0.0

    def test_no_time_window_no_time_fit_boost(self):
        """Without time_window param, time_fit is always 0."""
        task = _make_task(size=1)
        ranked = prioritize_tasks([task])
        assert ranked[0].factors["time_fit"] == 0.0

    def test_energy_and_time_window_combined(self):
        """Both energy_match and time_fit can boost the same task simultaneously."""
        fitting = _make_task(size=1, energy="low")   # matches energy=low AND fits 15min
        not_fitting = _make_task(size=8, energy="high")  # neither

        ranked = prioritize_tasks([not_fitting, fitting], energy="low", time_window=15)

        ids = [r.task.id for r in ranked]
        assert ids.index(fitting.id) < ids.index(not_fitting.id)
        top = next(r for r in ranked if r.task.id == fitting.id)
        assert top.factors["energy_match"] == 1.0
        assert top.factors["time_fit"] == 1.0


# ---------------------------------------------------------------------------
# Goal health tests (SUGGEST-002: status boost + urgency)
# ---------------------------------------------------------------------------

class _MockGoal:
    def __init__(self, goal_id, title, status_value=None, end_date=None):
        self.id = goal_id
        self.title = title
        self.status = SimpleNamespace(value=status_value) if status_value else None
        self.end_date = end_date


def _make_mock_db(task_goal_map: dict, goals: list):
    """
    Build a minimal mock DB that returns task-goal links and goal objects.
    task_goal_map: {task_id: [goal_id, ...]}
    goals: list of _MockGoal objects
    """
    goals_by_id = {g.id: g for g in goals}

    class _MockTG:
        def __init__(self, task_id, goal_id):
            self.task_id = task_id
            self.goal_id = goal_id

    all_links = [
        _MockTG(tid, gid)
        for tid, gids in task_goal_map.items()
        for gid in gids
    ]

    class _MockDB:
        def __init__(self):
            self._model = None

        def query(self, model):
            self._model = model
            return self

        def filter(self, *args):
            return self

        def all(self):
            model_str = str(self._model) if self._model else ""
            if "TaskGoal" in model_str:
                return all_links
            if "Goal" in model_str and "TaskGoal" not in model_str:
                return list(goals_by_id.values())
            if "Project" in model_str:
                return []
            return []

        def in_(self, ids):
            return self

    return _MockDB()


class TestGoalHealthRanking:

    def test_off_target_goal_boosts_rank(self):
        """Task linked to off_target goal scores higher than unlinked task."""
        t_linked = _make_task()
        t_plain = _make_task()

        goal = _MockGoal("g1", "My Goal", status_value="off_target")
        db = _make_mock_db({t_linked.id: ["g1"]}, [goal])

        ranked = prioritize_tasks([t_plain, t_linked], db=db)

        ids = [r.task.id for r in ranked]
        assert ids.index(t_linked.id) < ids.index(t_plain.id)
        linked_result = next(r for r in ranked if r.task.id == t_linked.id)
        assert linked_result.factors["goal_status_off_target"] == 1.0
        assert linked_result.factors["goal_status_at_risk"] == 0.0

    def test_at_risk_goal_boosts_rank(self):
        """Task linked to at_risk goal scores higher than unlinked task."""
        t_linked = _make_task()
        t_plain = _make_task()

        goal = _MockGoal("g1", "Risk Goal", status_value="at_risk")
        db = _make_mock_db({t_linked.id: ["g1"]}, [goal])

        ranked = prioritize_tasks([t_plain, t_linked], db=db)

        ids = [r.task.id for r in ranked]
        assert ids.index(t_linked.id) < ids.index(t_plain.id)
        linked_result = next(r for r in ranked if r.task.id == t_linked.id)
        assert linked_result.factors["goal_status_at_risk"] == 1.0
        assert linked_result.factors["goal_status_off_target"] == 0.0

    def test_off_target_takes_priority_over_at_risk(self):
        """When linked goals include both at_risk and off_target, off_target wins (max boost, no double count)."""
        t = _make_task()
        goal_at_risk = _MockGoal("g1", "At Risk Goal", status_value="at_risk")
        goal_off = _MockGoal("g2", "Off Target Goal", status_value="off_target")
        db = _make_mock_db({t.id: ["g1", "g2"]}, [goal_at_risk, goal_off])

        ranked = prioritize_tasks([t], db=db)

        assert ranked[0].factors["goal_status_off_target"] == 1.0
        assert ranked[0].factors["goal_status_at_risk"] == 0.0

    def test_on_target_goal_no_status_boost(self):
        """on_target goal does not trigger at_risk or off_target factors."""
        t = _make_task()
        goal = _MockGoal("g1", "On Target Goal", status_value="on_target")
        db = _make_mock_db({t.id: ["g1"]}, [goal])

        ranked = prioritize_tasks([t], db=db)

        assert ranked[0].factors["goal_status_at_risk"] == 0.0
        assert ranked[0].factors["goal_status_off_target"] == 0.0

    def test_goal_urgency_increases_as_end_date_approaches(self):
        """goal_urgency factor is higher for a near-expiring goal."""
        now = datetime.now(timezone.utc)
        t_urgent = _make_task()
        t_far = _make_task()

        goal_urgent = _MockGoal("g1", "Urgent Goal", end_date=now + timedelta(days=2))
        goal_far = _MockGoal("g2", "Far Goal", end_date=now + timedelta(days=60))

        db_urgent = _make_mock_db({t_urgent.id: ["g1"]}, [goal_urgent])
        db_far = _make_mock_db({t_far.id: ["g2"]}, [goal_far])

        ranked_urgent = prioritize_tasks([t_urgent], db=db_urgent)
        ranked_far = prioritize_tasks([t_far], db=db_far)

        assert ranked_urgent[0].factors["goal_urgency"] > ranked_far[0].factors["goal_urgency"]

    def test_goal_urgency_zero_for_expired_end_date(self):
        """goal_urgency is 0.0 when goal.end_date is in the past."""
        now = datetime.now(timezone.utc)
        t = _make_task()
        goal = _MockGoal("g1", "Expired Goal", end_date=now - timedelta(days=1))
        db = _make_mock_db({t.id: ["g1"]}, [goal])

        ranked = prioritize_tasks([t], db=db)

        assert ranked[0].factors["goal_urgency"] == 0.0

    def test_multi_goal_urgency_uses_nearest(self):
        """For multi-goal tasks, goal_urgency reflects the nearest-expiring goal."""
        now = datetime.now(timezone.utc)
        t = _make_task()
        goal_near = _MockGoal("g1", "Near Goal", end_date=now + timedelta(days=3))
        goal_far = _MockGoal("g2", "Far Goal", end_date=now + timedelta(days=60))
        db = _make_mock_db({t.id: ["g1", "g2"]}, [goal_near, goal_far])

        ranked = prioritize_tasks([t], db=db)

        # Urgency should be driven by g1 (3 days), not g2 (60 days)
        from app.services.recommendations import _calculate_goal_urgency
        expected = _calculate_goal_urgency(goal_near, now)
        assert abs(ranked[0].factors["goal_urgency"] - expected) < 0.01

    def test_no_linked_goals_no_health_factors(self):
        """Tasks with no goal links have all goal health factors at 0."""
        t = _make_task()
        ranked = prioritize_tasks([t])

        assert ranked[0].factors["goal_status_at_risk"] == 0.0
        assert ranked[0].factors["goal_status_off_target"] == 0.0
        assert ranked[0].factors["goal_urgency"] == 0.0


# ---------------------------------------------------------------------------
# Why text tests
# ---------------------------------------------------------------------------

class TestWhyText:

    def test_why_includes_energy_match(self):
        """why mentions energy level when energy_match is active."""
        t = _make_task(energy="low")
        ranked = prioritize_tasks([t], energy="low")
        assert "low energy level" in ranked[0].why.lower()

    def test_why_includes_time_fit(self):
        """why mentions time window when time_fit is active."""
        t = _make_task(size=1)
        ranked = prioritize_tasks([t], time_window=30)
        assert "30m window" in ranked[0].why

    def test_why_includes_off_target(self):
        """why mentions 'off target' when goal_status_off_target is active."""
        t = _make_task()
        goal = _MockGoal("g1", "OT Goal", status_value="off_target")
        db = _make_mock_db({t.id: ["g1"]}, [goal])
        ranked = prioritize_tasks([t], db=db)
        assert "off target" in ranked[0].why.lower()

    def test_why_includes_at_risk(self):
        """why mentions 'at risk' when goal_status_at_risk is active."""
        t = _make_task()
        goal = _MockGoal("g1", "AR Goal", status_value="at_risk")
        db = _make_mock_db({t.id: ["g1"]}, [goal])
        ranked = prioritize_tasks([t], db=db)
        assert "at risk" in ranked[0].why.lower()

    def test_why_includes_goal_urgency(self):
        """why mentions goal due when urgency is high (>0.5)."""
        now = datetime.now(timezone.utc)
        t = _make_task()
        goal = _MockGoal("g1", "Urgent Goal", end_date=now + timedelta(days=2))
        db = _make_mock_db({t.id: ["g1"]}, [goal])
        ranked = prioritize_tasks([t], db=db)
        assert "goal due" in ranked[0].why.lower()

    def test_why_baseline_when_no_signals(self):
        """why defaults to baseline message when no factors apply."""
        t = _make_task()
        ranked = prioritize_tasks([t])
        assert ranked[0].why == "No strong signals (baseline order)"
