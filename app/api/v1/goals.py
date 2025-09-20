from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.db import get_db
from app.services import GoalService
from app.schemas import GoalCreate, GoalOut, GoalDetail, GoalUpdate, KRCreate, KROut, TaskGoalLink, TaskGoalLinkResponse, GoalNode, GoalType
from app.api.v1.auth import get_current_user_dep

router = APIRouter()


def get_goal_service(db: Session = Depends(get_db)) -> GoalService:
    """Dependency to get GoalService instance."""
    return GoalService(db)


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(
    payload: GoalCreate,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Create a new goal for authenticated user."""
    return goal_service.create_goal(payload, current_user["user_id"])


@router.get("", response_model=List[GoalOut])
def list_goals(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_closed: bool = Query(None, description="Filter by closed status. None = no filter (all goals)"),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """List goals for authenticated user with optional closed status filter."""
    return goal_service.list_goals(current_user["user_id"], skip=skip, limit=limit, is_closed=is_closed)


# Goals v2: Tree and type endpoints must come before /{goal_id} to avoid conflicts
@router.get("/tree", response_model=List[GoalNode])
def get_goals_tree(
    include_tasks: bool = Query(False, description="Include linked tasks for weekly goals"),
    include_closed: bool = Query(False, description="Include closed goals in tree. Default: open goals only"),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Get hierarchical tree of goals (Annual → Quarterly → Weekly) for authenticated user."""
    return goal_service.get_goals_tree(current_user["user_id"], include_tasks=include_tasks, include_closed=include_closed)


@router.get("/by-type", response_model=List[GoalOut])
def get_goals_by_type(
    type: GoalType = Query(..., description="Goal type to filter by"),
    parent_id: str = Query(None, description="Parent goal ID (for quarterly/weekly goals)"),
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Get goals filtered by type and optionally by parent for picker UIs for authenticated user."""
    return goal_service.get_goals_by_type(current_user["user_id"], type, parent_id)


@router.get("/{goal_id}", response_model=GoalDetail)
def get_goal(
    goal_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Get a goal with its key results and linked tasks for authenticated user."""
    return goal_service.get_goal_detail(goal_id, current_user["user_id"])


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: str,
    goal_update: GoalUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Update a goal for authenticated user."""
    update_data = goal_update.dict(exclude_unset=True)
    return goal_service.update_goal(goal_id, current_user["user_id"], update_data)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(
    goal_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Delete a goal for authenticated user."""
    goal_service.delete_goal(goal_id, current_user["user_id"])
    return None


@router.post("/{goal_id}/krs", response_model=KROut, status_code=201)
def create_key_result(
    goal_id: str, 
    kr: KRCreate,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Create a key result for a goal for authenticated user."""
    return goal_service.create_key_result(goal_id, current_user["user_id"], kr)


@router.delete("/{goal_id}/krs/{kr_id}", status_code=204)
def delete_key_result(
    goal_id: str,
    kr_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Delete a key result for authenticated user."""
    goal_service.delete_key_result(goal_id, current_user["user_id"], kr_id)
    return None


@router.post("/{goal_id}/link-tasks", response_model=TaskGoalLinkResponse)
def link_tasks_to_goal(
    goal_id: str,
    link_data: TaskGoalLink,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Link tasks to a goal for authenticated user."""
    return goal_service.link_tasks_to_goal(goal_id, current_user["user_id"], link_data)


@router.delete("/{goal_id}/link-tasks", response_model=TaskGoalLinkResponse)
def unlink_tasks_from_goal(
    goal_id: str,
    link_data: TaskGoalLink,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Unlink tasks from a goal for authenticated user."""
    return goal_service.unlink_tasks_from_goal(goal_id, current_user["user_id"], link_data)


@router.post("/{goal_id}/close", response_model=GoalOut)
def close_goal(
    goal_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Close a goal for authenticated user. Idempotent: returns 200 if already closed."""
    return goal_service.close_goal(goal_id, current_user["user_id"])


@router.post("/{goal_id}/reopen", response_model=GoalOut)
def reopen_goal(
    goal_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
    goal_service: GoalService = Depends(get_goal_service)
):
    """Reopen a goal for authenticated user. Idempotent: returns 200 if already open."""
    return goal_service.reopen_goal(goal_id, current_user["user_id"])


