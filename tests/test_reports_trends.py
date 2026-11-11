"""Integration tests for GET /api/v1/reports/trends (REPORT-006).

Tests pin completed_at into a far-future year so they never collide with the
"completed now" tasks the rest of the suite creates in the shared test.db.
"""
import uuid
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import Task

client = TestClient(app)
_engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

H = {"x-test-user-id": "user_other"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_goal(title, parent_goal_id=None, headers=None):
    payload = {"title": title}
    if parent_goal_id:
        payload["parent_goal_id"] = parent_goal_id
    r = client.post("/api/v1/goals/", json=payload, headers=headers or H)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_done_task(title, size, completed_at, headers=None):
    """Create a task, mark it done, then pin completed_at to an exact timestamp."""
    r = client.post(
        "/api/v1/tasks",
        json={"title": title, "size": size},
        headers=headers or H,
    )
    assert r.status_code == 201, r.text
    task_id = r.json()["id"]
    r2 = client.put(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
        headers=headers or H,
    )
    assert r2.status_code == 200, r2.text

    db = _SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        assert task is not None
        task.completed_at = completed_at
        db.commit()
    finally:
        db.close()
    return task_id


def _link(task_id, goal_id, headers=None):
    r = client.post(
        f"/api/v1/goals/{goal_id}/link-tasks",
        json={"task_ids": [task_id]},
        headers=headers or H,
    )
    assert r.status_code == 200, r.text


def _trends(params, headers=None):
    return client.get("/api/v1/reports/trends", params=params, headers=headers or H)


def _window(year, start_month=1, start_day=1, end_month=12, end_day=31):
    return {
        "start_date": f"{year}-{start_month:02d}-{start_day:02d}T00:00:00",
        "end_date": f"{year}-{end_month:02d}-{end_day:02d}T23:59:59",
    }


def _bucket(body, label):
    return next(b for b in body["buckets"] if b["label"] == label)


def _series(body, title):
    return next(s for s in body["series"] if s["goal_title"] == title)


# ---------------------------------------------------------------------------
# Contract / validation
# ---------------------------------------------------------------------------

def test_missing_dates_returns_422():
    assert _trends({}).status_code == 422
    assert _trends({"start_date": "2031-01-01T00:00:00"}).status_code == 422
    assert _trends({"end_date": "2031-01-31T23:59:59"}).status_code == 422


def test_response_shape():
    r = _trends({**_window(2098, 1, 1, 1, 7), "granularity": "day"})
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("start_date", "end_date", "granularity", "parent_id",
                "total_points", "buckets", "series", "stats"):
        assert key in body, key
    for key in ("total_points", "task_count", "days_in_period", "active_days",
                "avg_points_per_day", "avg_points_per_active_day",
                "avg_points_per_week", "best_day", "best_day_points"):
        assert key in body["stats"], key


def test_invalid_granularity_returns_400():
    r = _trends({**_window(2098, 1, 1, 1, 7), "granularity": "fortnight"})
    assert r.status_code == 400, r.text


def test_granularity_defaults_to_day():
    r = _trends(_window(2098, 1, 1, 1, 7))
    assert r.status_code == 200, r.text
    assert r.json()["granularity"] == "day"


def test_end_before_start_returns_400():
    r = _trends({
        "start_date": "2098-02-01T00:00:00",
        "end_date": "2098-01-01T00:00:00",
        "granularity": "day",
    })
    assert r.status_code == 400, r.text


def test_too_many_buckets_returns_400():
    """A multi-year range by day exceeds the bucket cap rather than returning a huge payload."""
    r = _trends({
        "start_date": "2090-01-01T00:00:00",
        "end_date": "2095-01-01T00:00:00",
        "granularity": "day",
    })
    assert r.status_code == 400, r.text
    assert "granularity" in r.text


def test_unknown_parent_goal_id_returns_404():
    r = _trends({**_window(2098, 1, 1, 1, 7), "parent_goal_id": "goal_does_not_exist"})
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------

def test_buckets_are_dense_including_empty_days():
    """Idle days are present with 0 points, so the chart shows gaps."""
    r = _trends({**_window(2098, 3, 1, 3, 5), "granularity": "day"})
    body = r.json()
    assert len(body["buckets"]) == 5
    assert [b["label"] for b in body["buckets"]] == ["Mar 1", "Mar 2", "Mar 3", "Mar 4", "Mar 5"]
    assert all(b["points"] == 0 for b in body["buckets"])


def test_day_buckets_carry_points_and_task_count():
    _create_done_task("trend-day-a", 5, datetime(2031, 1, 6, 9, 0))
    _create_done_task("trend-day-b", 3, datetime(2031, 1, 6, 18, 30))
    _create_done_task("trend-day-c", 2, datetime(2031, 1, 8, 11, 0))

    body = _trends({**_window(2031, 1, 5, 1, 11), "granularity": "day"}).json()

    assert _bucket(body, "Jan 6")["points"] == 8
    assert _bucket(body, "Jan 6")["task_count"] == 2
    assert _bucket(body, "Jan 7")["points"] == 0
    assert _bucket(body, "Jan 8")["points"] == 2
    assert body["total_points"] == 10


def test_week_buckets_start_on_monday():
    # 2031-02-03 is a Monday; 2031-02-09 is the Sunday that closes that week.
    _create_done_task("trend-week-a", 8, datetime(2031, 2, 5, 12, 0))
    _create_done_task("trend-week-b", 5, datetime(2031, 2, 9, 23, 0))
    _create_done_task("trend-week-c", 1, datetime(2031, 2, 10, 1, 0))

    body = _trends({**_window(2031, 2, 3, 2, 16), "granularity": "week"}).json()

    labels = [b["label"] for b in body["buckets"]]
    assert labels[0] == "Feb 3–9"
    assert _bucket(body, "Feb 3–9")["points"] == 13
    assert _bucket(body, "Feb 10–16")["points"] == 1


def test_week_bucket_spanning_two_months_labels_both():
    # Mon 2098-04-28 .. Sun 2098-05-04 is one week straddling the month boundary
    body = _trends({**_window(2098, 4, 28, 5, 4), "granularity": "week"}).json()
    assert [b["label"] for b in body["buckets"]] == ["Apr 28–May 4"]


def test_month_buckets():
    _create_done_task("trend-month-a", 13, datetime(2031, 3, 15, 10, 0))
    _create_done_task("trend-month-b", 2, datetime(2031, 4, 2, 10, 0))

    body = _trends({**_window(2031, 3, 1, 5, 31), "granularity": "month"}).json()

    assert [b["label"] for b in body["buckets"]] == ["Mar 2031", "Apr 2031", "May 2031"]
    assert _bucket(body, "Mar 2031")["points"] == 13
    assert _bucket(body, "Apr 2031")["points"] == 2
    assert _bucket(body, "May 2031")["points"] == 0


def test_bucket_covers_partial_first_bucket():
    """A range starting mid-week still opens on that week's Monday."""
    body = _trends({**_window(2098, 6, 11, 6, 15), "granularity": "week"}).json()
    # 2098-06-11 falls in the week of Monday 2098-06-09
    assert body["buckets"][0]["label"] == "Jun 9–15"


def test_tasks_outside_range_are_excluded():
    _create_done_task("trend-outside", 21, datetime(2031, 6, 1, 12, 0))
    body = _trends({**_window(2031, 7, 1, 7, 31), "granularity": "day"}).json()
    assert body["total_points"] == 0


# ---------------------------------------------------------------------------
# Per-goal series
# ---------------------------------------------------------------------------

def test_series_split_by_goal_and_aligned_to_buckets():
    root = _create_goal("ZZ Trend Root A")
    t1 = _create_done_task("series-a1", 5, datetime(2031, 8, 4, 9, 0))
    t2 = _create_done_task("series-a2", 3, datetime(2031, 8, 6, 9, 0))
    _link(t1, root)
    _link(t2, root)

    body = _trends({**_window(2031, 8, 4, 8, 6), "granularity": "day"}).json()
    s = _series(body, "ZZ Trend Root A")

    assert len(s["values"]) == len(body["buckets"])
    assert s["values"] == [5, 0, 3]
    assert s["points"] == 8
    assert s["is_no_goal"] is False


def test_unlinked_tasks_land_in_no_goal_series():
    _create_done_task("series-nogoal", 2, datetime(2031, 9, 3, 9, 0))
    body = _trends({**_window(2031, 9, 1, 9, 30), "granularity": "day"}).json()
    s = _series(body, "No Goal")
    assert s["goal_id"] is None
    assert s["is_no_goal"] is True
    assert s["points"] == 2


def test_series_sum_equals_bucket_totals():
    root = _create_goal("ZZ Trend Root B")
    t1 = _create_done_task("sum-a", 8, datetime(2031, 10, 7, 9, 0))
    _link(t1, root)
    _create_done_task("sum-b", 5, datetime(2031, 10, 7, 10, 0))

    body = _trends({**_window(2031, 10, 1, 10, 31), "granularity": "day"}).json()

    for i, bucket in enumerate(body["buckets"]):
        assert sum(s["values"][i] for s in body["series"]) == bucket["points"]
    assert sum(s["points"] for s in body["series"]) == body["total_points"]


def test_zero_point_goals_are_omitted_from_series():
    _create_goal("ZZ Trend Silent Goal")
    body = _trends({**_window(2098, 8, 1, 8, 7), "granularity": "day"}).json()
    assert all(s["goal_title"] != "ZZ Trend Silent Goal" for s in body["series"])


def test_order_index_is_stable_across_periods():
    """A goal keeps its order_index when the period changes, so its colour can't move."""
    root = _create_goal("ZZ Trend Stable")
    t1 = _create_done_task("stable-1", 3, datetime(2031, 11, 4, 9, 0))
    t2 = _create_done_task("stable-2", 5, datetime(2031, 12, 4, 9, 0))
    _link(t1, root)
    _link(t2, root)

    nov = _trends({**_window(2031, 11, 1, 11, 30), "granularity": "day"}).json()
    dec = _trends({**_window(2031, 12, 1, 12, 31), "granularity": "day"}).json()

    assert _series(nov, "ZZ Trend Stable")["order_index"] == \
        _series(dec, "ZZ Trend Stable")["order_index"]


def test_points_roll_up_to_deepest_goal_in_scope():
    """Mirrors breakdown attribution: a child-linked task counts under its root row."""
    root = _create_goal("ZZ Trend Parent")
    child = _create_goal("ZZ Trend Child", parent_goal_id=root)
    t = _create_done_task("rollup-task", 13, datetime(2032, 1, 7, 9, 0))
    _link(t, child)

    body = _trends({**_window(2032, 1, 1, 1, 31), "granularity": "day"}).json()
    assert _series(body, "ZZ Trend Parent")["points"] == 13


def test_drill_down_scopes_series_to_children():
    root = _create_goal("ZZ Trend Drill Root")
    child_a = _create_goal("ZZ Trend Drill A", parent_goal_id=root)
    child_b = _create_goal("ZZ Trend Drill B", parent_goal_id=root)
    ta = _create_done_task("drill-a", 8, datetime(2032, 2, 3, 9, 0))
    tb = _create_done_task("drill-b", 5, datetime(2032, 2, 4, 9, 0))
    _link(ta, child_a)
    _link(tb, child_b)
    # An unlinked task that must NOT appear in the drilled view
    _create_done_task("drill-unlinked", 21, datetime(2032, 2, 5, 9, 0))

    body = _trends({
        **_window(2032, 2, 1, 2, 28),
        "granularity": "day",
        "parent_goal_id": root,
    }).json()

    assert body["parent_id"] == root
    titles = {s["goal_title"] for s in body["series"]}
    assert titles == {"ZZ Trend Drill A", "ZZ Trend Drill B"}
    assert body["total_points"] == 13
    assert _series(body, "ZZ Trend Drill A")["points"] == 8


def test_trends_and_breakdown_agree_on_totals():
    """The two views share one attribution path — their per-goal points must match."""
    root = _create_goal("ZZ Trend Agree")
    child = _create_goal("ZZ Trend Agree Child", parent_goal_id=root)
    t1 = _create_done_task("agree-1", 8, datetime(2032, 3, 2, 9, 0))
    t2 = _create_done_task("agree-2", 3, datetime(2032, 3, 9, 9, 0))
    _link(t1, root)
    _link(t2, child)
    _create_done_task("agree-unlinked", 2, datetime(2032, 3, 10, 9, 0))

    window = _window(2032, 3, 1, 3, 31)
    trends = _trends({**window, "granularity": "day"}).json()
    breakdown = client.get("/api/v1/reports/breakdown", params=window, headers=H).json()

    assert trends["total_points"] == breakdown["total_impact"]
    trend_points = {s["goal_title"]: s["points"] for s in trends["series"]}
    for row in breakdown["breakdown"]:
        if row["points"] == 0:
            continue
        assert trend_points[row["goal_title"]] == row["points"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_averages_over_calendar_days():
    _create_done_task("avg-a", 8, datetime(2032, 4, 5, 9, 0))
    _create_done_task("avg-b", 2, datetime(2032, 4, 6, 9, 0))

    # 2032-04-01 .. 2032-04-10 is 10 days
    stats = _trends({**_window(2032, 4, 1, 4, 10), "granularity": "day"}).json()["stats"]

    assert stats["total_points"] == 10
    assert stats["task_count"] == 2
    assert stats["days_in_period"] == 10
    assert stats["active_days"] == 2
    assert stats["avg_points_per_day"] == 1.0
    assert stats["avg_points_per_active_day"] == 5.0
    assert stats["avg_points_per_week"] == 7.0


def test_stats_identical_across_granularities():
    """Rolling the chart up to weeks must not change what the averages mean."""
    _create_done_task("gran-a", 5, datetime(2032, 5, 4, 9, 0))
    _create_done_task("gran-b", 3, datetime(2032, 5, 18, 9, 0))

    window = _window(2032, 5, 1, 5, 28)
    by_day = _trends({**window, "granularity": "day"}).json()["stats"]
    by_week = _trends({**window, "granularity": "week"}).json()["stats"]

    assert by_day == by_week


def test_best_day_reports_peak_and_points():
    _create_done_task("best-a", 3, datetime(2032, 6, 7, 9, 0))
    _create_done_task("best-b", 13, datetime(2032, 6, 9, 9, 0))
    _create_done_task("best-c", 2, datetime(2032, 6, 9, 17, 0))

    stats = _trends({**_window(2032, 6, 1, 6, 30), "granularity": "day"}).json()["stats"]

    assert stats["best_day_points"] == 15
    assert stats["best_day"].startswith("2032-06-09")


def test_empty_period_stats_are_zero_without_dividing_by_zero():
    stats = _trends({**_window(2098, 9, 1, 9, 30), "granularity": "day"}).json()["stats"]

    assert stats["total_points"] == 0
    assert stats["active_days"] == 0
    assert stats["avg_points_per_day"] == 0
    assert stats["avg_points_per_active_day"] == 0
    assert stats["avg_points_per_week"] == 0
    assert stats["best_day"] is None
    assert stats["best_day_points"] == 0


def test_single_day_period_does_not_divide_by_zero():
    body = _trends({
        "start_date": "2098-10-01T08:00:00",
        "end_date": "2098-10-01T17:00:00",
        "granularity": "day",
    }).json()
    assert body["stats"]["days_in_period"] == 1
    assert len(body["buckets"]) == 1


# ---------------------------------------------------------------------------
# Multi-tenant isolation
# ---------------------------------------------------------------------------

def test_other_users_points_are_not_visible():
    mine = _create_goal("ZZ Trend Isolation Mine", headers=H)
    t = _create_done_task("iso-mine", 8, datetime(2032, 7, 5, 9, 0), headers=H)
    _link(t, mine, headers=H)

    other = {"x-test-user-id": "user_test"}
    body = _trends({**_window(2032, 7, 1, 7, 31), "granularity": "day"}, headers=other).json()

    assert body["total_points"] == 0
    assert all(s["goal_title"] != "ZZ Trend Isolation Mine" for s in body["series"])


def test_drilling_into_another_users_goal_returns_404():
    mine = _create_goal("ZZ Trend Isolation Drill", headers=H)
    other = {"x-test-user-id": "user_test"}
    r = _trends(
        {**_window(2032, 7, 1, 7, 31), "parent_goal_id": mine},
        headers=other,
    )
    assert r.status_code == 404, r.text
