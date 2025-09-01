from typing import List
from sqlalchemy.orm import Session
import uuid

from app.models import Project
from app.schemas import ProjectCreate, ProjectUpdate, Project as ProjectSchema
from .base import BaseRepository


class ProjectRepository(BaseRepository[Project, ProjectCreate, ProjectUpdate]):
    """Repository for Project operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, Project)
    
    def _gen_id(self, prefix: str = "project") -> str:
        """Generate unique ID with prefix."""
        return f"{prefix}_{uuid.uuid4()}"
    
    def create_with_id(self, project_in: ProjectCreate) -> Project:
        """Create project with generated ID."""
        project_data = project_in.model_dump()
        project = Project(
            id=self._gen_id("project"),
            **project_data
        )
        
        self.db.add(project)
        self.db.flush()
        self.db.refresh(project)
        return project
    
    def update(self, project_id: str, project_update: ProjectUpdate) -> Project:
        """Update project by ID."""
        project = self.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        return super().update(project, project_update)
    
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