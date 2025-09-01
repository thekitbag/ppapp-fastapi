from fastapi.testclient import TestClient
from app.main import app
from datetime import datetime, timedelta, timezone

client = TestClient(app)

def _iso_in_days(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

def test_suggest_week_returns_3_to_5():
    # Seed 6 backlog tasks with varied due dates / tags
    ids = []
    for i in range(6):
        r = client.post("/api/v1/tasks", json={"title": f"Task {i}", "tags": ["goal"] if i%2==0 else []})
        ids.append(r.json()["id"])
    # set some due soon (within 7 days) and mark some todo
    client.put(f"/api/v1/tasks/{ids[0]}", json={"status":"today","hard_due_at": _iso_in_days(2)})
    client.put(f"/api/v1/tasks/{ids[1]}", json={"status":"today","hard_due_at": _iso_in_days(10)}) # outside 7 days
    client.put(f"/api/v1/tasks/{ids[2]}", json={"status":"backlog","soft_due_at": _iso_in_days(3)})

    r = client.post("/api/v1/recommendations/suggest-week", json={"limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert 1 <= len(data["items"]) <= 5
    # each item should have a why
    assert all("why" in it for it in data["items"])

def test_promote_week_moves_status():
    r = client.post("/api/v1/tasks", json={"title":"Promote me","tags":[]})
    tid = r.json()["id"]
    r2 = client.post("/api/v1/tasks/promote-week", json={"task_ids":[tid]})
    assert r2.status_code == 200
    assert tid in r2.json()["ids"]
    # confirm via listing
    items = client.get("/api/v1/tasks").json()
    st = next(t for t in items if t["id"]==tid)["status"]
    assert st == "week"


def test_suggest_week_prioritizes_project_milestones():
    """Test that suggest-week prioritizes tasks linked to projects with upcoming milestones."""
    
    # Create projects with different milestone dates
    project_soon_resp = client.post("/api/v1/projects", json={
        "name": "Urgent Project",
        "milestone_title": "Launch",
        "milestone_due_at": _iso_in_days(5)  # 5 days from now
    })
    project_soon = project_soon_resp.json()
    
    project_far_resp = client.post("/api/v1/projects", json={
        "name": "Long Term Project", 
        "milestone_title": "Research Phase",
        "milestone_due_at": _iso_in_days(25)  # 25 days from now
    })
    project_far = project_far_resp.json()
    
    # Create tasks linked to these projects (ensure they have status 'backlog' for suggest-week)
    # Use timestamp in title to ensure uniqueness across test runs
    from datetime import datetime
    timestamp = str(int(datetime.now().timestamp()))
    
    task_soon_resp = client.post("/api/v1/tasks", json={
        "title": f"Urgent project task {timestamp}",
        "project_id": project_soon["id"],
        "status": "backlog",
        "tags": ["goal"]  # Add goal tag to boost score
    })
    task_soon = task_soon_resp.json()
    
    task_far_resp = client.post("/api/v1/tasks", json={
        "title": f"Long term project task {timestamp}",
        "project_id": project_far["id"],
        "status": "backlog"
    })
    task_far = task_far_resp.json()
    
    task_no_project_resp = client.post("/api/v1/tasks", json={
        "title": f"No project task {timestamp}",
        "status": "backlog"
    })
    task_no_project = task_no_project_resp.json()
    
    # Get week suggestions with higher limit to ensure we capture our tasks
    suggest_resp = client.post("/api/v1/recommendations/suggest-week", json={"limit": 10})
    assert suggest_resp.status_code == 200
    
    suggestions = suggest_resp.json()["items"]
    
    # Find our task suggestions 
    urgent_task_suggestion = next((s for s in suggestions if s["task"]["id"] == task_soon["id"]), None)
    far_task_suggestion = next((s for s in suggestions if s["task"]["id"] == task_far["id"]), None)
    no_project_suggestion = next((s for s in suggestions if s["task"]["id"] == task_no_project["id"]), None)
    
    # The urgent task should be in suggestions with high project_due_proximity
    assert urgent_task_suggestion is not None, f"Urgent task not found in suggestions. Available tasks: {[s['task']['title'] for s in suggestions]}"
    assert urgent_task_suggestion["factors"]["project_due_proximity"] > 0.3
    
    # Check that urgent project task includes project milestone info in explanation
    assert "urgent project" in urgent_task_suggestion["why"].lower()
    assert "milestone in" in urgent_task_suggestion["why"]
    
    # Far task should have lower project proximity if it exists
    if far_task_suggestion:
        assert far_task_suggestion["factors"]["project_due_proximity"] < 0.3
    
    # No-project task should have 0 project proximity if it exists
    if no_project_suggestion:
        assert no_project_suggestion["factors"]["project_due_proximity"] == 0.0
    
    # Tasks with project milestones should rank higher than those without (when they exist)
    if urgent_task_suggestion and no_project_suggestion:
        urgent_rank = next(i for i, s in enumerate(suggestions) if s["task"]["id"] == task_soon["id"])
        no_project_rank = next(i for i, s in enumerate(suggestions) if s["task"]["id"] == task_no_project["id"])
        assert urgent_rank < no_project_rank, "Task with project milestone should rank higher"


def test_suggest_week_explanation_includes_project_milestones():
    """Test that explanations include project milestone information."""
    
    # Create project with milestone
    project_resp = client.post("/api/v1/projects", json={
        "name": "Demo Project",
        "milestone_title": "Beta Release", 
        "milestone_due_at": _iso_in_days(6)  # 6 days from now
    })
    project = project_resp.json()
    
    # Create task linked to project (with backlog status for suggest-week)
    from datetime import datetime
    timestamp = str(int(datetime.now().timestamp()))
    
    task_resp = client.post("/api/v1/tasks", json={
        "title": f"Prepare demo {timestamp}",
        "project_id": project["id"],
        "status": "backlog",
        "tags": ["goal"]  # Add goal tag to boost score
    })
    task = task_resp.json()
    
    # Get suggestions with higher limit to ensure our task is included
    suggest_resp = client.post("/api/v1/recommendations/suggest-week", json={"limit": 10})
    suggestions = suggest_resp.json()["items"]
    
    # Find our task in suggestions
    demo_task_suggestion = next((s for s in suggestions if s["task"]["id"] == task["id"]), None)
    
    # Task should be found and have project milestone explanation
    assert demo_task_suggestion is not None, f"Demo task not found in suggestions. Available tasks: {[s['task']['title'] for s in suggestions]}"
    assert "demo project" in demo_task_suggestion["why"].lower()
    assert "milestone in" in demo_task_suggestion["why"]
