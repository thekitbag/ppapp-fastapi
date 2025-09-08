import pytest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

from app.schemas import TaskUpdate


class TestTaskUpdateValidation:
    """Test validation logic for TaskUpdate schema."""

    def test_hard_due_at_cannot_be_past(self):
        """Test that hard_due_at cannot be set to a past date."""
        past_date = datetime.now(timezone.utc) - timedelta(hours=1)
        
        with pytest.raises(ValidationError) as exc_info:
            TaskUpdate(hard_due_at=past_date)
        
        assert "hard_due_at cannot be in the past" in str(exc_info.value)

    def test_hard_due_at_can_be_future(self):
        """Test that hard_due_at can be set to a future date."""
        future_date = datetime.now(timezone.utc) + timedelta(hours=1)
        
        # Should not raise
        task_update = TaskUpdate(hard_due_at=future_date)
        assert task_update.hard_due_at == future_date

    def test_hard_due_at_can_be_none(self):
        """Test that hard_due_at can be None."""
        task_update = TaskUpdate(hard_due_at=None)
        assert task_update.hard_due_at is None

    def test_soft_due_at_can_be_before_hard_due_at(self):
        """Test that soft_due_at can be before hard_due_at."""
        base_time = datetime.now(timezone.utc) + timedelta(hours=2)
        hard_due = base_time + timedelta(hours=2)
        soft_due = base_time + timedelta(hours=1)
        
        task_update = TaskUpdate(hard_due_at=hard_due, soft_due_at=soft_due)
        assert task_update.hard_due_at == hard_due
        assert task_update.soft_due_at == soft_due

    def test_soft_due_at_can_equal_hard_due_at(self):
        """Test that soft_due_at can equal hard_due_at."""
        due_date = datetime.now(timezone.utc) + timedelta(hours=1)
        
        task_update = TaskUpdate(hard_due_at=due_date, soft_due_at=due_date)
        assert task_update.hard_due_at == due_date
        assert task_update.soft_due_at == due_date

    def test_soft_due_at_cannot_be_after_hard_due_at(self):
        """Test that soft_due_at cannot be after hard_due_at."""
        base_time = datetime.now(timezone.utc) + timedelta(hours=2)
        hard_due = base_time + timedelta(hours=1)
        soft_due = base_time + timedelta(hours=2)
        
        with pytest.raises(ValidationError) as exc_info:
            TaskUpdate(hard_due_at=hard_due, soft_due_at=soft_due)
        
        assert "soft_due_at cannot be after hard_due_at" in str(exc_info.value)

    def test_soft_due_at_alone_has_no_validation(self):
        """Test that soft_due_at by itself has no validation constraints."""
        past_date = datetime.now(timezone.utc) - timedelta(hours=1)
        
        # Should not raise - soft dates can be in the past
        task_update = TaskUpdate(soft_due_at=past_date)
        assert task_update.soft_due_at == past_date

    def test_all_fields_are_optional(self):
        """Test that all fields are optional and can be omitted."""
        task_update = TaskUpdate()
        
        # Check all fields are None
        assert task_update.title is None
        assert task_update.description is None
        assert task_update.status is None
        assert task_update.sort_order is None
        assert task_update.tags is None
        assert task_update.size is None
        assert task_update.effort_minutes is None
        assert task_update.hard_due_at is None
        assert task_update.soft_due_at is None
        assert task_update.energy is None
        assert task_update.project_id is None
        assert task_update.goal_id is None

    def test_valid_update_with_all_fields(self):
        """Test a valid update with all fields populated."""
        future_date = datetime.now(timezone.utc) + timedelta(hours=2)
        
        task_update = TaskUpdate(
            title="Updated task",
            description="Updated description",
            status="doing",
            sort_order=1.5,
            tags=["tag1", "tag2"],
            size="m",
            effort_minutes=60,
            hard_due_at=future_date,
            soft_due_at=future_date - timedelta(minutes=30),
            energy="high",
            project_id="proj-123",
            goal_id="goal-456"
        )
        
        assert task_update.title == "Updated task"
        assert task_update.description == "Updated description"
        assert task_update.status == "doing"
        assert task_update.sort_order == 1.5
        assert task_update.tags == ["tag1", "tag2"]
        assert task_update.size == "m"
        assert task_update.effort_minutes == 60
        assert task_update.hard_due_at == future_date
        assert task_update.soft_due_at == future_date - timedelta(minutes=30)
        assert task_update.energy == "high"
        assert task_update.project_id == "proj-123"
        assert task_update.goal_id == "goal-456"