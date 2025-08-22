
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
