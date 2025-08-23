
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_recommendations_endpoint():
    # ensure it returns shape
    r = client.get("/recommendations/next?window=30&limit=3&energy=high")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_recommendations_returns_why():
    # create some data to make sure we have at least one task
    r = client.post("/tasks", json={"title": "Demo goal due soon", "tags": ["goal"]})
    assert r.status_code == 200
    # patch a due date within 24h to trigger 'due soon'
    tid = r.json()["id"]
    import datetime as _dt
    soon = (_dt.datetime.utcnow() + _dt.timedelta(hours=1)).isoformat()
    client.patch(f"/tasks/{tid}", json={"status":"todo","hard_due_at": soon})

    resp = client.get("/recommendations/next?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and len(body["items"]) >= 1
    top = body["items"][0]
    assert "why" in top and isinstance(top["why"], str) and len(top["why"]) > 0
