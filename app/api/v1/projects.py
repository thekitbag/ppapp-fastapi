from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.db import get_db
from app.services import ProjectService
from app.schemas import ProjectCreate, ProjectUpdate, Project
from app.api.v1.auth import get_current_user_dep


router = APIRouter()


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    """Dependency to get ProjectService instance."""
    return ProjectService(db)


@router.post("", response_model=Project, status_code=201)
def create_project(
    payload: ProjectCreate,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    project_service: ProjectService = Depends(get_project_service)
):
    """Create a new project for authenticated user."""
    return project_service.create_project(payload, current_user["user_id"])


@router.get("", response_model=List[Project])
def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    project_service: ProjectService = Depends(get_project_service)
):
    """List projects for authenticated user."""
    return project_service.list_projects(current_user["user_id"], skip=skip, limit=limit)


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    project_service: ProjectService = Depends(get_project_service)
):
    """Get a specific project by ID for authenticated user."""
    return project_service.get_project(project_id, current_user["user_id"])


@router.patch("/{project_id}", response_model=Project)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    project_service: ProjectService = Depends(get_project_service)
):
    """Update a project (partial update) for authenticated user."""
    return project_service.update_project(project_id, current_user["user_id"], payload)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    project_service: ProjectService = Depends(get_project_service)
):
    """Delete a project for authenticated user."""
    project_service.delete_project(project_id, current_user["user_id"])
    return None