from fastapi.testclient import TestClient
from app.main import app
from datetime import datetime, timezone
import uuid
import json

client = TestClient(app)

def _timestamp():
    """Generate a unique timestamp for test data."""
    return str(int(datetime.now().timestamp()))

def test_create_goal():
    """Test creating a goal."""
    timestamp = _timestamp()
    response = client.post("/api/v1/goals/", json={
        "title": f"Improve Retention {timestamp}",
        "description": "Increase user retention rate",
        "type": "quarterly"
    })
    assert response.status_code == 201
    goal = response.json()
    assert goal["title"] == f"Improve Retention {timestamp}"
    assert goal["description"] == "Increase user retention rate"
    assert goal["type"] == "quarterly"
    assert "id" in goal
    assert "created_at" in goal

def test_list_goals():
    """Test listing goals."""
    # Create a goal first
    timestamp = _timestamp()
    create_response = client.post("/api/v1/goals/", json={
        "title": f"Test Goal {timestamp}",
        "description": "Test description"
    })
    goal = create_response.json()
    
    # List goals
    response = client.get("/api/v1/goals/")
    assert response.status_code == 200
    goals = response.json()
    assert isinstance(goals, list)
    assert any(g["id"] == goal["id"] for g in goals)

def test_create_goal_with_key_results():
    """Test creating a goal and adding key results."""
    timestamp = _timestamp()
    
    # Create goal
    goal_response = client.post("/api/v1/goals/", json={
        "title": f"Launch Product {timestamp}",
        "description": "Successfully launch the new product"
    })
    assert goal_response.status_code == 201
    goal = goal_response.json()
    
    # Add first key result
    kr1_response = client.post(f"/api/v1/goals/{goal['id']}/krs", json={
        "name": "Increase NPS from 45 to 55",
        "target_value": 55.0,
        "unit": "score",
        "baseline_value": 45.0
    })
    assert kr1_response.status_code == 201
    kr1 = kr1_response.json()
    assert kr1["name"] == "Increase NPS from 45 to 55"
    assert kr1["target_value"] == 55.0
    assert kr1["baseline_value"] == 45.0
    assert kr1["goal_id"] == goal["id"]
    
    # Add second key result
    kr2_response = client.post(f"/api/v1/goals/{goal['id']}/krs", json={
        "name": "Reach 1000 active users",
        "target_value": 1000.0,
        "unit": "users"
    })
    assert kr2_response.status_code == 201
    kr2 = kr2_response.json()
    assert kr2["name"] == "Reach 1000 active users"
    assert kr2["target_value"] == 1000.0
    assert kr2["unit"] == "users"

def test_get_goal_with_key_results_and_tasks():
    """Test getting a goal with its key results and linked tasks."""
    timestamp = _timestamp()
    
    # Create goal
    goal_response = client.post("/api/v1/goals/", json={
        "title": f"Website Redesign {timestamp}",
        "description": "Redesign company website"
    })
    goal = goal_response.json()
    
    # Add key result
    kr_response = client.post(f"/api/v1/goals/{goal['id']}/krs", json={
        "name": "Increase conversion rate to 5%",
        "target_value": 5.0,
        "unit": "percent"
    })
    kr = kr_response.json()
    
    # Create tasks
    task1_response = client.post("/api/v1/tasks/", json={
        "title": f"Design mockups {timestamp}",
        "status": "backlog"
    })
    task1 = task1_response.json()
    
    task2_response = client.post("/api/v1/tasks/", json={
        "title": f"Implement frontend {timestamp}",
        "status": "backlog"
    })
    task2 = task2_response.json()
    
    # Link tasks to goal
    link_response = client.post(f"/api/v1/goals/{goal['id']}/link-tasks", json={
        "task_ids": [task1["id"], task2["id"]],
        "goal_id": goal["id"]
    })
    assert link_response.status_code == 200
    link_result = link_response.json()
    assert len(link_result["linked"]) == 2
    assert task1["id"] in link_result["linked"]
    assert task2["id"] in link_result["linked"]
    
    # Get goal with details
    get_response = client.get(f"/api/v1/goals/{goal['id']}")
    assert get_response.status_code == 200
    goal_detail = get_response.json()
    
    # Verify goal details
    assert goal_detail["title"] == f"Website Redesign {timestamp}"
    assert len(goal_detail["key_results"]) == 1
    assert goal_detail["key_results"][0]["id"] == kr["id"]
    
    # Verify linked tasks
    assert len(goal_detail["tasks"]) == 2
    task_titles = [t["title"] for t in goal_detail["tasks"]]
    assert f"Design mockups {timestamp}" in task_titles
    assert f"Implement frontend {timestamp}" in task_titles
    
    # Verify tasks have goals populated
    for task in goal_detail["tasks"]:
        assert len(task["goals"]) == 1
        assert task["goals"][0]["id"] == goal["id"]
        assert task["goals"][0]["title"] == f"Website Redesign {timestamp}"

def test_link_tasks_to_goal():
    """Test linking multiple tasks to a goal."""
    timestamp = _timestamp()
    
    # Create goal
    goal_response = client.post("/api/v1/goals/", json={
        "title": f"Marketing Campaign {timestamp}"
    })
    goal = goal_response.json()
    
    # Create tasks
    task1_response = client.post("/api/v1/tasks/", json={
        "title": f"Create content {timestamp}",
        "status": "backlog"
    })
    task1 = task1_response.json()
    
    task2_response = client.post("/api/v1/tasks/", json={
        "title": f"Launch ads {timestamp}",
        "status": "backlog"
    })
    task2 = task2_response.json()
    
    # Link tasks
    response = client.post(f"/api/v1/goals/{goal['id']}/link-tasks", json={
        "task_ids": [task1["id"], task2["id"]],
        "goal_id": goal["id"]
    })
    assert response.status_code == 200
    result = response.json()
    assert len(result["linked"]) == 2
    assert len(result["already_linked"]) == 0
    
    # Try linking same tasks again (should show already linked)
    response2 = client.post(f"/api/v1/goals/{goal['id']}/link-tasks", json={
        "task_ids": [task1["id"], task2["id"]],
        "goal_id": goal["id"]
    })
    assert response2.status_code == 200
    result2 = response2.json()
    assert len(result2["linked"]) == 0
    assert len(result2["already_linked"]) == 2

def test_tasks_include_goals_in_response():
    """Test that task endpoints include goals in responses."""
    timestamp = _timestamp()
    
    # Create goal
    goal_response = client.post("/api/v1/goals/", json={
        "title": f"API Development {timestamp}"
    })
    assert goal_response.status_code == 201, f"Goal creation failed: {goal_response.text}"
    goal = goal_response.json()
    assert "id" in goal, "Goal response missing ID"
    
    # Create task  
    task_response = client.post("/api/v1/tasks/", json={
        "title": f"Implement API endpoint {timestamp}",
        "status": "backlog"
    })
    assert task_response.status_code == 201, f"Task creation failed: {task_response.text}"
    task = task_response.json()
    assert "id" in task, "Task response missing ID"
    
    # Verify task was created by fetching it individually first
    get_task_response = client.get(f"/api/v1/tasks/{task['id']}")
    if get_task_response.status_code != 200:
        print(f"DEBUG: Individual task fetch failed: {get_task_response.status_code} - {get_task_response.text}")
    assert get_task_response.status_code == 200, f"Could not fetch individual task: {get_task_response.text}"
    
    # Link task to goal
    link_response = client.post(f"/api/v1/goals/{goal['id']}/link-tasks", json={
        "task_ids": [task["id"]],
        "goal_id": goal["id"]
    })
    assert link_response.status_code == 200, f"Task linking failed: {link_response.text}"
    link_result = link_response.json()
    assert task["id"] in link_result["linked"], "Task was not successfully linked to goal"
    
    # Get tasks list - should include goals
    # Note: Repository now orders by created_at DESC so newest tasks appear first
    tasks_response = client.get("/api/v1/tasks/")
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()
    
    # Find our task (should be near the top now due to DESC ordering)
    our_task = next((t for t in tasks if t["id"] == task["id"]), None)
    assert our_task is not None, f"Task {task['id']} not found in task list (newest first ordering)"
    assert len(our_task["goals"]) == 1
    assert our_task["goals"][0]["id"] == goal["id"]
    assert our_task["goals"][0]["title"] == f"API Development {timestamp}"

def test_delete_key_result():
    """Test deleting a key result."""
    timestamp = _timestamp()
    
    # Create goal
    goal_response = client.post("/api/v1/goals/", json={
        "title": f"Test Goal {timestamp}"
    })
    goal = goal_response.json()
    
    # Add key result
    kr_response = client.post(f"/api/v1/goals/{goal['id']}/krs", json={
        "name": "Test KR",
        "target_value": 100.0
    })
    kr = kr_response.json()
    
    # Delete key result
    delete_response = client.delete(f"/api/v1/goals/{goal['id']}/krs/{kr['id']}")
    assert delete_response.status_code == 204
    
    # Verify it's gone by getting the goal
    get_response = client.get(f"/api/v1/goals/{goal['id']}")
    goal_detail = get_response.json()
    assert len(goal_detail["key_results"]) == 0

def test_unlink_tasks_from_goal():
    """Test unlinking tasks from a goal."""
    timestamp = _timestamp()
    
    # Create goal
    goal_response = client.post("/api/v1/goals/", json={
        "title": f"Unlink Test {timestamp}"
    })
    goal = goal_response.json()
    
    # Create task
    task_response = client.post("/api/v1/tasks/", json={
        "title": f"Test task {timestamp}",
        "status": "backlog"
    })
    task = task_response.json()
    
    # Link task
    client.post(f"/api/v1/goals/{goal['id']}/link-tasks", json={
        "task_ids": [task["id"]],
        "goal_id": goal["id"]
    })
    
    # Verify link exists
    get_response = client.get(f"/api/v1/goals/{goal['id']}")
    goal_detail = get_response.json()
    assert len(goal_detail["tasks"]) == 1
    
    # Unlink task
    unlink_response = client.request("DELETE", f"/api/v1/goals/{goal['id']}/link-tasks", 
                                   content=json.dumps({
                                       "task_ids": [task["id"]],
                                       "goal_id": goal["id"]
                                   }),
                                   headers={"Content-Type": "application/json"})
    assert unlink_response.status_code == 200
    result = unlink_response.json()
    assert len(result["linked"]) == 1  # Actually unlinked
    assert result["linked"][0] == task["id"]
    
    # Verify link is gone
    get_response2 = client.get(f"/api/v1/goals/{goal['id']}")
    goal_detail2 = get_response2.json()
    assert len(goal_detail2["tasks"]) == 0

def test_update_goal():
    """Test updating a goal."""
    timestamp = _timestamp()
    
    # Create goal
    goal_response = client.post("/api/v1/goals/", json={
        "title": f"Original Title {timestamp}",
        "description": "Original description"
    })
    goal = goal_response.json()
    
    # Update goal
    update_response = client.patch(f"/api/v1/goals/{goal['id']}", json={
        "title": f"Updated Title {timestamp}",
        "description": "Updated description"
    })
    assert update_response.status_code == 200
    updated_goal = update_response.json()
    assert updated_goal["title"] == f"Updated Title {timestamp}"
    assert updated_goal["description"] == "Updated description"
    assert updated_goal["id"] == goal["id"]

def test_error_cases():
    """Test various error cases."""
    fake_id = str(uuid.uuid4())
    
    # Get non-existent goal
    response = client.get(f"/api/v1/goals/{fake_id}")
    assert response.status_code == 404
    
    # Update non-existent goal
    response = client.patch(f"/api/v1/goals/{fake_id}", json={
        "title": "Updated"
    })
    assert response.status_code == 404
    
    # Add KR to non-existent goal
    response = client.post(f"/api/v1/goals/{fake_id}/krs", json={
        "name": "Test KR",
        "target_value": 100.0
    })
    assert response.status_code == 404
    
    # Link tasks to non-existent goal
    response = client.post(f"/api/v1/goals/{fake_id}/link-tasks", json={
        "task_ids": [str(uuid.uuid4())],
        "goal_id": fake_id
    })
    assert response.status_code == 404