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

    r2 = client.get("/api/v1/tasks")
    assert r2.status_code == 200
    lst = r2.json()
    assert any(t["id"] == task["id"] for t in lst)

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
    # check they appear also via GET /tasks
    r2 = client.get("/api/v1/tasks")
    assert any(t["id"] == body["id"] and "created_at" in t for t in r2.json())

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
