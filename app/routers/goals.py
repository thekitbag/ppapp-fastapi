from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.db import SessionLocal
from app import models, schemas

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.GoalOut)
def create_goal(goal: schemas.GoalCreate, db: Session = Depends(get_db)):
    """Create a new goal."""
    db_goal = models.Goal(
        id=str(uuid.uuid4()),
        title=goal.title,
        description=goal.description,
        type=goal.type,
    )
    db.add(db_goal)
    db.commit()
    db.refresh(db_goal)
    return db_goal

@router.get("/", response_model=List[schemas.GoalOut])
def list_goals(db: Session = Depends(get_db)):
    """List all goals."""
    goals = db.query(models.Goal).all()
    return goals

@router.get("/{goal_id}", response_model=schemas.GoalDetail)
def get_goal(goal_id: str, db: Session = Depends(get_db)):
    """Get a goal with its key results and linked tasks."""
    goal = db.query(models.Goal).filter(models.Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    # Get key results
    key_results = db.query(models.GoalKR).filter(models.GoalKR.goal_id == goal_id).all()
    
    # Get linked tasks
    task_links = db.query(models.TaskGoal).filter(models.TaskGoal.goal_id == goal_id).all()
    task_ids = [link.task_id for link in task_links]
    
    tasks = []
    if task_ids:
        tasks = db.query(models.Task).filter(models.Task.id.in_(task_ids)).all()
    
    # Build response with goals populated for tasks
    task_out_list = []
    for task in tasks:
        # Get all goals for this task
        task_goal_links = db.query(models.TaskGoal).filter(models.TaskGoal.task_id == task.id).all()
        goal_ids = [link.goal_id for link in task_goal_links]
        task_goals = []
        if goal_ids:
            task_goals = db.query(models.Goal).filter(models.Goal.id.in_(goal_ids)).all()
        
        task_out = schemas.TaskOut(
            id=task.id,
            title=task.title,
            status=task.status.value,
            sort_order=task.sort_order,
            tags=[tag.name for tag in task.tags],
            effort_minutes=task.effort_minutes,
            hard_due_at=task.hard_due_at,
            soft_due_at=task.soft_due_at,
            project_id=task.project_id,
            goal_id=task.goal_id,  # Keep for backward compatibility
            goals=[schemas.GoalSummary(id=g.id, title=g.title) for g in task_goals],
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        task_out_list.append(task_out)
    
    return schemas.GoalDetail(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        type=goal.type,
        created_at=goal.created_at,
        key_results=[schemas.KROut(
            id=kr.id,
            goal_id=kr.goal_id,
            name=kr.name,
            target_value=kr.target_value,
            unit=kr.unit,
            baseline_value=kr.baseline_value,
            created_at=kr.created_at,
        ) for kr in key_results],
        tasks=task_out_list,
    )

@router.patch("/{goal_id}", response_model=schemas.GoalOut)
def update_goal(goal_id: str, goal_update: schemas.GoalUpdate, db: Session = Depends(get_db)):
    """Update a goal."""
    db_goal = db.query(models.Goal).filter(models.Goal.id == goal_id).first()
    if not db_goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    update_data = goal_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_goal, field, value)
    
    db.commit()
    db.refresh(db_goal)
    return db_goal

@router.post("/{goal_id}/krs", response_model=schemas.KROut)
def create_key_result(goal_id: str, kr: schemas.KRCreate, db: Session = Depends(get_db)):
    """Create a key result for a goal."""
    # Verify goal exists
    goal = db.query(models.Goal).filter(models.Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    db_kr = models.GoalKR(
        id=str(uuid.uuid4()),
        goal_id=goal_id,
        name=kr.name,
        target_value=kr.target_value,
        unit=kr.unit,
        baseline_value=kr.baseline_value,
    )
    db.add(db_kr)
    db.commit()
    db.refresh(db_kr)
    return db_kr

@router.delete("/{goal_id}/krs/{kr_id}")
def delete_key_result(goal_id: str, kr_id: str, db: Session = Depends(get_db)):
    """Delete a key result."""
    db_kr = db.query(models.GoalKR).filter(
        models.GoalKR.id == kr_id, 
        models.GoalKR.goal_id == goal_id
    ).first()
    if not db_kr:
        raise HTTPException(status_code=404, detail="Key result not found")
    
    db.delete(db_kr)
    db.commit()
    return {"status": "deleted"}

@router.post("/{goal_id}/link-tasks", response_model=schemas.TaskGoalLinkResponse)
def link_tasks_to_goal(goal_id: str, link_data: schemas.TaskGoalLink, db: Session = Depends(get_db)):
    """Link tasks to a goal."""
    # Verify goal exists
    goal = db.query(models.Goal).filter(models.Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    # Verify tasks exist
    tasks = db.query(models.Task).filter(models.Task.id.in_(link_data.task_ids)).all()
    task_ids_found = {task.id for task in tasks}
    task_ids_requested = set(link_data.task_ids)
    
    missing_tasks = task_ids_requested - task_ids_found
    if missing_tasks:
        raise HTTPException(
            status_code=400, 
            detail=f"Tasks not found: {list(missing_tasks)}"
        )
    
    # Check which tasks are already linked
    existing_links = db.query(models.TaskGoal).filter(
        models.TaskGoal.goal_id == goal_id,
        models.TaskGoal.task_id.in_(link_data.task_ids)
    ).all()
    already_linked = {link.task_id for link in existing_links}
    
    # Create new links for tasks not already linked
    to_link = task_ids_requested - already_linked
    linked = []
    
    for task_id in to_link:
        db_link = models.TaskGoal(
            id=str(uuid.uuid4()),
            task_id=task_id,
            goal_id=goal_id,
        )
        db.add(db_link)
        linked.append(task_id)
    
    db.commit()
    
    return schemas.TaskGoalLinkResponse(
        linked=linked,
        already_linked=list(already_linked)
    )

@router.delete("/{goal_id}/link-tasks", response_model=schemas.TaskGoalLinkResponse)
def unlink_tasks_from_goal(goal_id: str, link_data: schemas.TaskGoalLink, db: Session = Depends(get_db)):
    """Unlink tasks from a goal."""
    # Verify goal exists
    goal = db.query(models.Goal).filter(models.Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    # Find existing links to remove
    existing_links = db.query(models.TaskGoal).filter(
        models.TaskGoal.goal_id == goal_id,
        models.TaskGoal.task_id.in_(link_data.task_ids)
    ).all()
    
    unlinked = []
    for link in existing_links:
        unlinked.append(link.task_id)
        db.delete(link)
    
    not_linked = set(link_data.task_ids) - set(unlinked)
    
    db.commit()
    
    return schemas.TaskGoalLinkResponse(
        linked=unlinked,  # Actually unlinked
        already_linked=list(not_linked)  # Were not linked to begin with
    )