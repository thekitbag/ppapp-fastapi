from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_and_list_project():
    # Create a project
    response = client.post("/projects", json={"name": "Work", "color": "#ff0000"})
    assert response.status_code == 200
    project = response.json()
    assert project["name"] == "Work"
    assert project["color"] == "#ff0000"
    assert "id" in project
    assert "created_at" in project

    # List projects
    response = client.get("/projects")
    assert response.status_code == 200
    projects = response.json()
    assert any(p["id"] == project["id"] for p in projects)
