from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List

from app.db import get_db
from app.services import ProjectService
from app.schemas import ProjectCreate, Project


router = APIRouter()


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    """Dependency to get ProjectService instance."""
    return ProjectService(db)


@router.post("", response_model=Project, status_code=201)
def create_project(
    payload: ProjectCreate,
    project_service: ProjectService = Depends(get_project_service)
):
    """Create a new project."""
    return project_service.create_project(payload)


@router.get("", response_model=List[Project])
def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    project_service: ProjectService = Depends(get_project_service)
):
    """List projects."""
    return project_service.list_projects(skip=skip, limit=limit)


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service)
):
    """Get a specific project by ID."""
    return project_service.get_project(project_id)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service)
):
    """Delete a project."""
    project_service.delete_project(project_id)
    return None