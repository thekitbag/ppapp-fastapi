from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.repositories import TaskRepository
from app.schemas import TaskCreate, TaskOut
from app.exceptions import NotFoundError, ValidationError
from .base import BaseService


class TaskService(BaseService):
    """Service for multi-tenant task business logic."""
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.task_repo = TaskRepository(db)
    
    def create_task(self, task_in: TaskCreate, user_id: str) -> TaskOut:
        """Create a new task for specific user."""
        try:
            self.logger.info(f"Creating task for user {user_id}: {task_in.title}")
            
            if not task_in.title or not task_in.title.strip():
                raise ValidationError("Task title cannot be empty")
            
            task = self.task_repo.create_with_tags(task_in, user_id)
            self.commit()
            
            self.logger.info(f"Task created successfully: {task.id}")
            return self.task_repo.to_schema(task)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to create task: {str(e)}")
            raise
    
    def get_task(self, task_id: str, user_id: str) -> TaskOut:
        """Get a task by ID for specific user."""
        self.logger.debug(f"Fetching task {task_id} for user {user_id}")
        
        task = self.task_repo.get_by_user(task_id, user_id)
        if not task:
            raise NotFoundError("Task", task_id)
        
        return self.task_repo.to_schema(task)
    
    def list_tasks(
        self, 
        user_id: str,
        status: Optional[List[str]] = None,
        skip: int = 0,
        limit: Optional[int] = None
    ) -> List[TaskOut]:
        """List tasks for specific user with optional filtering. Excludes archived by default unless specifically requested."""
        self.logger.debug(f"Listing tasks for user {user_id} with status filter: {status}")
        
        # If no status filter provided, exclude archived by default
        if status is None:
            status = ["backlog", "doing", "done", "week", "today", "waiting"]
        
        # Apply limit validation only if limit is specified
        if limit is not None and limit > 1000:
            raise ValidationError("Limit cannot exceed 1000")
        
        tasks = self.task_repo.get_by_status(user_id, status, skip=skip, limit=limit)
        return self.task_repo.to_schema_batch(tasks)  # Use batch method for better performance
    
    def update_task(self, task_id: str, user_id: str, update_data: Dict[str, Any]) -> TaskOut:
        """Update a task for specific user."""
        try:
            self.logger.info(f"Updating task {task_id} for user {user_id}")
            
            # Validate update data
            if "title" in update_data and not update_data["title"].strip():
                raise ValidationError("Task title cannot be empty")
            
            task = self.task_repo.update_with_tags(task_id, user_id, update_data)
            self.commit()
            
            self.logger.info(f"Task updated successfully: {task_id}")
            return self.task_repo.to_schema(task)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to update task {task_id}: {str(e)}")
            raise
    
    def delete_task(self, task_id: str, user_id: str) -> bool:
        """Delete a task for specific user."""
        try:
            self.logger.info(f"Deleting task {task_id} for user {user_id}")
            
            if not self.task_repo.get_by_user(task_id, user_id):
                raise NotFoundError("Task", task_id)
            
            deleted = self.task_repo.delete_by_user(task_id, user_id)
            self.commit()
            
            self.logger.info(f"Task deleted successfully: {task_id}")
            return deleted
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to delete task {task_id}: {str(e)}")
            raise
    
    def promote_tasks_to_week(self, task_ids: List[str], user_id: str) -> List[str]:
        """Promote multiple tasks to week status for specific user."""
        try:
            self.logger.info(f"Promoting {len(task_ids)} tasks to week status for user {user_id}")
            
            updated_ids = []
            for task_id in task_ids:
                task = self.task_repo.get_by_user(task_id, user_id)
                if task:
                    self.task_repo.update_with_tags(task_id, user_id, {"status": "week"})
                    updated_ids.append(task_id)
            
            self.commit()
            self.logger.info(f"Successfully promoted {len(updated_ids)} tasks to week")
            return updated_ids
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to promote tasks to week: {str(e)}")
            raise
    
    def validate_cross_user_resources(self, user_id: str, task_id: str = None, goal_id: str = None, project_id: str = None) -> bool:
        """Validate that resources belong to the same user before creating links."""
        from app.models import Goal, Project
        
        # Validate task ownership
        if task_id:
            task = self.task_repo.get_by_user(task_id, user_id)
            if not task:
                raise NotFoundError("Task", task_id)
        
        # Validate goal ownership
        if goal_id:
            goal = self.db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user_id).first()
            if not goal:
                raise NotFoundError("Goal", goal_id)
        
        # Validate project ownership
        if project_id:
            project = self.db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
            if not project:
                raise NotFoundError("Project", project_id)
        
        return True
    
    def link_task_to_goal(self, task_id: str, goal_id: str, user_id: str, weight: float = None) -> bool:
        """Link a task to a goal with cross-user validation."""
        try:
            self.logger.info(f"Linking task {task_id} to goal {goal_id} for user {user_id}")
            
            # Validate both resources belong to the same user
            self.validate_cross_user_resources(user_id, task_id=task_id, goal_id=goal_id)
            
            from app.models import TaskGoal
            import uuid
            
            # Check if link already exists
            existing_link = self.db.query(TaskGoal).filter(
                TaskGoal.task_id == task_id,
                TaskGoal.goal_id == goal_id,
                TaskGoal.user_id == user_id
            ).first()
            
            if existing_link:
                self.logger.warning(f"Task-goal link already exists: {task_id} -> {goal_id}")
                return False
            
            # Create new link
            task_goal = TaskGoal(
                id=f"tg_{uuid.uuid4()}",
                task_id=task_id,
                goal_id=goal_id,
                user_id=user_id,
                weight=weight
            )
            
            self.db.add(task_goal)
            self.commit()
            
            self.logger.info(f"Successfully linked task to goal: {task_id} -> {goal_id}")
            return True
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to link task to goal: {str(e)}")
            raise