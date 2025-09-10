from typing import List
from sqlalchemy.orm import Session

from app.repositories import ProjectRepository
from app.schemas import ProjectCreate, ProjectUpdate, Project as ProjectSchema
from app.exceptions import NotFoundError, ValidationError
from .base import BaseService


class ProjectService(BaseService):
    """Service for project business logic."""
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.project_repo = ProjectRepository(db)
    
    def create_project(self, project_in: ProjectCreate, user_id: str) -> ProjectSchema:
        """Create a new project."""
        try:
            self.logger.info(f"Creating project: {project_in.name}")
            
            if not project_in.name or not project_in.name.strip():
                raise ValidationError("Project name cannot be empty")
            
            project = self.project_repo.create_with_id(project_in, user_id)
            self.commit()
            
            self.logger.info(f"Project created successfully: {project.id}")
            return self.project_repo.to_schema(project)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to create project: {str(e)}")
            raise
    
    def get_project(self, project_id: str, user_id: str) -> ProjectSchema:
        """Get a project by ID."""
        self.logger.debug(f"Fetching project: {project_id}")
        
        project = self.project_repo.get_by_user(project_id, user_id)
        if not project:
            raise NotFoundError("Project", project_id)
        
        return self.project_repo.to_schema(project)
    
    def list_projects(self, user_id: str, skip: int = 0, limit: int = 100) -> List[ProjectSchema]:
        """List projects."""
        self.logger.debug("Listing projects")
        
        if limit > 1000:
            raise ValidationError("Limit cannot exceed 1000")
        
        projects = self.project_repo.get_multi_by_user(user_id, skip=skip, limit=limit)
        return [self.project_repo.to_schema(project) for project in projects]
    
    def update_project(self, project_id: str, user_id: str, project_update: ProjectUpdate) -> ProjectSchema:
        """Update a project (partial update)."""
        try:
            self.logger.info(f"Updating project: {project_id}")
            
            existing_project = self.project_repo.get_by_user(project_id, user_id)
            if not existing_project:
                raise NotFoundError("Project", project_id)
            
            if project_update.name is not None and (not project_update.name or not project_update.name.strip()):
                raise ValidationError("Project name cannot be empty")
            
            updated_project = self.project_repo.update_by_user(project_id, user_id, project_update)
            self.commit()
            
            self.logger.info(f"Project updated successfully: {project_id}")
            return self.project_repo.to_schema(updated_project)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to update project {project_id}: {str(e)}")
            raise
    
    def delete_project(self, project_id: str, user_id: str) -> bool:
        """Delete a project."""
        try:
            self.logger.info(f"Deleting project: {project_id}")
            
            if not self.project_repo.get_by_user(project_id, user_id):
                raise NotFoundError("Project", project_id)
            
            deleted = self.project_repo.delete_by_user(project_id, user_id)
            self.commit()
            
            self.logger.info(f"Project deleted successfully: {project_id}")
            return deleted
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to delete project {project_id}: {str(e)}")
            raise