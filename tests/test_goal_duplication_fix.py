"""Test that goal duplication issue is fixed."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_goal_not_duplicated_with_legacy_goal_id():
    """Test that using legacy goal_id doesn't cause goal to appear twice in response."""
    # Create a weekly goal
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    # Create task with legacy goal_id (simulating frontend goals page behavior)
    task_response = client.post("/api/v1/tasks", json={
        "title": "Task from Goals Page",
        "goal_id": weekly_goal["id"]
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Verify goal only appears once - in the goals array, not duplicated
    assert len(task["goals"]) == 1
    assert task["goals"][0]["id"] == weekly_goal["id"]
    assert task["goals"][0]["title"] == "Weekly Goal"

    # The legacy goal_id field should be populated for backward compatibility
    assert task["goal_id"] == weekly_goal["id"]

    # But the goal should NOT appear twice (this was the bug)
    goal_ids_in_goals_array = [g["id"] for g in task["goals"]]
    assert goal_ids_in_goals_array.count(weekly_goal["id"]) == 1


def test_goal_not_duplicated_with_goals_array():
    """Test that using goals array doesn't cause duplication."""
    # Create a weekly goal
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    # Create task with new goals array
    task_response = client.post("/api/v1/tasks", json={
        "title": "Task with Goals Array",
        "goals": [weekly_goal["id"]]
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Verify goal appears exactly once
    assert len(task["goals"]) == 1
    assert task["goals"][0]["id"] == weekly_goal["id"]

    # Legacy field should also be set for backward compatibility
    assert task["goal_id"] == weekly_goal["id"]


def test_goal_not_duplicated_with_both_fields():
    """Test that using both goal_id and goals with same goal doesn't cause duplication."""
    # Create a weekly goal
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    # Create task with both goal_id and goals pointing to same goal
    task_response = client.post("/api/v1/tasks", json={
        "title": "Task with Duplicate Goal References",
        "goal_id": weekly_goal["id"],
        "goals": [weekly_goal["id"]]
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Verify goal appears exactly once despite being specified in both fields
    assert len(task["goals"]) == 1
    assert task["goals"][0]["id"] == weekly_goal["id"]
    assert task["goal_id"] == weekly_goal["id"]


def test_legacy_goal_id_priority_with_multiple_goals():
    """Test that when using both goal_id and goals, the legacy goal_id field reflects the original goal_id value."""
    # Create two weekly goals
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()

    weekly_goal1 = client.post("/api/v1/goals", json={
        "title": "Weekly Goal 1",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()
    weekly_goal2 = client.post("/api/v1/goals", json={
        "title": "Weekly Goal 2",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    # Create task with goals array and different goal_id
    task_response = client.post("/api/v1/tasks", json={
        "title": "Task with Priority Test",
        "goals": [weekly_goal1["id"]],
        "goal_id": weekly_goal2["id"]  # Different goal in legacy field
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Should have both goals linked
    assert len(task["goals"]) == 2
    goal_ids = [g["id"] for g in task["goals"]]
    assert weekly_goal1["id"] in goal_ids
    assert weekly_goal2["id"] in goal_ids

    # Legacy goal_id should reflect the original goal_id value for backward compatibility
    assert task["goal_id"] == weekly_goal2["id"]