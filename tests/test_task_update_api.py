import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestTaskUpdateAPI:
    """Test the task update API with validation."""

    def test_update_task_with_valid_data(self):
        """Test updating a task with valid data."""
        # Create a task first
        create_response = client.post("/api/v1/tasks", json={
            "title": "Test task",
            "description": "Original description"
        })
        assert create_response.status_code == 201
        task_id = create_response.json()["id"]
        
        # Update the task with all valid fields
        future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        soft_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        
        update_data = {
            "title": "Updated task title",
            "description": "Updated description",
            "status": "doing",
            "size": "m",
            "effort_minutes": 60,
            "hard_due_at": future_time,
            "soft_due_at": soft_time,
            "energy": "high",
            "tags": ["updated", "test"]
        }
        
        response = client.patch(f"/api/v1/tasks/{task_id}", json=update_data)
        assert response.status_code == 200
        
        updated_task = response.json()
        assert updated_task["title"] == "Updated task title"
        assert updated_task["description"] == "Updated description"
        assert updated_task["status"] == "doing"
        assert updated_task["tags"] == ["updated", "test"]

    def test_update_task_hard_due_at_past_validation(self):
        """Test that updating hard_due_at to a past date fails validation."""
        # Create a task first
        create_response = client.post("/api/v1/tasks", json={
            "title": "Test task for validation"
        })
        assert create_response.status_code == 201
        task_id = create_response.json()["id"]
        
        # Try to update with a past hard_due_at
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        
        update_data = {
            "hard_due_at": past_time
        }
        
        response = client.patch(f"/api/v1/tasks/{task_id}", json=update_data)
        assert response.status_code == 422
        assert "hard_due_at cannot be in the past" in response.json()["detail"][0]["msg"]

    def test_update_task_soft_after_hard_validation(self):
        """Test that soft_due_at after hard_due_at fails validation."""
        # Create a task first
        create_response = client.post("/api/v1/tasks", json={
            "title": "Test task for validation"
        })
        assert create_response.status_code == 201
        task_id = create_response.json()["id"]
        
        # Try to update with soft_due_at > hard_due_at
        base_time = datetime.now(timezone.utc) + timedelta(hours=2)
        hard_time = base_time.isoformat()
        soft_time = (base_time + timedelta(hours=1)).isoformat()
        
        update_data = {
            "hard_due_at": hard_time,
            "soft_due_at": soft_time
        }
        
        response = client.patch(f"/api/v1/tasks/{task_id}", json=update_data)
        assert response.status_code == 422
        assert "soft_due_at cannot be after hard_due_at" in response.json()["detail"][0]["msg"]

    def test_update_task_partial_fields(self):
        """Test updating only some fields (partial update)."""
        # Create a task first
        create_response = client.post("/api/v1/tasks", json={
            "title": "Test task",
            "description": "Original description",
            "status": "backlog"
        })
        assert create_response.status_code == 201
        task_id = create_response.json()["id"]
        original_task = create_response.json()
        
        # Update only the title
        update_data = {
            "title": "Only title updated"
        }
        
        response = client.patch(f"/api/v1/tasks/{task_id}", json=update_data)
        assert response.status_code == 200
        
        updated_task = response.json()
        assert updated_task["title"] == "Only title updated"
        # Other fields should remain unchanged
        assert updated_task["description"] == original_task["description"]
        assert updated_task["status"] == original_task["status"]

    def test_update_task_both_put_and_patch_work(self):
        """Test that both PUT and PATCH endpoints work."""
        # Create a task first
        create_response = client.post("/api/v1/tasks", json={
            "title": "Test task"
        })
        assert create_response.status_code == 201
        task_id = create_response.json()["id"]
        
        # Test PATCH
        patch_response = client.patch(f"/api/v1/tasks/{task_id}", json={
            "title": "Updated via PATCH"
        })
        assert patch_response.status_code == 200
        assert patch_response.json()["title"] == "Updated via PATCH"
        
        # Test PUT 
        put_response = client.put(f"/api/v1/tasks/{task_id}", json={
            "title": "Updated via PUT"
        })
        assert put_response.status_code == 200
        assert put_response.json()["title"] == "Updated via PUT"