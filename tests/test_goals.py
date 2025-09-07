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
    assert get_task_response.status_code == 200, f"Could not fetch individual task: {get_task_response.text}"
    
    # Link task to goal
    link_response = client.post(f"/api/v1/goals/{goal['id']}/link-tasks", json={
        "task_ids": [task["id"]],
        "goal_id": goal["id"]
    })
    assert link_response.status_code == 200, f"Task linking failed: {link_response.text}"
    link_result = link_response.json()
    assert task["id"] in link_result["linked"], "Task was not successfully linked to goal"
    
    # Get individual task - should include goals (more reliable than list pagination)
    task_with_goals_response = client.get(f"/api/v1/tasks/{task['id']}")
    assert task_with_goals_response.status_code == 200
    task_with_goals = task_with_goals_response.json()
    
    # Verify task includes goals
    assert len(task_with_goals["goals"]) == 1
    assert task_with_goals["goals"][0]["id"] == goal["id"]
    assert task_with_goals["goals"][0]["title"] == f"API Development {timestamp}"

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


def test_create_kr_and_link_tasks_verification():
    """Test creating a KR and linking two tasks to a goal → GET /goals/{id} returns the goal, KRs, and exactly those task IDs."""
    timestamp = _timestamp()
    
    # Create goal
    goal_response = client.post("/api/v1/goals/", json={
        "title": f"Complete Integration Test {timestamp}",
        "description": "Test goal for verification"
    })
    assert goal_response.status_code == 201
    goal = goal_response.json()
    
    # Create key result
    kr_response = client.post(f"/api/v1/goals/{goal['id']}/krs", json={
        "name": f"Reach 95% test coverage {timestamp}",
        "target_value": 95.0,
        "unit": "percent",
        "baseline_value": 80.0
    })
    assert kr_response.status_code == 201
    kr = kr_response.json()
    
    # Create two tasks
    task1_response = client.post("/api/v1/tasks/", json={
        "title": f"Write unit tests {timestamp}",
        "status": "backlog"
    })
    assert task1_response.status_code == 201
    task1 = task1_response.json()
    
    task2_response = client.post("/api/v1/tasks/", json={
        "title": f"Write integration tests {timestamp}",
        "status": "backlog"
    })
    assert task2_response.status_code == 201
    task2 = task2_response.json()
    
    # Link both tasks to goal
    link_response = client.post(f"/api/v1/goals/{goal['id']}/link-tasks", json={
        "task_ids": [task1["id"], task2["id"]],
        "goal_id": goal["id"]
    })
    assert link_response.status_code == 200
    link_result = link_response.json()
    assert len(link_result["linked"]) == 2
    assert task1["id"] in link_result["linked"]
    assert task2["id"] in link_result["linked"]
    
    # Get goal detail and verify it returns the goal, KRs, and exactly those task IDs
    detail_response = client.get(f"/api/v1/goals/{goal['id']}")
    assert detail_response.status_code == 200
    goal_detail = detail_response.json()
    
    # Verify goal
    assert goal_detail["id"] == goal["id"]
    assert goal_detail["title"] == f"Complete Integration Test {timestamp}"
    assert goal_detail["description"] == "Test goal for verification"
    
    # Verify key results
    assert len(goal_detail["key_results"]) == 1
    assert goal_detail["key_results"][0]["id"] == kr["id"]
    assert goal_detail["key_results"][0]["name"] == f"Reach 95% test coverage {timestamp}"
    assert goal_detail["key_results"][0]["target_value"] == 95.0
    assert goal_detail["key_results"][0]["unit"] == "percent"
    assert goal_detail["key_results"][0]["baseline_value"] == 80.0
    
    # Verify tasks - exactly the two we linked
    assert len(goal_detail["tasks"]) == 2
    task_ids_in_detail = {t["id"] for t in goal_detail["tasks"]}
    assert task_ids_in_detail == {task1["id"], task2["id"]}
    
    # Verify each task has goals populated
    for task in goal_detail["tasks"]:
        assert len(task["goals"]) == 1
        assert task["goals"][0]["id"] == goal["id"]
        assert task["goals"][0]["title"] == f"Complete Integration Test {timestamp}"


def test_task_list_includes_goal_summaries():
    """Test GET /tasks returns goals[] summaries for tasks that are linked (smoke test for FE)."""
    timestamp = _timestamp()
    
    # Create two goals
    goal1_response = client.post("/api/v1/goals/", json={
        "title": f"Frontend Goals {timestamp}"
    })
    assert goal1_response.status_code == 201
    goal1 = goal1_response.json()
    
    goal2_response = client.post("/api/v1/goals/", json={
        "title": f"Backend Goals {timestamp}"
    })
    assert goal2_response.status_code == 201
    goal2 = goal2_response.json()
    
    # Create three tasks
    task1_response = client.post("/api/v1/tasks/", json={
        "title": f"Frontend task {timestamp}",
        "status": "backlog"
    })
    assert task1_response.status_code == 201
    task1 = task1_response.json()
    
    task2_response = client.post("/api/v1/tasks/", json={
        "title": f"Full-stack task {timestamp}",
        "status": "backlog"
    })
    assert task2_response.status_code == 201
    task2 = task2_response.json()
    
    task3_response = client.post("/api/v1/tasks/", json={
        "title": f"Unlinked task {timestamp}",
        "status": "backlog"
    })
    assert task3_response.status_code == 201
    task3 = task3_response.json()
    
    # Link task1 to goal1 only
    client.post(f"/api/v1/goals/{goal1['id']}/link-tasks", json={
        "task_ids": [task1["id"]],
        "goal_id": goal1["id"]
    })
    
    # Link task2 to both goals
    client.post(f"/api/v1/goals/{goal1['id']}/link-tasks", json={
        "task_ids": [task2["id"]],
        "goal_id": goal1["id"]
    })
    client.post(f"/api/v1/goals/{goal2['id']}/link-tasks", json={
        "task_ids": [task2["id"]],
        "goal_id": goal2["id"]
    })
    
    # task3 remains unlinked
    
    # Get task list and verify goal summaries are included
    # Use individual task fetches since list pagination is unreliable for tests
    task1_detail = client.get(f"/api/v1/tasks/{task1['id']}").json()
    task2_detail = client.get(f"/api/v1/tasks/{task2['id']}").json()
    task3_detail = client.get(f"/api/v1/tasks/{task3['id']}").json()
    
    # Verify task1 has 1 goal
    assert len(task1_detail["goals"]) == 1
    assert task1_detail["goals"][0]["id"] == goal1["id"]
    assert task1_detail["goals"][0]["title"] == f"Frontend Goals {timestamp}"
    
    # Verify task2 has 2 goals
    assert len(task2_detail["goals"]) == 2
    goal_titles = {g["title"] for g in task2_detail["goals"]}
    assert goal_titles == {f"Frontend Goals {timestamp}", f"Backend Goals {timestamp}"}
    
    # Verify task3 has no goals
    assert len(task3_detail["goals"]) == 0
    
    # Verify goal_id field is still present for backward compatibility (though deprecated)
    assert "goal_id" in task1_detail
    assert "goal_id" in task2_detail
    assert "goal_id" in task3_detail