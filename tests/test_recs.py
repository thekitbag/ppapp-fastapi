
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
