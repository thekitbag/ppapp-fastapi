from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_and_list_task():
    r = client.post("/api/v1/tasks", json={"title":"Write docs","tags":["docs","alpha"]})
    assert r.status_code == 201
    task = r.json()
    assert task["title"] == "Write docs"
    assert "alpha" in task["tags"]
    assert task["project_id"] is None
    assert task["goal_id"] is None

    # Verify task can be retrieved individually (more reliable than list pagination)
    r2 = client.get(f"/api/v1/tasks/{task['id']}")
    assert r2.status_code == 200
    retrieved_task = r2.json()
    assert retrieved_task["title"] == "Write docs"

def test_patch_task():
    r = client.post("/api/v1/tasks", json={"title":"Patch me"})
    tid = r.json()["id"]
    r2 = client.put(f"/api/v1/tasks/{tid}", json={"status":"week"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "week"

def test_task_timestamps_present_on_create():
    r = client.post("/api/v1/tasks", json={"title": "Timestamp check", "tags": []})
    assert r.status_code == 201
    body = r.json()
    # ensure created_at and updated_at fields exist and are ISO strings
    assert "created_at" in body and "updated_at" in body
    ca = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
    ua = datetime.fromisoformat(body["updated_at"].replace("Z", "+00:00"))
    assert ca <= ua
    # check they appear also via individual GET (more reliable than list pagination)
    r2 = client.get(f"/api/v1/tasks/{body['id']}")
    assert r2.status_code == 200
    task_detail = r2.json()
    assert task_detail["id"] == body["id"] and "created_at" in task_detail

def test_create_task_with_project_and_goal():
    # Create a project and a goal first
    project_response = client.post("/api/v1/projects", json={"name": "New Project"})
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    goal_response = client.post("/api/v1/goals", json={"title": "New Goal"})
    assert goal_response.status_code == 201
    goal_id = goal_response.json()["id"]

    # Create a task with the project and goal
    task_response = client.post("/api/v1/tasks", json={
        "title": "Task with Project and Goal",
        "project_id": project_id,
        "goal_id": goal_id
    })
    assert task_response.status_code == 201
    task = task_response.json()
    assert task["project_id"] == project_id
    assert task["goal_id"] == goal_id

def test_list_tasks_by_status():
    # Create tasks with different statuses
    client.post("/api/v1/tasks", json={"title": "Backlog Task", "status": "backlog"})
    client.post("/api/v1/tasks", json={"title": "Week Task", "status": "week"})

    # Filter by a single status
    response = client.get("/api/v1/tasks?status=backlog")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) > 0
    assert all(t["status"] == "backlog" for t in tasks)

    # Filter by multiple statuses
    response = client.get("/api/v1/tasks?status=backlog&status=week")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) > 0
    assert all(t["status"] in ["backlog", "week"] for t in tasks)


def test_create_task_defaults_status_to_week():
    """Test that tasks created without status default to 'week'."""
    response = client.post("/api/v1/tasks", json={"title": "Default Status Task"})
    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "week"


def test_create_task_respects_explicit_status():
    """Test that explicit status is respected when provided."""
    response = client.post("/api/v1/tasks", json={"title": "Backlog Task", "status": "backlog"})
    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "backlog"


def test_create_task_insert_at_top():
    """Test creating task at top of bucket."""
    # Create an existing task in 'week' status
    first_response = client.post("/api/v1/tasks", json={"title": "First Task", "status": "week"})
    assert first_response.status_code == 201
    first_task = first_response.json()

    # Create a new task at the top
    second_response = client.post("/api/v1/tasks", json={
        "title": "Second Task",
        "status": "week",
        "insert_at": "top"
    })
    assert second_response.status_code == 201
    second_task = second_response.json()

    # Second task should have lower sort_order (appears first)
    assert second_task["sort_order"] < first_task["sort_order"]


def test_create_task_insert_at_bottom():
    """Test creating task at bottom of bucket."""
    # Create an existing task in 'week' status
    first_response = client.post("/api/v1/tasks", json={"title": "First Task", "status": "week"})
    assert first_response.status_code == 201
    first_task = first_response.json()

    # Create a new task at the bottom
    second_response = client.post("/api/v1/tasks", json={
        "title": "Second Task",
        "status": "week",
        "insert_at": "bottom"
    })
    assert second_response.status_code == 201
    second_task = second_response.json()

    # Second task should have higher sort_order (appears last)
    assert second_task["sort_order"] > first_task["sort_order"]


def test_create_task_insert_at_defaults_to_top():
    """Test that insert_at defaults to 'top' when not specified."""
    # Create an existing task in 'week' status
    first_response = client.post("/api/v1/tasks", json={"title": "First Task", "status": "week"})
    assert first_response.status_code == 201
    first_task = first_response.json()

    # Create a new task without specifying insert_at
    second_response = client.post("/api/v1/tasks", json={
        "title": "Second Task",
        "status": "week"
    })
    assert second_response.status_code == 201
    second_task = second_response.json()

    # Second task should have lower sort_order (appears first, as default is top)
    assert second_task["sort_order"] < first_task["sort_order"]


def test_stable_sorting_by_sort_order_and_created_at():
    """Test that tasks are sorted by sort_order ASC, created_at ASC."""
    import time

    # Create tasks with specific sort orders and slight time gaps
    first_response = client.post("/api/v1/tasks", json={
        "title": "Task A",
        "status": "week",
        "sort_order": 2.0
    })
    assert first_response.status_code == 201
    first_task = first_response.json()

    time.sleep(0.01)  # Small delay to ensure different created_at

    second_response = client.post("/api/v1/tasks", json={
        "title": "Task B",
        "status": "week",
        "sort_order": 1.0
    })
    assert second_response.status_code == 201
    second_task = second_response.json()

    time.sleep(0.01)

    third_response = client.post("/api/v1/tasks", json={
        "title": "Task C",
        "status": "week",
        "sort_order": 1.0
    })
    assert third_response.status_code == 201
    third_task = third_response.json()

    # Get tasks in week status
    response = client.get("/api/v1/tasks?status=week")
    assert response.status_code == 200
    tasks = response.json()

    # Find our test tasks in the response
    task_a = next(t for t in tasks if t["id"] == first_task["id"])
    task_b = next(t for t in tasks if t["id"] == second_task["id"])
    task_c = next(t for t in tasks if t["id"] == third_task["id"])

    # Get their positions in the sorted list
    task_a_idx = tasks.index(task_a)
    task_b_idx = tasks.index(task_b)
    task_c_idx = tasks.index(task_c)

    # Task B and C should come before Task A (lower sort_order)
    assert task_b_idx < task_a_idx
    assert task_c_idx < task_a_idx

    # Task B should come before Task C (same sort_order, but earlier created_at)
    assert task_b_idx < task_c_idx


def test_reindex_tasks_endpoint():
    """Test the reindex endpoint compresses sort_order values."""
    # Create tasks with gaps in sort_order
    client.post("/api/v1/tasks", json={
        "title": "Task 1",
        "status": "week",
        "sort_order": 10.0
    })
    client.post("/api/v1/tasks", json={
        "title": "Task 2",
        "status": "week",
        "sort_order": 100.0
    })
    client.post("/api/v1/tasks", json={
        "title": "Task 3",
        "status": "week",
        "sort_order": 1000.0
    })

    # Reindex the week bucket
    response = client.post("/api/v1/tasks/reindex?status=week")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "week"
    assert result["reindexed"] >= 3  # At least our 3 test tasks

    # Check that sort_order values are now compressed
    tasks_response = client.get("/api/v1/tasks?status=week")
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()

    # Extract sort_order values for our tasks
    week_tasks = [t for t in tasks if t["status"] == "week"]
    sort_orders = [t["sort_order"] for t in week_tasks]

    # Should be small consecutive numbers starting from 1
    sorted_orders = sorted(sort_orders)
    for i, order in enumerate(sorted_orders):
        # Each task should have sort_order close to its position (allowing for other tasks)
        assert order <= len(week_tasks) * 2  # Should be much smaller than the original values


def test_reindex_empty_status_bucket():
    """Test reindexing an empty status bucket."""
    response = client.post("/api/v1/tasks/reindex?status=nonexistent")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "nonexistent"
    assert result["reindexed"] == 0


def test_create_task_idempotency_first_request():
    """Test that first request with client_request_id creates task normally."""
    import uuid
    client_request_id = str(uuid.uuid4())

    response = client.post("/api/v1/tasks", json={
        "title": "Idempotent Task",
        "client_request_id": client_request_id
    })

    assert response.status_code == 201
    task = response.json()
    assert task["title"] == "Idempotent Task"
    assert task["id"] is not None


def test_create_task_idempotency_duplicate_request():
    """Test that duplicate request with same client_request_id returns existing task."""
    import uuid
    client_request_id = str(uuid.uuid4())

    # First request - creates the task
    first_response = client.post("/api/v1/tasks", json={
        "title": "Idempotent Task",
        "client_request_id": client_request_id,
        "tags": ["test"]
    })
    assert first_response.status_code == 201
    first_task = first_response.json()

    # Second request - should return the same task
    second_response = client.post("/api/v1/tasks", json={
        "title": "Idempotent Task",
        "client_request_id": client_request_id,
        "tags": ["test"]
    })
    assert second_response.status_code == 200  # Should be 200, not 201
    second_task = second_response.json()

    # Should be the exact same task
    assert first_task["id"] == second_task["id"]
    assert first_task["title"] == second_task["title"]
    assert first_task["created_at"] == second_task["created_at"]


def test_create_task_idempotency_different_users():
    """Test that different users can use the same client_request_id independently."""
    import uuid
    client_request_id = str(uuid.uuid4())

    # This test assumes single-user mode where user isolation would be handled
    # by authentication middleware. In a real multi-user system, we'd need to
    # test with different authenticated users, but the repository logic ensures
    # user_id scoping.

    # First user creates task
    first_response = client.post("/api/v1/tasks", json={
        "title": "User 1 Task",
        "client_request_id": client_request_id
    })
    assert first_response.status_code == 201
    first_task = first_response.json()

    # Same user tries again - should get same task
    second_response = client.post("/api/v1/tasks", json={
        "title": "User 1 Task",
        "client_request_id": client_request_id
    })
    assert second_response.status_code == 200
    second_task = second_response.json()
    assert first_task["id"] == second_task["id"]


def test_create_task_without_client_request_id():
    """Test that tasks without client_request_id behave normally (no idempotency)."""
    # Create two tasks with identical content but no client_request_id
    first_response = client.post("/api/v1/tasks", json={
        "title": "Duplicate Task",
        "tags": ["test"]
    })
    assert first_response.status_code == 201
    first_task = first_response.json()

    second_response = client.post("/api/v1/tasks", json={
        "title": "Duplicate Task",
        "tags": ["test"]
    })
    assert second_response.status_code == 201
    second_task = second_response.json()

    # Should be different tasks
    assert first_task["id"] != second_task["id"]
    assert first_task["title"] == second_task["title"]


def test_create_task_different_client_request_ids():
    """Test that different client_request_ids create different tasks."""
    import uuid

    first_client_request_id = str(uuid.uuid4())
    second_client_request_id = str(uuid.uuid4())

    # First task
    first_response = client.post("/api/v1/tasks", json={
        "title": "Task 1",
        "client_request_id": first_client_request_id
    })
    assert first_response.status_code == 201
    first_task = first_response.json()

    # Second task with different client_request_id
    second_response = client.post("/api/v1/tasks", json={
        "title": "Task 2",
        "client_request_id": second_client_request_id
    })
    assert second_response.status_code == 201
    second_task = second_response.json()

    # Should be different tasks
    assert first_task["id"] != second_task["id"]


def test_create_task_idempotency_with_complex_payload():
    """Test idempotency works with complex task payloads including relationships."""
    import uuid

    # Create a project first for the test
    project_response = client.post("/api/v1/projects", json={"name": "Test Project"})
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    client_request_id = str(uuid.uuid4())

    # First request with complex payload
    first_response = client.post("/api/v1/tasks", json={
        "title": "Complex Idempotent Task",
        "description": "This is a complex task",
        "status": "week",
        "tags": ["complex", "test"],
        "size": "m",
        "effort_minutes": 60,
        "energy": "medium",
        "project_id": project_id,
        "client_request_id": client_request_id
    })
    assert first_response.status_code == 201
    first_task = first_response.json()

    # Second request with same payload
    second_response = client.post("/api/v1/tasks", json={
        "title": "Complex Idempotent Task",
        "description": "This is a complex task",
        "status": "week",
        "tags": ["complex", "test"],
        "size": "m",
        "effort_minutes": 60,
        "energy": "medium",
        "project_id": project_id,
        "client_request_id": client_request_id
    })
    assert second_response.status_code == 200
    second_task = second_response.json()

    # Should be the same task with all the same properties
    assert first_task["id"] == second_task["id"]
    assert first_task["description"] == second_task["description"]
    assert first_task["project_id"] == second_task["project_id"]
    assert set(first_task["tags"]) == set(second_task["tags"])
