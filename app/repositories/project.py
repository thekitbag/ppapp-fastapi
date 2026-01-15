from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid

from app.models import Project
from app.schemas import ProjectCreate, ProjectUpdate, Project as ProjectSchema
from app.exceptions import NotFoundError
from .base import BaseRepository


class ProjectRepository(BaseRepository[Project, ProjectCreate, ProjectUpdate]):
    """Repository for Project operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, Project)
    
    def _gen_id(self, prefix: str = "project") -> str:
        """Generate unique ID with prefix."""
        return f"{prefix}_{uuid.uuid4()}"
    
    def create_with_id(self, project_in: ProjectCreate, user_id: str) -> Project:
        """Create project with generated ID for specific user."""
        project_data = project_in.model_dump()
        project = Project(
            id=self._gen_id("project"),
            user_id=user_id,
            **project_data
        )
        
        self.db.add(project)
        self.db.flush()
        self.db.refresh(project)
        return project
    
    def update_by_user(self, project_id: str, user_id: str, project_update: ProjectUpdate) -> Project:
        """Update project by ID for specific user."""
        project = super().get_by_user(project_id, user_id)
        if not project:
            raise NotFoundError("Project", project_id)
        
        return super().update(project, project_update)
    
    def get_by_user(self, project_id: str, user_id: str) -> Optional[Project]:
        """Get a project by ID for specific user."""
        return super().get_by_user(project_id, user_id)
    
    def get_multi_by_user(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Project]:
        """Get projects for specific user."""
        return super().get_multi_by_user(
            user_id,
            skip=skip,
            limit=limit,
            order_by=[Project.created_at.desc()],
        )
    
    def delete_by_user(self, project_id: str, user_id: str) -> bool:
        """Delete a project by ID for specific user."""
        return super().delete_by_user(project_id, user_id)
    
    def to_schema(self, project: Project) -> ProjectSchema:
        """Convert Project model to Project schema."""
        return ProjectSchema(
            id=project.id,
            name=project.name,
            color=project.color,
            milestone_title=project.milestone_title,
            milestone_due_at=project.milestone_due_at,
            created_at=project.created_at
        )
