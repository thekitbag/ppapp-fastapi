
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_recommendations_endpoint():
    # ensure it returns shape
    r = client.get("/api/v1/recommendations/next?window=30&limit=3&energy=high")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_recommendations_returns_why():
    # create some data to make sure we have at least one task
    r = client.post("/api/v1/tasks", json={"title": "Demo goal due soon", "tags": ["goal"]})
    assert r.status_code == 201
    # patch a due date within 24h to trigger 'due soon'
    tid = r.json()["id"]
    import datetime as _dt
    soon = (_dt.datetime.utcnow() + _dt.timedelta(hours=1)).isoformat()
    client.put(f"/api/v1/tasks/{tid}", json={"status":"today","hard_due_at": soon})

    resp = client.get("/api/v1/recommendations/next?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and len(body["items"]) >= 1
    top = body["items"][0]
    assert "why" in top and isinstance(top["why"], str) and len(top["why"]) > 0


def test_valid_energy_and_time_window_returns_200():
    """Valid energy + time_window params return 200 with expected shape."""
    r = client.get("/api/v1/recommendations/next?energy=low&time_window=30&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_invalid_time_window_returns_422():
    """Non-allowed time_window value returns 422."""
    r = client.get("/api/v1/recommendations/next?time_window=45")
    assert r.status_code == 422


def test_invalid_energy_returns_422():
    """Non-allowed energy value returns 422."""
    r = client.get("/api/v1/recommendations/next?energy=super")
    assert r.status_code == 422


def test_deprecated_window_param_still_works():
    """Existing clients using the legacy `window` param continue to get 200."""
    r = client.get("/api/v1/recommendations/next?window=60")
    assert r.status_code == 200
    assert "items" in r.json()


def test_recommendations_are_tenant_scoped():
    # Create one task for each test user
    r1 = client.post("/api/v1/tasks", json={"title": "User A task"}, headers={"x-test-user-id": "user_test"})
    assert r1.status_code == 201
    user_a_task_id = r1.json()["id"]

    r2 = client.post("/api/v1/tasks", json={"title": "User B task"}, headers={"x-test-user-id": "user_other"})
    assert r2.status_code == 201
    user_b_task_id = r2.json()["id"]

    # Recommendations for user A should not include user B's task
    rec_a = client.get("/api/v1/recommendations/next?limit=50", headers={"x-test-user-id": "user_test"}).json()
    ids_a = {item["task"]["id"] for item in rec_a["items"]}
    assert user_a_task_id in ids_a
    assert user_b_task_id not in ids_a

    # Recommendations for user B should not include user A's task
    rec_b = client.get("/api/v1/recommendations/next?limit=50", headers={"x-test-user-id": "user_other"}).json()
    ids_b = {item["task"]["id"] for item in rec_b["items"]}
    assert user_b_task_id in ids_b
    assert user_a_task_id not in ids_b
