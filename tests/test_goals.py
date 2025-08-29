from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_and_list_goal():
    # Create a goal
    response = client.post("/goals", json={"title": "Finish Q3 report", "type": "work"})
    assert response.status_code == 200
    goal = response.json()
    assert goal["title"] == "Finish Q3 report"
    assert goal["type"] == "work"
    assert "id" in goal
    assert "created_at" in goal

    # List goals
    response = client.get("/goals")
    assert response.status_code == 200
    goals = response.json()
    assert any(g["id"] == goal["id"] for g in goals)
