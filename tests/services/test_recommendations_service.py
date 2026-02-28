"""Service-level tests for prioritize_tasks energy and time_window ranking behavior."""
import uuid
from datetime import datetime, timezone

import pytest

from app.models import Task, StatusEnum
from app.services.recommendations import prioritize_tasks


def _uid():
    return str(uuid.uuid4())


def _make_task(size=None, status="backlog"):
    return Task(
        id=f"task_{_uid()}",
        title=f"Task size={size}",
        user_id="svc-user-1",
        status=status,
        sort_order=0.0,
        size=size,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


class TestEnergyRanking:

    def test_energy_low_ranks_small_tasks_higher(self):
        """energy=low boosts tasks with size<=2 above larger tasks."""
        small = _make_task(size=1)
        large = _make_task(size=8)

        ranked = prioritize_tasks([large, small], energy="low")

        ids = [r.task.id for r in ranked]
        assert ids.index(small.id) < ids.index(large.id), (
            "Small task should rank higher than large task when energy=low"
        )

    def test_energy_medium_ranks_mid_size_tasks_higher(self):
        """energy=medium boosts tasks with size<=5 above larger tasks."""
        medium = _make_task(size=3)
        large = _make_task(size=8)

        ranked = prioritize_tasks([large, medium], energy="medium")

        ids = [r.task.id for r in ranked]
        assert ids.index(medium.id) < ids.index(large.id)

    def test_energy_high_ranks_large_tasks_higher(self):
        """energy=high boosts tasks with size>=5 above smaller tasks."""
        small = _make_task(size=1)
        large = _make_task(size=8)

        ranked = prioritize_tasks([small, large], energy="high")

        ids = [r.task.id for r in ranked]
        assert ids.index(large.id) < ids.index(small.id), (
            "Large task should rank higher than small task when energy=high"
        )

    def test_energy_none_no_fit_boost(self):
        """With no energy param, energy_fit is always 0."""
        task = _make_task(size=3)
        ranked = prioritize_tasks([task])
        assert ranked[0].factors["energy_fit"] == 0.0

    def test_energy_fit_factor_present_in_output(self):
        """factors dict always includes energy_fit and size_fit keys."""
        task = _make_task(size=3)
        ranked = prioritize_tasks([task], energy="low")
        assert "energy_fit" in ranked[0].factors
        assert "size_fit" in ranked[0].factors

    def test_energy_low_tasks_without_size_get_fit_bonus(self):
        """Tasks with size=None are treated as fitting low/medium energy."""
        no_size = _make_task(size=None)
        ranked = prioritize_tasks([no_size], energy="low")
        assert ranked[0].factors["energy_fit"] == 1.0

    def test_energy_high_tasks_without_size_get_no_boost(self):
        """Tasks with size=None do not get energy_fit for high (unknown effort)."""
        no_size = _make_task(size=None)
        ranked = prioritize_tasks([no_size], energy="high")
        assert ranked[0].factors["energy_fit"] == 0.0


class TestTimeWindowRanking:

    def test_time_window_boosts_small_tasks(self):
        """time_window=15 boosts tasks with size<=1 above larger ones."""
        tiny = _make_task(size=1)
        large = _make_task(size=5)

        ranked = prioritize_tasks([large, tiny], time_window=15)

        ids = [r.task.id for r in ranked]
        assert ids.index(tiny.id) < ids.index(large.id)

    def test_time_window_120_includes_medium_tasks(self):
        """time_window=120 boosts tasks with size<=5."""
        medium = _make_task(size=5)
        large = _make_task(size=8)

        ranked = prioritize_tasks([large, medium], time_window=120)

        ids = [r.task.id for r in ranked]
        assert ids.index(medium.id) < ids.index(large.id)

    def test_no_time_window_no_size_fit_boost(self):
        """Without time_window, size_fit is always 0."""
        task = _make_task(size=1)
        ranked = prioritize_tasks([task])
        assert ranked[0].factors["size_fit"] == 0.0

    def test_energy_and_time_window_combined(self):
        """Both energy and time_window can boost the same task."""
        fitting = _make_task(size=1)
        not_fitting = _make_task(size=8)

        ranked = prioritize_tasks([not_fitting, fitting], energy="low", time_window=15)

        ids = [r.task.id for r in ranked]
        assert ids.index(fitting.id) < ids.index(not_fitting.id)
        # Fitting task should have both boosts active
        top = next(r for r in ranked if r.task.id == fitting.id)
        assert top.factors["energy_fit"] == 1.0
        assert top.factors["size_fit"] == 1.0
