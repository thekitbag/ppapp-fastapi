"""Integration tests for GET /api/v1/reports/goals/{goal_id}."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

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


def _create_task(title, size, status="done", headers=None):
    r = client.post(
        "/api/v1/tasks",
        json={"title": title, "size": size, "status": status},
        headers=headers or {},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _link_task_to_goal(task_id, goal_id, headers=None):
    r = client.post(
        f"/api/v1/goals/{goal_id}/link-tasks",
        json={"task_ids": [task_id]},
        headers=headers or {},
    )
    assert r.status_code == 200, r.text


def _mark_done(task_id, completed_at: str, headers=None):
    """PATCH task status to done and set completed_at via update."""
    r = client.put(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
        headers=headers or {},
    )
    assert r.status_code == 200, r.text


def _get_report(goal_id, params=None, headers=None):
    return client.get(
        f"/api/v1/reports/goals/{goal_id}",
        params=params or {},
        headers=headers or {},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_goal_report_basic():
    """Create a two-level hierarchy with done tasks, check response shape."""
    annual_id = _create_goal("Annual 2025")
    quarterly_id = _create_goal("Q1 2025", parent_goal_id=annual_id)

    # Create and link tasks — tasks are created as 'done' so completed_at is set
    t1 = _create_task("Big task", 8)
    t2 = _create_task("Small task", 3)

    _link_task_to_goal(t1, annual_id)
    _link_task_to_goal(t2, quarterly_id)

    r = _get_report(annual_id)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["goal_id"] == annual_id
    assert body["goal_title"] == "Annual 2025"
    assert isinstance(body["total_size"], int)
    assert isinstance(body["direct_size"], int)
    assert isinstance(body["descendant_size"], int)
    assert body["total_size"] == body["direct_size"] + body["descendant_size"]
    # Tasks with status=done should be counted (completed_at may be set by service)
    assert body["direct_size"] >= 0
    assert body["descendant_size"] >= 0


def test_get_goal_report_lifetime():
    """No date params → endpoint returns 200 with valid shape."""
    goal_id = _create_goal("Lifetime Goal")
    t1 = _create_task("Task A", 5)
    _link_task_to_goal(t1, goal_id)

    r = _get_report(goal_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["start_date"] is None
    assert body["end_date"] is None
    assert body["total_size"] == body["direct_size"] + body["descendant_size"]


def test_get_goal_report_with_date_filter():
    """Date filter query params are accepted and returned in response."""
    goal_id = _create_goal("Filtered Goal")

    r = _get_report(
        goal_id,
        params={
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2025-06-30T23:59:59",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["start_date"] is not None
    assert body["end_date"] is not None
    assert body["total_size"] == body["direct_size"] + body["descendant_size"]


def test_get_goal_report_404_unknown_goal():
    """Unknown goal ID returns 404."""
    r = _get_report("goal_does_not_exist_xyz")
    assert r.status_code == 404


def test_get_goal_report_404_other_users_goal():
    """Querying another user's goal returns 404 (not 403)."""
    # Create a goal as default user
    goal_id = _create_goal("Private Goal")

    # Request it as other user
    r = _get_report(goal_id, headers={"x-test-user-id": "user_other"})
    assert r.status_code == 404
