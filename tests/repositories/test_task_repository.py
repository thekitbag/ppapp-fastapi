import pytest
from app.repositories.task import TaskRepository
from app.schemas import TaskCreate
from app.models import Task, Tag
from app.exceptions import NotFoundError


class TestTaskRepository:
    """Test TaskRepository data access logic."""
    
    @pytest.fixture
    def task_repo(self, test_db):
        """Create TaskRepository instance with test database."""
        return TaskRepository(test_db)
    
    def test_create_with_tags_success(self, task_repo, sample_task_data):
        """Test creating task with tags."""
        task_create = TaskCreate(**sample_task_data)
        result = task_repo.create_with_tags(task_create)
        
        assert isinstance(result, Task)
        assert result.title == "Test Task"
        assert len(result.tags) == 2
        tag_names = [tag.name for tag in result.tags]
        assert "test" in tag_names
        assert "sample" in tag_names
    
    def test_create_with_tags_reuses_existing_tags(self, task_repo, test_db, sample_task_data):
        """Test that creating tasks reuses existing tags."""
        # Create first task with tags
        task_create1 = TaskCreate(**sample_task_data)
        task1 = task_repo.create_with_tags(task_create1)
        
        # Create second task with same tags
        data2 = sample_task_data.copy()
        data2["title"] = "Task 2"
        task_create2 = TaskCreate(**data2)
        task2 = task_repo.create_with_tags(task_create2)
        
        # Check that tags are reused (same tag objects)
        task1_tag_ids = {tag.id for tag in task1.tags}
        task2_tag_ids = {tag.id for tag in task2.tags}
        assert task1_tag_ids == task2_tag_ids
        
        # Verify total tag count in database
        total_tags = test_db.query(Tag).count()
        assert total_tags == 2  # Only 2 unique tags should exist
    
    def test_get_or_create_tag_creates_new(self, task_repo, test_db):
        """Test get_or_create_tag creates new tag when it doesn't exist."""
        tag = task_repo.get_or_create_tag("new_tag")
        
        assert isinstance(tag, Tag)
        assert tag.name == "new_tag"
        assert tag.id.startswith("tag_")
        
        # Verify it's in the database
        db_tag = test_db.query(Tag).filter(Tag.name == "new_tag").first()
        assert db_tag is not None
        assert db_tag.id == tag.id
    
    def test_get_or_create_tag_returns_existing(self, task_repo, test_db):
        """Test get_or_create_tag returns existing tag."""
        # Create tag first
        tag1 = task_repo.get_or_create_tag("existing_tag")
        
        # Try to create same tag again
        tag2 = task_repo.get_or_create_tag("existing_tag")
        
        # Should return the same tag
        assert tag1.id == tag2.id
        assert tag1.name == tag2.name
        
        # Verify only one tag exists in database
        tag_count = test_db.query(Tag).filter(Tag.name == "existing_tag").count()
        assert tag_count == 1
    
    def test_update_with_tags_success(self, task_repo, sample_task_data):
        """Test updating task with tags."""
        # Create task first
        task_create = TaskCreate(**sample_task_data)
        task = task_repo.create_with_tags(task_create)
        
        # Update task
        update_data = {
            "title": "Updated Task",
            "status": "doing",
            "tags": ["updated", "modified"]
        }
        result = task_repo.update_with_tags(task.id, update_data)
        
        assert result.title == "Updated Task"
        assert result.status.value == "doing"
        assert len(result.tags) == 2
        tag_names = [tag.name for tag in result.tags]
        assert "updated" in tag_names
        assert "modified" in tag_names
    
    def test_update_with_tags_not_found(self, task_repo):
        """Test updating non-existent task raises NotFoundError."""
        update_data = {"title": "Updated Task"}
        
        with pytest.raises(NotFoundError):
            task_repo.update_with_tags("nonexistent_id", update_data)
    
    def test_get_by_status_single_status(self, task_repo, sample_task_data):
        """Test getting tasks by single status."""
        # Create tasks with different statuses
        data1 = sample_task_data.copy()
        data1["status"] = "backlog"
        task1 = task_repo.create_with_tags(TaskCreate(**data1))
        
        data2 = sample_task_data.copy()
        data2["title"] = "Week Task"
        data2["status"] = "week"
        task2 = task_repo.create_with_tags(TaskCreate(**data2))
        
        # Get tasks with specific status
        result = task_repo.get_by_status(["week"])
        
        assert len(result) == 1
        assert result[0].id == task2.id
        assert result[0].title == "Week Task"
    
    def test_get_by_status_multiple_statuses(self, task_repo, sample_task_data):
        """Test getting tasks by multiple statuses."""
        # Create tasks with different statuses
        statuses = ["backlog", "week", "doing"]
        tasks = []
        
        for i, status in enumerate(statuses):
            data = sample_task_data.copy()
            data["title"] = f"Task {i}"
            data["status"] = status
            task = task_repo.create_with_tags(TaskCreate(**data))
            tasks.append(task)
        
        # Get tasks with multiple statuses
        result = task_repo.get_by_status(["backlog", "week"])
        
        assert len(result) == 2
        result_statuses = [task.status.value for task in result]
        assert "backlog" in result_statuses
        assert "week" in result_statuses
        assert "doing" not in result_statuses
    
    def test_to_schema_conversion(self, task_repo, sample_task_data):
        """Test converting Task model to TaskOut schema."""
        # Create task
        task_create = TaskCreate(**sample_task_data)
        task = task_repo.create_with_tags(task_create)
        
        # Convert to schema
        task_out = task_repo.to_schema(task)
        
        assert task_out.id == task.id
        assert task_out.title == task.title
        assert task_out.status == task.status.value
        assert set(task_out.tags) == {"test", "sample"}
        assert task_out.created_at is not None
        assert task_out.updated_at is not None