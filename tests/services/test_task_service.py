import pytest
from unittest.mock import Mock, patch
from app.services.task import TaskService
from app.repositories.task import TaskRepository
from app.schemas import TaskCreate, TaskOut
from app.exceptions import NotFoundError, ValidationError
from app.models import Task, StatusEnum, User, ProviderEnum


class TestTaskService:
    """Test TaskService business logic."""
    
    @pytest.fixture
    def task_service(self, test_db):
        """Create TaskService instance with test database."""
        return TaskService(test_db)

    @pytest.fixture
    def test_user(self, test_db):
        """Create and return a test user in the in-memory DB."""
        user = User(
            id="test-user-id",
            provider=ProviderEnum.google,
            provider_sub="test-sub",
            email="test@example.com",
            name="Test User",
        )
        test_db.add(user)
        test_db.commit()
        return user
    
    def test_create_task_success(self, task_service, sample_task_data, test_user):
        """Test successful task creation."""
        task_create = TaskCreate(**sample_task_data)
        result, was_created = task_service.create_task(task_create, test_user.id)

        assert isinstance(result, TaskOut)
        assert was_created is True  # Should be a new creation
        assert result.title == "Test Task"
        assert result.status == "backlog"
        assert "test" in result.tags
        assert "sample" in result.tags
    
    def test_create_task_empty_title_fails(self, task_service, test_user):
        """Test task creation with empty title fails."""
        task_create = TaskCreate(title="", description="Test")

        with pytest.raises(ValidationError) as exc_info:
            task_service.create_task(task_create, test_user.id)

        assert "title cannot be empty" in str(exc_info.value)
    
    def test_create_task_whitespace_only_title_fails(self, task_service, test_user):
        """Test task creation with whitespace-only title fails."""
        task_create = TaskCreate(title="   ", description="Test")
        
        with pytest.raises(ValidationError) as exc_info:
            task_service.create_task(task_create, test_user.id)
        
        assert "title cannot be empty" in str(exc_info.value)
    
    def test_get_task_success(self, task_service, sample_task_data, test_user):
        """Test successful task retrieval."""
        # Create a task first
        task_create = TaskCreate(**sample_task_data)
        created_task, _ = task_service.create_task(task_create, test_user.id)

        # Retrieve the task
        result = task_service.get_task(created_task.id, test_user.id)

        assert result.id == created_task.id
        assert result.title == "Test Task"
    
    def test_get_task_not_found(self, task_service, test_user):
        """Test getting non-existent task raises NotFoundError."""
        with pytest.raises(NotFoundError) as exc_info:
            task_service.get_task("nonexistent_id", test_user.id)
        
        assert "Task with id 'nonexistent_id' not found" in str(exc_info.value)
    
    def test_list_tasks_default(self, task_service, sample_task_data, test_user):
        """Test listing tasks with default parameters."""
        # Create multiple tasks
        for i in range(3):
            data = sample_task_data.copy()
            data["title"] = f"Task {i}"
            task_service.create_task(TaskCreate(**data), test_user.id)

        result = task_service.list_tasks(test_user.id)

        assert len(result) == 3
        assert all(isinstance(task, TaskOut) for task in result)
    
    def test_list_tasks_with_status_filter(self, task_service, sample_task_data, test_user):
        """Test listing tasks with status filter."""
        # Create tasks with different statuses
        data1 = sample_task_data.copy()
        data1["status"] = "backlog"
        task_service.create_task(TaskCreate(**data1), test_user.id)
        
        data2 = sample_task_data.copy()
        data2["title"] = "Week Task"
        data2["status"] = "week"
        task_service.create_task(TaskCreate(**data2), test_user.id)
        
        result = task_service.list_tasks(test_user.id, status=["week"]) 
        
        assert len(result) == 1
        assert result[0].title == "Week Task"
        assert result[0].status == "week"
    
    def test_list_tasks_limit_validation(self, task_service, test_user):
        """Test list tasks with invalid limit."""
        with pytest.raises(ValidationError) as exc_info:
            task_service.list_tasks(test_user.id, limit=1001)
        
        assert "Limit cannot exceed 1000" in str(exc_info.value)
    
    def test_update_task_success(self, task_service, sample_task_data, test_user):
        """Test successful task update."""
        # Create a task first
        task_create = TaskCreate(**sample_task_data)
        created_task, _ = task_service.create_task(task_create, test_user.id)

        # Update the task
        update_data = {"title": "Updated Task", "status": "doing"}
        result = task_service.update_task(created_task.id, test_user.id, update_data)

        assert result.title == "Updated Task"
        assert result.status == "doing"
    
    def test_update_task_empty_title_fails(self, task_service, sample_task_data, test_user):
        """Test updating task with empty title fails."""
        # Create a task first
        task_create = TaskCreate(**sample_task_data)
        created_task, _ = task_service.create_task(task_create, test_user.id)

        # Try to update with empty title
        update_data = {"title": ""}

        with pytest.raises(ValidationError) as exc_info:
            task_service.update_task(created_task.id, test_user.id, update_data)

        assert "title cannot be empty" in str(exc_info.value)
    
    def test_update_task_not_found(self, task_service, test_user):
        """Test updating non-existent task raises NotFoundError."""
        update_data = {"title": "Updated Task"}
        
        with pytest.raises(NotFoundError):
            task_service.update_task("nonexistent_id", test_user.id, update_data)
    
    def test_delete_task_success(self, task_service, sample_task_data, test_user):
        """Test successful task deletion."""
        # Create a task first
        task_create = TaskCreate(**sample_task_data)
        created_task, _ = task_service.create_task(task_create, test_user.id)

        # Delete the task
        result = task_service.delete_task(created_task.id, test_user.id)

        assert result is True

        # Verify task is deleted
        with pytest.raises(NotFoundError):
            task_service.get_task(created_task.id, test_user.id)
    
    def test_delete_task_not_found(self, task_service, test_user):
        """Test deleting non-existent task raises NotFoundError."""
        with pytest.raises(NotFoundError):
            task_service.delete_task("nonexistent_id", test_user.id)
    
    def test_promote_tasks_to_week_success(self, task_service, sample_task_data, test_user):
        """Test promoting tasks to week status."""
        # Create multiple tasks
        task_ids = []
        for i in range(3):
            data = sample_task_data.copy()
            data["title"] = f"Task {i}"
            created_task, _ = task_service.create_task(TaskCreate(**data), test_user.id)
            task_ids.append(created_task.id)
        
        # Promote to week
        result = task_service.promote_tasks_to_week(task_ids, test_user.id)
        
        assert len(result) == 3
        assert set(result) == set(task_ids)
        
        # Verify status changed
        for task_id in task_ids:
            task = task_service.get_task(task_id, test_user.id)
            assert task.status == "week"
    
    def test_promote_tasks_to_week_partial_success(self, task_service, sample_task_data, test_user):
        """Test promoting tasks where some don't exist."""
        # Create one task
        task_create = TaskCreate(**sample_task_data)
        created_task, _ = task_service.create_task(task_create, test_user.id)

        # Try to promote existing and non-existing tasks
        task_ids = [created_task.id, "nonexistent_id"]
        result = task_service.promote_tasks_to_week(task_ids, test_user.id)

        # Only the existing task should be updated
        assert len(result) == 1
        assert result[0] == created_task.id

        # Verify the existing task was updated
        task = task_service.get_task(created_task.id, test_user.id)
        assert task.status == "week"
