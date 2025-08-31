import pytest
from app.services.project import ProjectService
from app.schemas import ProjectCreate, Project as ProjectSchema
from app.exceptions import NotFoundError, ValidationError


class TestProjectService:
    """Test ProjectService business logic."""
    
    @pytest.fixture
    def project_service(self, test_db):
        """Create ProjectService instance with test database."""
        return ProjectService(test_db)
    
    def test_create_project_success(self, project_service, sample_project_data):
        """Test successful project creation."""
        project_create = ProjectCreate(**sample_project_data)
        result = project_service.create_project(project_create)
        
        assert isinstance(result, ProjectSchema)
        assert result.name == "Test Project"
        assert result.color == "#ff0000"
        assert result.id.startswith("project_")
    
    def test_create_project_empty_name_fails(self, project_service):
        """Test project creation with empty name fails."""
        project_create = ProjectCreate(name="", color="#ff0000")
        
        with pytest.raises(ValidationError) as exc_info:
            project_service.create_project(project_create)
        
        assert "Project name cannot be empty" in str(exc_info.value)
    
    def test_create_project_whitespace_only_name_fails(self, project_service):
        """Test project creation with whitespace-only name fails."""
        project_create = ProjectCreate(name="   ", color="#ff0000")
        
        with pytest.raises(ValidationError) as exc_info:
            project_service.create_project(project_create)
        
        assert "Project name cannot be empty" in str(exc_info.value)
    
    def test_get_project_success(self, project_service, sample_project_data):
        """Test successful project retrieval."""
        # Create a project first
        project_create = ProjectCreate(**sample_project_data)
        created_project = project_service.create_project(project_create)
        
        # Retrieve the project
        result = project_service.get_project(created_project.id)
        
        assert result.id == created_project.id
        assert result.name == "Test Project"
    
    def test_get_project_not_found(self, project_service):
        """Test getting non-existent project raises NotFoundError."""
        with pytest.raises(NotFoundError) as exc_info:
            project_service.get_project("nonexistent_id")
        
        assert "Project with id 'nonexistent_id' not found" in str(exc_info.value)
    
    def test_list_projects_default(self, project_service, sample_project_data):
        """Test listing projects with default parameters."""
        # Create multiple projects
        for i in range(3):
            data = sample_project_data.copy()
            data["name"] = f"Project {i}"
            project_service.create_project(ProjectCreate(**data))
        
        result = project_service.list_projects()
        
        assert len(result) == 3
        assert all(isinstance(project, ProjectSchema) for project in result)
    
    def test_list_projects_limit_validation(self, project_service):
        """Test list projects with invalid limit."""
        with pytest.raises(ValidationError) as exc_info:
            project_service.list_projects(limit=1001)
        
        assert "Limit cannot exceed 1000" in str(exc_info.value)
    
    def test_list_projects_with_pagination(self, project_service, sample_project_data):
        """Test listing projects with pagination."""
        # Create multiple projects
        for i in range(5):
            data = sample_project_data.copy()
            data["name"] = f"Project {i}"
            project_service.create_project(ProjectCreate(**data))
        
        # Test pagination
        result = project_service.list_projects(skip=2, limit=2)
        
        assert len(result) == 2
    
    def test_delete_project_success(self, project_service, sample_project_data):
        """Test successful project deletion."""
        # Create a project first
        project_create = ProjectCreate(**sample_project_data)
        created_project = project_service.create_project(project_create)
        
        # Delete the project
        result = project_service.delete_project(created_project.id)
        
        assert result is True
        
        # Verify project is deleted
        with pytest.raises(NotFoundError):
            project_service.get_project(created_project.id)
    
    def test_delete_project_not_found(self, project_service):
        """Test deleting non-existent project raises NotFoundError."""
        with pytest.raises(NotFoundError):
            project_service.delete_project("nonexistent_id")