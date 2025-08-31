from typing import List
from sqlalchemy.orm import Session
import uuid

from app.models import Project
from app.schemas import ProjectCreate, Project as ProjectSchema
from .base import BaseRepository


class ProjectRepository(BaseRepository[Project, ProjectCreate, dict]):
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
    
    def to_schema(self, project: Project) -> ProjectSchema:
        """Convert Project model to Project schema."""
        return ProjectSchema(
            id=project.id,
            name=project.name,
            color=project.color,
            created_at=project.created_at
        )