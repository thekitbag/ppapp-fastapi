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
        assert result.type == "annual"  # Updated to match new sample data
        assert result.id.startswith("goal_")
    
    def test_create_goal_empty_title_fails(self, goal_service):
        """Test goal creation with empty title fails."""
        goal_create = GoalCreate(title="", type="annual")  # Changed to annual
        
        with pytest.raises(ValidationError) as exc_info:
            goal_service.create_goal(goal_create)
        
        assert "Goal title cannot be empty" in str(exc_info.value)
    
    def test_create_goal_whitespace_only_title_fails(self, goal_service):
        """Test goal creation with whitespace-only title fails."""
        goal_create = GoalCreate(title="   ", type="annual")  # Changed to annual
        
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

    # Goals v2: Hierarchy validation tests
    
    def test_quarterly_goal_requires_annual_parent(self, goal_service):
        """Test quarterly goal creation requires annual parent."""
        # Try to create quarterly without parent - should fail
        quarterly_create = GoalCreate(title="Q1 Goal", type="quarterly")
        
        with pytest.raises(ValidationError) as exc_info:
            goal_service.create_goal(quarterly_create)
        
        assert "Quarterly goals must have an annual parent goal" in str(exc_info.value)
    
    def test_weekly_goal_requires_quarterly_parent(self, goal_service):
        """Test weekly goal creation requires quarterly parent."""
        # Try to create weekly without parent - should fail
        weekly_create = GoalCreate(title="Week 1 Goal", type="weekly")
        
        with pytest.raises(ValidationError) as exc_info:
            goal_service.create_goal(weekly_create)
        
        assert "Weekly goals must have a quarterly parent goal" in str(exc_info.value)
    
    def test_annual_goal_cannot_have_parent(self, goal_service):
        """Test annual goal creation with parent fails."""
        # Create an annual goal first
        annual_create = GoalCreate(title="Annual Goal", type="annual")
        annual_goal = goal_service.create_goal(annual_create)
        
        # Try to create another annual with the first as parent - should fail
        annual_with_parent = GoalCreate(title="Child Annual", type="annual", parent_goal_id=annual_goal.id)
        
        with pytest.raises(ValidationError) as exc_info:
            goal_service.create_goal(annual_with_parent)
        
        assert "Annual goals cannot have a parent goal" in str(exc_info.value)
    
    def test_valid_hierarchy_creation(self, goal_service):
        """Test creating valid goal hierarchy."""
        # Create annual goal
        annual_create = GoalCreate(title="Annual Goal", type="annual", status="on_target")
        annual_goal = goal_service.create_goal(annual_create)
        
        # Create quarterly goal under annual
        quarterly_create = GoalCreate(title="Q1 Goal", type="quarterly", parent_goal_id=annual_goal.id, status="at_risk")
        quarterly_goal = goal_service.create_goal(quarterly_create)
        
        # Create weekly goal under quarterly
        weekly_create = GoalCreate(title="Week 1 Goal", type="weekly", parent_goal_id=quarterly_goal.id)
        weekly_goal = goal_service.create_goal(weekly_create)
        
        # Verify hierarchy
        assert annual_goal.parent_goal_id is None
        assert quarterly_goal.parent_goal_id == annual_goal.id
        assert weekly_goal.parent_goal_id == quarterly_goal.id
        
        # Verify statuses
        assert annual_goal.status == "on_target"
        assert quarterly_goal.status == "at_risk"
        assert weekly_goal.status == "on_target"  # Default
    
    def test_quarterly_with_wrong_parent_type_fails(self, goal_service):
        """Test quarterly goal with non-annual parent fails."""
        # Create annual and quarterly goals
        annual_create = GoalCreate(title="Annual Goal", type="annual")
        annual_goal = goal_service.create_goal(annual_create)
        
        quarterly_create = GoalCreate(title="Q1 Goal", type="quarterly", parent_goal_id=annual_goal.id)
        quarterly_goal = goal_service.create_goal(quarterly_create)
        
        # Try to create another quarterly with quarterly as parent - should fail
        bad_quarterly = GoalCreate(title="Bad Q Goal", type="quarterly", parent_goal_id=quarterly_goal.id)
        
        with pytest.raises(ValidationError) as exc_info:
            goal_service.create_goal(bad_quarterly)
        
        assert "Quarterly goals must have an annual parent" in str(exc_info.value)
    
    def test_weekly_with_wrong_parent_type_fails(self, goal_service):
        """Test weekly goal with non-quarterly parent fails."""
        # Create annual goal
        annual_create = GoalCreate(title="Annual Goal", type="annual")
        annual_goal = goal_service.create_goal(annual_create)
        
        # Try to create weekly with annual as parent - should fail
        bad_weekly = GoalCreate(title="Bad Week Goal", type="weekly", parent_goal_id=annual_goal.id)
        
        with pytest.raises(ValidationError) as exc_info:
            goal_service.create_goal(bad_weekly)
        
        assert "Weekly goals must have a quarterly parent" in str(exc_info.value)