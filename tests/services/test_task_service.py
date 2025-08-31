import pytest
from unittest.mock import Mock, patch
from app.services.task import TaskService
from app.repositories.task import TaskRepository
from app.schemas import TaskCreate, TaskOut
from app.exceptions import NotFoundError, ValidationError
from app.models import Task, StatusEnum


class TestTaskService:
    """Test TaskService business logic."""
    
    @pytest.fixture
    def task_service(self, test_db):
        """Create TaskService instance with test database."""
        return TaskService(test_db)
    
    def test_create_task_success(self, task_service, sample_task_data):
        """Test successful task creation."""
        task_create = TaskCreate(**sample_task_data)
        result = task_service.create_task(task_create)
        
        assert isinstance(result, TaskOut)
        assert result.title == "Test Task"
        assert result.status == "backlog"
        assert "test" in result.tags
        assert "sample" in result.tags
    
    def test_create_task_empty_title_fails(self, task_service):
        """Test task creation with empty title fails."""
        task_create = TaskCreate(title="", description="Test")
        
        with pytest.raises(ValidationError) as exc_info:
            task_service.create_task(task_create)
        
        assert "title cannot be empty" in str(exc_info.value)
    
    def test_create_task_whitespace_only_title_fails(self, task_service):
        """Test task creation with whitespace-only title fails."""
        task_create = TaskCreate(title="   ", description="Test")
        
        with pytest.raises(ValidationError) as exc_info:
            task_service.create_task(task_create)
        
        assert "title cannot be empty" in str(exc_info.value)
    
    def test_get_task_success(self, task_service, sample_task_data):
        """Test successful task retrieval."""
        # Create a task first
        task_create = TaskCreate(**sample_task_data)
        created_task = task_service.create_task(task_create)
        
        # Retrieve the task
        result = task_service.get_task(created_task.id)
        
        assert result.id == created_task.id
        assert result.title == "Test Task"
    
    def test_get_task_not_found(self, task_service):
        """Test getting non-existent task raises NotFoundError."""
        with pytest.raises(NotFoundError) as exc_info:
            task_service.get_task("nonexistent_id")
        
        assert "Task with id 'nonexistent_id' not found" in str(exc_info.value)
    
    def test_list_tasks_default(self, task_service, sample_task_data):
        """Test listing tasks with default parameters."""
        # Create multiple tasks
        for i in range(3):
            data = sample_task_data.copy()
            data["title"] = f"Task {i}"
            task_service.create_task(TaskCreate(**data))
        
        result = task_service.list_tasks()
        
        assert len(result) == 3
        assert all(isinstance(task, TaskOut) for task in result)
    
    def test_list_tasks_with_status_filter(self, task_service, sample_task_data):
        """Test listing tasks with status filter."""
        # Create tasks with different statuses
        data1 = sample_task_data.copy()
        data1["status"] = "backlog"
        task_service.create_task(TaskCreate(**data1))
        
        data2 = sample_task_data.copy()
        data2["title"] = "Week Task"
        data2["status"] = "week"
        task_service.create_task(TaskCreate(**data2))
        
        result = task_service.list_tasks(status=["week"])
        
        assert len(result) == 1
        assert result[0].title == "Week Task"
        assert result[0].status == "week"
    
    def test_list_tasks_limit_validation(self, task_service):
        """Test list tasks with invalid limit."""
        with pytest.raises(ValidationError) as exc_info:
            task_service.list_tasks(limit=1001)
        
        assert "Limit cannot exceed 1000" in str(exc_info.value)
    
    def test_update_task_success(self, task_service, sample_task_data):
        """Test successful task update."""
        # Create a task first
        task_create = TaskCreate(**sample_task_data)
        created_task = task_service.create_task(task_create)
        
        # Update the task
        update_data = {"title": "Updated Task", "status": "doing"}
        result = task_service.update_task(created_task.id, update_data)
        
        assert result.title == "Updated Task"
        assert result.status == "doing"
    
    def test_update_task_empty_title_fails(self, task_service, sample_task_data):
        """Test updating task with empty title fails."""
        # Create a task first
        task_create = TaskCreate(**sample_task_data)
        created_task = task_service.create_task(task_create)
        
        # Try to update with empty title
        update_data = {"title": ""}
        
        with pytest.raises(ValidationError) as exc_info:
            task_service.update_task(created_task.id, update_data)
        
        assert "title cannot be empty" in str(exc_info.value)
    
    def test_update_task_not_found(self, task_service):
        """Test updating non-existent task raises NotFoundError."""
        update_data = {"title": "Updated Task"}
        
        with pytest.raises(NotFoundError):
            task_service.update_task("nonexistent_id", update_data)
    
    def test_delete_task_success(self, task_service, sample_task_data):
        """Test successful task deletion."""
        # Create a task first
        task_create = TaskCreate(**sample_task_data)
        created_task = task_service.create_task(task_create)
        
        # Delete the task
        result = task_service.delete_task(created_task.id)
        
        assert result is True
        
        # Verify task is deleted
        with pytest.raises(NotFoundError):
            task_service.get_task(created_task.id)
    
    def test_delete_task_not_found(self, task_service):
        """Test deleting non-existent task raises NotFoundError."""
        with pytest.raises(NotFoundError):
            task_service.delete_task("nonexistent_id")
    
    def test_promote_tasks_to_week_success(self, task_service, sample_task_data):
        """Test promoting tasks to week status."""
        # Create multiple tasks
        task_ids = []
        for i in range(3):
            data = sample_task_data.copy()
            data["title"] = f"Task {i}"
            created_task = task_service.create_task(TaskCreate(**data))
            task_ids.append(created_task.id)
        
        # Promote to week
        result = task_service.promote_tasks_to_week(task_ids)
        
        assert len(result) == 3
        assert set(result) == set(task_ids)
        
        # Verify status changed
        for task_id in task_ids:
            task = task_service.get_task(task_id)
            assert task.status == "week"
    
    def test_promote_tasks_to_week_partial_success(self, task_service, sample_task_data):
        """Test promoting tasks where some don't exist."""
        # Create one task
        task_create = TaskCreate(**sample_task_data)
        created_task = task_service.create_task(task_create)
        
        # Try to promote existing and non-existing tasks
        task_ids = [created_task.id, "nonexistent_id"]
        result = task_service.promote_tasks_to_week(task_ids)
        
        # Only the existing task should be updated
        assert len(result) == 1
        assert result[0] == created_task.id
        
        # Verify the existing task was updated
        task = task_service.get_task(created_task.id)
        assert task.status == "week"