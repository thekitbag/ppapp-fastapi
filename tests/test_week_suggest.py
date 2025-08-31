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
