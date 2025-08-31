import pytest
from app.services.goal import GoalService
from app.schemas import GoalCreate, Goal as GoalSchema
from app.exceptions import NotFoundError, ValidationError


class TestGoalService:
    """Test GoalService business logic."""
    
    @pytest.fixture
    def goal_service(self, test_db):
        """Create GoalService instance with test database."""
        return GoalService(test_db)
    
    def test_create_goal_success(self, goal_service, sample_goal_data):
        """Test successful goal creation."""
        goal_create = GoalCreate(**sample_goal_data)
        result = goal_service.create_goal(goal_create)
        
        assert isinstance(result, GoalSchema)
        assert result.title == "Test Goal"
        assert result.type == "personal"
        assert result.id.startswith("goal_")
    
    def test_create_goal_empty_title_fails(self, goal_service):
        """Test goal creation with empty title fails."""
        goal_create = GoalCreate(title="", type="personal")
        
        with pytest.raises(ValidationError) as exc_info:
            goal_service.create_goal(goal_create)
        
        assert "Goal title cannot be empty" in str(exc_info.value)
    
    def test_create_goal_whitespace_only_title_fails(self, goal_service):
        """Test goal creation with whitespace-only title fails."""
        goal_create = GoalCreate(title="   ", type="personal")
        
        with pytest.raises(ValidationError) as exc_info:
            goal_service.create_goal(goal_create)
        
        assert "Goal title cannot be empty" in str(exc_info.value)
    
    def test_get_goal_success(self, goal_service, sample_goal_data):
        """Test successful goal retrieval."""
        # Create a goal first
        goal_create = GoalCreate(**sample_goal_data)
        created_goal = goal_service.create_goal(goal_create)
        
        # Retrieve the goal
        result = goal_service.get_goal(created_goal.id)
        
        assert result.id == created_goal.id
        assert result.title == "Test Goal"
    
    def test_get_goal_not_found(self, goal_service):
        """Test getting non-existent goal raises NotFoundError."""
        with pytest.raises(NotFoundError) as exc_info:
            goal_service.get_goal("nonexistent_id")
        
        assert "Goal with id 'nonexistent_id' not found" in str(exc_info.value)
    
    def test_list_goals_default(self, goal_service, sample_goal_data):
        """Test listing goals with default parameters."""
        # Create multiple goals
        for i in range(3):
            data = sample_goal_data.copy()
            data["title"] = f"Goal {i}"
            goal_service.create_goal(GoalCreate(**data))
        
        result = goal_service.list_goals()
        
        assert len(result) == 3
        assert all(isinstance(goal, GoalSchema) for goal in result)
    
    def test_list_goals_limit_validation(self, goal_service):
        """Test list goals with invalid limit."""
        with pytest.raises(ValidationError) as exc_info:
            goal_service.list_goals(limit=1001)
        
        assert "Limit cannot exceed 1000" in str(exc_info.value)
    
    def test_list_goals_with_pagination(self, goal_service, sample_goal_data):
        """Test listing goals with pagination."""
        # Create multiple goals
        for i in range(5):
            data = sample_goal_data.copy()
            data["title"] = f"Goal {i}"
            goal_service.create_goal(GoalCreate(**data))
        
        # Test pagination
        result = goal_service.list_goals(skip=2, limit=2)
        
        assert len(result) == 2
    
    def test_delete_goal_success(self, goal_service, sample_goal_data):
        """Test successful goal deletion."""
        # Create a goal first
        goal_create = GoalCreate(**sample_goal_data)
        created_goal = goal_service.create_goal(goal_create)
        
        # Delete the goal
        result = goal_service.delete_goal(created_goal.id)
        
        assert result is True
        
        # Verify goal is deleted
        with pytest.raises(NotFoundError):
            goal_service.get_goal(created_goal.id)
    
    def test_delete_goal_not_found(self, goal_service):
        """Test deleting non-existent goal raises NotFoundError."""
        with pytest.raises(NotFoundError):
            goal_service.delete_goal("nonexistent_id")