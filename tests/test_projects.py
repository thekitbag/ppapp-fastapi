from fastapi.testclient import TestClient
from datetime import datetime, timezone
from app.main import app

client = TestClient(app)

def test_create_and_list_project():
    # Create a project
    response = client.post("/api/v1/projects", json={"name": "Work", "color": "#ff0000"})
    assert response.status_code == 201
    project = response.json()
    assert project["name"] == "Work"
    assert project["color"] == "#ff0000"
    assert "id" in project
    assert "created_at" in project

    # List projects
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    projects = response.json()
    assert any(p["id"] == project["id"] for p in projects)


def test_create_project_with_milestone():
    """Test creating a project with milestone fields."""
    milestone_date = (datetime.now(timezone.utc)).isoformat()
    
    # Create project with milestone
    response = client.post("/api/v1/projects", json={
        "name": "Website Launch",
        "color": "#00ff00",
        "milestone_title": "v1.0 Release",
        "milestone_due_at": milestone_date
    })
    
    assert response.status_code == 201
    project = response.json()
    assert project["name"] == "Website Launch"
    assert project["milestone_title"] == "v1.0 Release"
    assert project["milestone_due_at"] is not None
    assert "id" in project


def test_update_project_milestone():
    """Test updating project milestone via PATCH."""
    # First create a project
    response = client.post("/api/v1/projects", json={
        "name": "Test Project",
        "color": "#blue"
    })
    assert response.status_code == 201
    project = response.json()
    project_id = project["id"]
    
    # Update with milestone information
    milestone_date = (datetime.now(timezone.utc)).isoformat()
    update_response = client.patch(f"/api/v1/projects/{project_id}", json={
        "milestone_title": "Beta Release",
        "milestone_due_at": milestone_date
    })
    
    assert update_response.status_code == 200
    updated_project = update_response.json()
    assert updated_project["milestone_title"] == "Beta Release"
    assert updated_project["milestone_due_at"] is not None
    assert updated_project["name"] == "Test Project"  # Unchanged fields remain


def test_update_project_partial():
    """Test partial updates work correctly."""
    # Create project with milestone
    milestone_date = (datetime.now(timezone.utc)).isoformat()
    response = client.post("/api/v1/projects", json={
        "name": "Partial Test",
        "milestone_title": "Original Milestone",
        "milestone_due_at": milestone_date
    })
    project = response.json()
    project_id = project["id"]
    
    # Update only milestone title
    update_response = client.patch(f"/api/v1/projects/{project_id}", json={
        "milestone_title": "Updated Milestone"
    })
    
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["milestone_title"] == "Updated Milestone"
    assert updated["milestone_due_at"] is not None  # Should remain unchanged
    assert updated["name"] == "Partial Test"  # Should remain unchanged


def test_list_projects_includes_milestones():
    """Test that listing projects includes milestone fields."""
    milestone_date = (datetime.now(timezone.utc)).isoformat()
    
    # Create project with milestone
    response = client.post("/api/v1/projects", json={
        "name": "Milestone Project",
        "milestone_title": "Launch",
        "milestone_due_at": milestone_date
    })
    project = response.json()
    
    # List projects
    list_response = client.get("/api/v1/projects")
    assert list_response.status_code == 200
    projects = list_response.json()
    
    # Find our project in the list
    milestone_project = next(p for p in projects if p["id"] == project["id"])
    assert milestone_project["milestone_title"] == "Launch"
    assert milestone_project["milestone_due_at"] is not None


def test_get_single_project_with_milestone():
    """Test getting a single project includes milestone fields."""
    milestone_date = (datetime.now(timezone.utc)).isoformat()
    
    # Create project
    response = client.post("/api/v1/projects", json={
        "name": "Single Project Test",
        "milestone_title": "Phase 1",
        "milestone_due_at": milestone_date
    })
    project = response.json()
    project_id = project["id"]
    
    # Get single project
    get_response = client.get(f"/api/v1/projects/{project_id}")
    assert get_response.status_code == 200
    
    retrieved_project = get_response.json()
    assert retrieved_project["milestone_title"] == "Phase 1"
    assert retrieved_project["milestone_due_at"] is not None
