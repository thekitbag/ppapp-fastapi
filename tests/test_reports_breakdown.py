"""Integration tests for GET /api/v1/reports/breakdown (REPORT-005)."""
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_START = "2020-01-01T00:00:00Z"
_END = "2099-12-31T23:59:59Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_goal(title, parent_goal_id=None, headers=None):
    payload = {"title": title}
    if parent_goal_id:
        payload["parent_goal_id"] = parent_goal_id
    r = client.post("/api/v1/goals/", json=payload, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_done_task(title, size, headers=None):
    """Create a task then PUT to done so completed_at is injected by the service."""
    r = client.post(
        "/api/v1/tasks",
        json={"title": title, "size": size},
        headers=headers or {},
    )
    assert r.status_code == 201, r.text
    task_id = r.json()["id"]
    r2 = client.put(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
        headers=headers or {},
    )
    assert r2.status_code == 200, r2.text
    return task_id


def _link(task_id, goal_id, headers=None):
    r = client.post(
        f"/api/v1/goals/{goal_id}/link-tasks",
        json={"task_ids": [task_id]},
        headers=headers or {},
    )
    assert r.status_code == 200, r.text


def _get_breakdown(params, headers=None):
    return client.get(
        "/api/v1/reports/breakdown",
        params=params,
        headers=headers or {},
    )


# ---------------------------------------------------------------------------
# Shape / contract tests
# ---------------------------------------------------------------------------

def test_root_breakdown_returns_200():
    r = _get_breakdown({"start_date": _START, "end_date": _END})
    assert r.status_code == 200


def test_response_has_required_fields():
    r = _get_breakdown({"start_date": _START, "end_date": _END})
    body = r.json()
    assert "parent_id" in body
    assert "total_impact" in body
    assert "breakdown" in body
    assert isinstance(body["breakdown"], list)


def test_parent_id_is_none_in_root_view():
    r = _get_breakdown({"start_date": _START, "end_date": _END})
    assert r.json()["parent_id"] is None


def test_breakdown_row_fields():
    # Ensure at least one goal exists so there's a row to inspect
    gid = _create_goal(f"Row fields test {uuid.uuid4()}")
    r = _get_breakdown({"start_date": _START, "end_date": _END})
    body = r.json()
    row = next((row for row in body["breakdown"] if row["goal_id"] == gid), None)
    assert row is not None
    assert "goal_id" in row
    assert "goal_title" in row
    assert "goal_type" in row
    assert "points" in row
    assert "percentage" in row
    assert "has_children" in row


def test_missing_start_date_returns_422():
    r = _get_breakdown({"end_date": _END})
    assert r.status_code == 422


def test_missing_end_date_returns_422():
    r = _get_breakdown({"start_date": _START})
    assert r.status_code == 422


def test_unknown_parent_goal_returns_404():
    r = _get_breakdown({
        "start_date": _START,
        "end_date": _END,
        "parent_goal_id": "totally-nonexistent-goal-id",
    })
    assert r.status_code == 404


def test_other_users_goal_as_parent_returns_404():
    """A goal owned by user_other is not accessible by the default test user."""
    other_h = {"x-test-user-id": "user_other"}
    gid = _create_goal("Other BD Goal", headers=other_h)

    r = _get_breakdown({
        "start_date": _START,
        "end_date": _END,
        "parent_goal_id": gid,
    })
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Functional tests (via API — shared test DB, additive data)
# ---------------------------------------------------------------------------

def test_root_view_includes_no_goal_row():
    """Root view always has a No Goal row."""
    r = _get_breakdown({"start_date": _START, "end_date": _END})
    body = r.json()
    no_goal = next((row for row in body["breakdown"] if row["goal_id"] is None), None)
    assert no_goal is not None
    assert no_goal["goal_title"] == "No Goal"
    assert no_goal["has_children"] is False


def test_root_view_counts_task_linked_to_root():
    gid = _create_goal(f"Root BD test {uuid.uuid4()}")
    tid = _create_done_task(f"BD Task {uuid.uuid4()}", size=5)
    _link(tid, gid)

    r = _get_breakdown({"start_date": _START, "end_date": _END})
    row = next(row for row in r.json()["breakdown"] if row["goal_id"] == gid)
    assert row["points"] == 5


def test_root_view_cascades_through_hierarchy():
    """Points at quarterly/weekly levels roll up to the annual root row."""
    annual_id = _create_goal(f"Annual Cascade {uuid.uuid4()}")
    q_id = _create_goal(f"Q Cascade {uuid.uuid4()}", parent_goal_id=annual_id)
    w_id = _create_goal(f"W Cascade {uuid.uuid4()}", parent_goal_id=q_id)

    t1 = _create_done_task(f"T cascade 1 {uuid.uuid4()}", size=3)
    t2 = _create_done_task(f"T cascade 2 {uuid.uuid4()}", size=5)
    _link(t1, q_id)
    _link(t2, w_id)

    r = _get_breakdown({"start_date": _START, "end_date": _END})
    annual_row = next(row for row in r.json()["breakdown"] if row["goal_id"] == annual_id)
    assert annual_row["points"] == 8  # 3 + 5 cascaded up


def test_drill_down_shows_immediate_children_only():
    """parent_goal_id returns only immediate children of that goal."""
    annual_id = _create_goal(f"Annual Drill {uuid.uuid4()}")
    q1_id = _create_goal(f"Q1 Drill {uuid.uuid4()}", parent_goal_id=annual_id)
    q2_id = _create_goal(f"Q2 Drill {uuid.uuid4()}", parent_goal_id=annual_id)
    _create_goal(f"W Drill {uuid.uuid4()}", parent_goal_id=q1_id)  # grandchild

    r = _get_breakdown({
        "start_date": _START,
        "end_date": _END,
        "parent_goal_id": annual_id,
    })
    body = r.json()
    assert body["parent_id"] == annual_id
    row_ids = {row["goal_id"] for row in body["breakdown"]}
    assert q1_id in row_ids
    assert q2_id in row_ids
    assert annual_id not in row_ids
    assert None not in row_ids  # no No Goal row at child level


def test_deepest_link_attribution_no_double_count():
    """Task linked to both parent and child counted once, attributed to child."""
    annual_id = _create_goal(f"Annual Deep {uuid.uuid4()}")
    q_id = _create_goal(f"Q Deep {uuid.uuid4()}", parent_goal_id=annual_id)
    w_id = _create_goal(f"W Deep {uuid.uuid4()}", parent_goal_id=q_id)

    tid = _create_done_task(f"Deep task {uuid.uuid4()}", size=8)
    _link(tid, q_id)
    _link(tid, w_id)  # also linked to child

    r = _get_breakdown({"start_date": _START, "end_date": _END})
    annual_row = next(row for row in r.json()["breakdown"] if row["goal_id"] == annual_id)
    # Task counted once (at weekly level, rolled up to annual)
    assert annual_row["points"] == 8

    # Confirm total_impact reflects no double-count by checking the annual subtree
    r2 = _get_breakdown({
        "start_date": _START,
        "end_date": _END,
        "parent_goal_id": annual_id,
    })
    q_row = next(row for row in r2.json()["breakdown"] if row["goal_id"] == q_id)
    assert q_row["points"] == 8  # counted once at Q level


def test_has_children_flag_set_correctly():
    annual_id = _create_goal(f"Annual HasChild {uuid.uuid4()}")
    _create_goal(f"Q HasChild {uuid.uuid4()}", parent_goal_id=annual_id)

    r = _get_breakdown({"start_date": _START, "end_date": _END})
    annual_row = next(row for row in r.json()["breakdown"] if row["goal_id"] == annual_id)
    assert annual_row["has_children"] is True
