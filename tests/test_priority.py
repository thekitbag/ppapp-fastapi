from datetime import datetime, timedelta, timezone
from app.services.recommendations import prioritize_tasks
from types import SimpleNamespace

class _Tag(SimpleNamespace):
    pass

class _Task(SimpleNamespace):
    pass

def _mk_task(title, status="inbox", tags=None, hard_due_at=None, soft_due_at=None, sort_order=0, created_at=None):
    return _Task(
        id=title,
        title=title,
        status=SimpleNamespace(value=status),
        tags=[_Tag(name=t) for t in (tags or [])],
        hard_due_at=hard_due_at,
        soft_due_at=soft_due_at,
        sort_order=sort_order,
        created_at=created_at or datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        effort_minutes=None,
    )

def test_prioritize_tasks_simple_formula():
    now = datetime.now(timezone.utc)
    t1 = _mk_task("A inbox no due", status="inbox", sort_order=100)
    t2 = _mk_task("B todo due soon goal", status="todo", tags=["goal"], hard_due_at=now + timedelta(hours=2), sort_order=500)
    t3 = _mk_task("C todo no due", status="todo", sort_order=10)
    ranked = prioritize_tasks([t1, t2, t3])
    # B has +10 (todo) +5 (due soon) +2 (goal) = 17 -> 100
    # C has +10 (todo) = 10 -> ~59
    # A has 0 -> 0
    assert ranked[0].task.title == "B todo due soon goal"
    assert ranked[0].score == 100
    assert ranked[0].factors["due_proximity"] == 1
    assert ranked[0].factors["goal_align"] == 1
    assert ranked[0].factors["status_boost"] == 1
