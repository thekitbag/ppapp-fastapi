from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_and_list_task():
    r = client.post("/tasks", json={"title":"Write docs","tags":["docs","alpha"]})
    assert r.status_code == 200
    task = r.json()
    assert task["title"] == "Write docs"
    assert "alpha" in task["tags"]

    r2 = client.get("/tasks")
    assert r2.status_code == 200
    lst = r2.json()
    assert any(t["id"] == task["id"] for t in lst)

def test_patch_task():
    r = client.post("/tasks", json={"title":"Patch me"})
    tid = r.json()["id"]
    r2 = client.patch(f"/tasks/{tid}", json={"status":"todo"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "todo"

def test_task_timestamps_present_on_create():
    r = client.post("/tasks", json={"title": "Timestamp check", "tags": []})
    assert r.status_code == 200
    body = r.json()
    # ensure created_at and updated_at fields exist and are ISO strings
    assert "created_at" in body and "updated_at" in body
    ca = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
    ua = datetime.fromisoformat(body["updated_at"].replace("Z", "+00:00"))
    assert ca <= ua
    # check they appear also via GET /tasks
    r2 = client.get("/tasks")
    assert any(t["id"] == body["id"] and "created_at" in t for t in r2.json())
