import pytest
from app.services.project import ProjectService
from app.schemas import ProjectCreate, Project as ProjectSchema
from app.exceptions import NotFoundError, ValidationError
from app.models import User, ProviderEnum


class TestProjectService:
    """Test ProjectService business logic."""
    
    @pytest.fixture
    def project_service(self, test_db):
        """Create ProjectService instance with test database."""
        return ProjectService(test_db)

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
    
    def test_create_project_success(self, project_service, sample_project_data, test_user):
        """Test successful project creation."""
        project_create = ProjectCreate(**sample_project_data)
        result = project_service.create_project(project_create, test_user.id)
        
        assert isinstance(result, ProjectSchema)
        assert result.name == "Test Project"
        assert result.color == "#ff0000"
        assert result.id.startswith("project_")
    
    def test_create_project_empty_name_fails(self, project_service, test_user):
        """Test project creation with empty name fails."""
        project_create = ProjectCreate(name="", color="#ff0000")
        
        with pytest.raises(ValidationError) as exc_info:
            project_service.create_project(project_create, test_user.id)
        
        assert "Project name cannot be empty" in str(exc_info.value)
    
    def test_create_project_whitespace_only_name_fails(self, project_service, test_user):
        """Test project creation with whitespace-only name fails."""
        project_create = ProjectCreate(name="   ", color="#ff0000")
        
        with pytest.raises(ValidationError) as exc_info:
            project_service.create_project(project_create, test_user.id)
        
        assert "Project name cannot be empty" in str(exc_info.value)
    
    def test_get_project_success(self, project_service, sample_project_data, test_user):
        """Test successful project retrieval."""
        # Create a project first
        project_create = ProjectCreate(**sample_project_data)
        created_project = project_service.create_project(project_create, test_user.id)
        
        # Retrieve the project
        result = project_service.get_project(created_project.id, test_user.id)
        
        assert result.id == created_project.id
        assert result.name == "Test Project"
    
    def test_get_project_not_found(self, project_service, test_user):
        """Test getting non-existent project raises NotFoundError."""
        with pytest.raises(NotFoundError) as exc_info:
            project_service.get_project("nonexistent_id", test_user.id)
        
        assert "Project with id 'nonexistent_id' not found" in str(exc_info.value)
    
    def test_list_projects_default(self, project_service, sample_project_data, test_user):
        """Test listing projects with default parameters."""
        # Create multiple projects
        for i in range(3):
            data = sample_project_data.copy()
            data["name"] = f"Project {i}"
            project_service.create_project(ProjectCreate(**data), test_user.id)
        
        result = project_service.list_projects(test_user.id)
        
        assert len(result) == 3
        assert all(isinstance(project, ProjectSchema) for project in result)
    
    def test_list_projects_limit_validation(self, project_service, test_user):
        """Test list projects with invalid limit."""
        with pytest.raises(ValidationError) as exc_info:
            project_service.list_projects(test_user.id, limit=1001)
        
        assert "Limit cannot exceed 1000" in str(exc_info.value)
    
    def test_list_projects_with_pagination(self, project_service, sample_project_data, test_user):
        """Test listing projects with pagination."""
        # Create multiple projects
        for i in range(5):
            data = sample_project_data.copy()
            data["name"] = f"Project {i}"
            project_service.create_project(ProjectCreate(**data), test_user.id)
        
        # Test pagination
        result = project_service.list_projects(test_user.id, skip=2, limit=2)
        
        assert len(result) == 2
    
    def test_delete_project_success(self, project_service, sample_project_data, test_user):
        """Test successful project deletion."""
        # Create a project first
        project_create = ProjectCreate(**sample_project_data)
        created_project = project_service.create_project(project_create, test_user.id)
        
        # Delete the project
        result = project_service.delete_project(created_project.id, test_user.id)
        
        assert result is True
        
        # Verify project is deleted
        with pytest.raises(NotFoundError):
            project_service.get_project(created_project.id, test_user.id)
    
    def test_delete_project_not_found(self, project_service, test_user):
        """Test deleting non-existent project raises NotFoundError."""
        with pytest.raises(NotFoundError):
            project_service.delete_project("nonexistent_id", test_user.id)
