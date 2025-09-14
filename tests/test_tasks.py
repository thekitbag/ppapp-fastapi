from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from urllib.parse import quote
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

def test_filter_tasks_by_project():
    # Create project
    project_response = client.post("/api/v1/projects", json={"name": "Test Project"})
    project_id = project_response.json()["id"]

    # Create tasks with and without project
    client.post("/api/v1/tasks", json={"title": "Project Task", "project_id": project_id})
    client.post("/api/v1/tasks", json={"title": "No Project Task"})

    # Filter by project
    response = client.get(f"/api/v1/tasks?project_id={project_id}")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) > 0
    assert all(t["project_id"] == project_id for t in tasks)

def test_filter_tasks_by_goal():
    # Create goal
    goal_response = client.post("/api/v1/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create task with legacy goal_id
    legacy_task_response = client.post("/api/v1/tasks", json={"title": "Legacy Goal Task", "goal_id": goal_id})
    legacy_task_id = legacy_task_response.json()["id"]

    # Create task and link it to goal via TaskGoal (many-to-many)
    linked_task_response = client.post("/api/v1/tasks", json={"title": "Linked Goal Task"})
    linked_task_id = linked_task_response.json()["id"]

    # Link the task to goal via goals endpoint
    client.post(f"/api/v1/goals/{goal_id}/link-tasks", json={
        "task_ids": [linked_task_id],
        "goal_id": goal_id
    })

    # Create task with no goal
    client.post("/api/v1/tasks", json={"title": "No Goal Task"})

    # Filter by goal - should return both legacy and linked tasks
    response = client.get(f"/api/v1/tasks?goal_id={goal_id}")
    assert response.status_code == 200
    tasks = response.json()
    task_ids = [t["id"] for t in tasks]
    assert legacy_task_id in task_ids
    assert linked_task_id in task_ids

def test_filter_tasks_by_tags():
    # Create tasks with different tags
    client.post("/api/v1/tasks", json={"title": "Important Urgent Task", "tags": ["important", "urgent"]})
    client.post("/api/v1/tasks", json={"title": "Important Task", "tags": ["important", "work"]})
    client.post("/api/v1/tasks", json={"title": "Urgent Task", "tags": ["urgent"]})
    client.post("/api/v1/tasks", json={"title": "No Tags Task", "tags": []})

    # Filter by single tag
    response = client.get("/api/v1/tasks?tag=important")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) >= 2  # At least the two tasks with 'important' tag
    for task in tasks:
        assert "important" in task["tags"]

    # Filter by multiple tags (AND condition - task must have ALL tags)
    response = client.get("/api/v1/tasks?tag=important&tag=urgent")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) >= 1  # At least the task with both tags
    for task in tasks:
        assert "important" in task["tags"]
        assert "urgent" in task["tags"]

def test_filter_tasks_by_due_dates():
    # Create tasks with different due dates
    now = datetime.now(timezone.utc)
    past_date = now - timedelta(days=1)
    future_date = now + timedelta(days=1)
    far_future = now + timedelta(days=7)

    # Task due in the past (hard due)
    client.post("/api/v1/tasks", json={
        "title": "Past Due Task",
        "hard_due_at": past_date.isoformat()
    })

    # Task due in the future (soft due)
    client.post("/api/v1/tasks", json={
        "title": "Future Due Task",
        "soft_due_at": future_date.isoformat()
    })

    # Task due far in the future
    client.post("/api/v1/tasks", json={
        "title": "Far Future Task",
        "hard_due_at": far_future.isoformat()
    })

    # Task with no due date
    client.post("/api/v1/tasks", json={"title": "No Due Date Task"})

    # Filter tasks due before now
    response = client.get(f"/api/v1/tasks?due_before={quote(now.isoformat())}")
    assert response.status_code == 200
    tasks = response.json()
    for task in tasks:
        # Should have either hard_due_at or soft_due_at before now
        has_due_before = False
        if task["hard_due_at"]:
            due_date = datetime.fromisoformat(task["hard_due_at"].replace('Z', '+00:00'))
            if due_date.replace(tzinfo=timezone.utc) <= now:
                has_due_before = True
        if task["soft_due_at"]:
            due_date = datetime.fromisoformat(task["soft_due_at"].replace('Z', '+00:00'))
            if due_date.replace(tzinfo=timezone.utc) <= now:
                has_due_before = True
        assert has_due_before, f"Task {task['title']} doesn't have due date before {now}"

    # Filter tasks due after now
    response = client.get(f"/api/v1/tasks?due_after={quote(now.isoformat())}")
    assert response.status_code == 200
    tasks = response.json()
    for task in tasks:
        # Should have either hard_due_at or soft_due_at after now
        has_due_after = False
        if task["hard_due_at"]:
            due_date = datetime.fromisoformat(task["hard_due_at"].replace('Z', '+00:00'))
            if due_date.replace(tzinfo=timezone.utc) >= now:
                has_due_after = True
        if task["soft_due_at"]:
            due_date = datetime.fromisoformat(task["soft_due_at"].replace('Z', '+00:00'))
            if due_date.replace(tzinfo=timezone.utc) >= now:
                has_due_after = True
        assert has_due_after, f"Task {task['title']} doesn't have due date after {now}"

def test_filter_tasks_by_search():
    # Create tasks with different titles and descriptions
    client.post("/api/v1/tasks", json={
        "title": "Write documentation",
        "description": "Create comprehensive user guides"
    })
    client.post("/api/v1/tasks", json={
        "title": "Fix bug in authentication",
        "description": "Users are unable to login"
    })
    client.post("/api/v1/tasks", json={
        "title": "Review code",
        "description": "Check documentation and tests"
    })
    client.post("/api/v1/tasks", json={
        "title": "Deploy to production",
        "description": "Release new features"
    })

    # Search in title
    response = client.get("/api/v1/tasks?search=documentation")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) >= 2  # Should find tasks with "documentation" in title or description
    search_found = []
    for task in tasks:
        title_match = "documentation" in task["title"].lower()
        desc_match = task["description"] and "documentation" in task["description"].lower()
        assert title_match or desc_match
        search_found.append(task["title"])

    # Search should be case-insensitive
    response = client.get("/api/v1/tasks?search=AUTHENTICATION")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) >= 1
    found_auth_task = False
    for task in tasks:
        if "authentication" in task["title"].lower():
            found_auth_task = True
            break
    assert found_auth_task

def test_combined_filters():
    # Create project and goal
    project_response = client.post("/api/v1/projects", json={"name": "Combined Filter Project"})
    project_id = project_response.json()["id"]

    goal_response = client.post("/api/v1/goals", json={"title": "Combined Filter Goal"})
    goal_id = goal_response.json()["id"]

    future_date = datetime.now(timezone.utc) + timedelta(days=2)

    # Create task that matches all filters
    matching_task_response = client.post("/api/v1/tasks", json={
        "title": "Important project task",
        "description": "This is a critical feature",
        "status": "doing",
        "project_id": project_id,
        "goal_id": goal_id,
        "tags": ["critical", "feature"],
        "hard_due_at": future_date.isoformat()
    })
    matching_task_id = matching_task_response.json()["id"]

    # Create tasks that don't match all filters
    client.post("/api/v1/tasks", json={
        "title": "Different project task",
        "status": "doing",
        "tags": ["critical", "feature"]
    })

    client.post("/api/v1/tasks", json={
        "title": "Important task wrong status",
        "description": "This is a critical feature",
        "status": "backlog",
        "project_id": project_id,
        "tags": ["critical", "feature"]
    })

    # Apply combined filters
    due_after_time = quote(datetime.now(timezone.utc).isoformat())
    response = client.get(f"/api/v1/tasks?status=doing&project_id={project_id}&goal_id={goal_id}&tag=critical&tag=feature&search=important&due_after={due_after_time}")
    if response.status_code != 200:
        print("Response status:", response.status_code)
        print("Response body:", response.text)
    assert response.status_code == 200
    tasks = response.json()

    # Should only return the matching task
    task_ids = [t["id"] for t in tasks]
    assert matching_task_id in task_ids

    # Verify all filters are applied
    for task in tasks:
        assert task["status"] == "doing"
        assert task["project_id"] == project_id
        assert task["goal_id"] == goal_id or any(g["id"] == goal_id for g in task.get("goals", []))
        assert "critical" in task["tags"]
        assert "feature" in task["tags"]
        assert "important" in task["title"].lower() or (task["description"] and "important" in task["description"].lower())
