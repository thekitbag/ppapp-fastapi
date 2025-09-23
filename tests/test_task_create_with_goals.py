"""Test task creation with goal linking functionality."""
from fastapi.testclient import TestClient
from app.main import app
import uuid

client = TestClient(app)


def test_create_task_with_single_goal():
    """Test creating a task with a single goal in the goals array."""
    # Create a weekly goal to link to
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

    # Create task with goal link
    task_response = client.post("/api/v1/tasks", json={
        "title": "Test Task with Goal",
        "goals": [weekly_goal["id"]]
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Verify task was created with goal link
    assert task["title"] == "Test Task with Goal"
    assert len(task["goals"]) == 1
    assert task["goals"][0]["id"] == weekly_goal["id"]
    assert task["goals"][0]["title"] == "Weekly Goal"


def test_create_task_with_multiple_goals():
    """Test creating a task with multiple goals."""
    # Create multiple weekly goals
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

    # Create task with multiple goal links
    task_response = client.post("/api/v1/tasks", json={
        "title": "Multi-Goal Task",
        "goals": [weekly_goal1["id"], weekly_goal2["id"]]
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Verify task was created with multiple goal links
    assert task["title"] == "Multi-Goal Task"
    assert len(task["goals"]) == 2
    goal_ids = [g["id"] for g in task["goals"]]
    assert weekly_goal1["id"] in goal_ids
    assert weekly_goal2["id"] in goal_ids


def test_create_task_with_legacy_goal_id():
    """Test creating a task with legacy goal_id field for backward compatibility."""
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

    # Create task with legacy goal_id
    task_response = client.post("/api/v1/tasks", json={
        "title": "Legacy Goal ID Task",
        "goal_id": weekly_goal["id"]
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Verify task was created with goal link
    assert task["title"] == "Legacy Goal ID Task"
    assert task["goal_id"] == weekly_goal["id"]  # Legacy field maintained
    assert len(task["goals"]) == 1
    assert task["goals"][0]["id"] == weekly_goal["id"]


def test_create_task_with_both_goals_and_goal_id():
    """Test creating a task with both goals array and goal_id (should link to both)."""
    # Create weekly goals
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

    # Create task with both fields
    task_response = client.post("/api/v1/tasks", json={
        "title": "Combined Goals Task",
        "goals": [weekly_goal1["id"]],
        "goal_id": weekly_goal2["id"]
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Verify task was created with links to both goals
    assert task["title"] == "Combined Goals Task"
    assert task["goal_id"] == weekly_goal2["id"]  # Legacy field maintained
    assert len(task["goals"]) == 2
    goal_ids = [g["id"] for g in task["goals"]]
    assert weekly_goal1["id"] in goal_ids
    assert weekly_goal2["id"] in goal_ids


def test_create_task_with_duplicate_goals():
    """Test creating a task with duplicate goal IDs (should deduplicate)."""
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

    # Create task with duplicate goal IDs
    task_response = client.post("/api/v1/tasks", json={
        "title": "Duplicate Goals Task",
        "goals": [weekly_goal["id"], weekly_goal["id"]],
        "goal_id": weekly_goal["id"]  # Same goal again
    })

    assert task_response.status_code == 201
    task = task_response.json()

    # Verify task was created with only one link (deduplicated)
    assert task["title"] == "Duplicate Goals Task"
    assert len(task["goals"]) == 1
    assert task["goals"][0]["id"] == weekly_goal["id"]


def test_create_task_with_invalid_goal_type():
    """Test creating a task with non-weekly goal should fail."""
    # Create an annual goal (not weekly)
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()

    # Try to create task linked to annual goal
    task_response = client.post("/api/v1/tasks", json={
        "title": "Invalid Goal Type Task",
        "goals": [annual_goal["id"]]
    })

    assert task_response.status_code == 400
    error = task_response.json()
    assert "Only weekly goals can have tasks linked" in error["error"]["message"]


def test_create_task_with_nonexistent_goal():
    """Test creating a task with non-existent goal ID should fail."""
    fake_goal_id = f"goal_{uuid.uuid4()}"

    task_response = client.post("/api/v1/tasks", json={
        "title": "Non-existent Goal Task",
        "goals": [fake_goal_id]
    })

    assert task_response.status_code == 400
    error = task_response.json()
    assert "Goals not found" in error["error"]["message"]


def test_create_task_without_goals():
    """Test creating a task without any goals still works."""
    task_response = client.post("/api/v1/tasks", json={
        "title": "No Goals Task"
    })

    assert task_response.status_code == 201
    task = task_response.json()

    assert task["title"] == "No Goals Task"
    assert task["goal_id"] is None
    assert len(task["goals"]) == 0


def test_create_task_with_client_request_id_and_goals():
    """Test idempotent task creation with goals linking."""
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

    client_request_id = f"test-{uuid.uuid4()}"

    # Create task first time
    task_response1 = client.post("/api/v1/tasks", json={
        "title": "Idempotent Goals Task",
        "goals": [weekly_goal["id"]],
        "client_request_id": client_request_id
    })

    assert task_response1.status_code == 201
    task1 = task_response1.json()

    # Create task second time with same client_request_id
    task_response2 = client.post("/api/v1/tasks", json={
        "title": "Idempotent Goals Task",
        "goals": [weekly_goal["id"]],
        "client_request_id": client_request_id
    })

    assert task_response2.status_code == 200  # Idempotent: returns existing task
    task2 = task_response2.json()

    # Should return the same task
    assert task1["id"] == task2["id"]
    assert len(task2["goals"]) == 1
    assert task2["goals"][0]["id"] == weekly_goal["id"]


def test_create_task_quarterly_goal_fails():
    """Test that linking to quarterly goal fails with appropriate error."""
    # Create quarterly goal
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()

    # Try to create task linked to quarterly goal
    task_response = client.post("/api/v1/tasks", json={
        "title": "Quarterly Goal Task",
        "goals": [quarterly_goal["id"]]
    })

    assert task_response.status_code == 400
    error = task_response.json()
    assert "Only weekly goals can have tasks linked" in error["error"]["message"]
    assert "quarterly" in error["error"]["message"]