from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.repositories import TaskRepository
from app.schemas import TaskCreate, TaskOut
from app.exceptions import NotFoundError, ValidationError
from .base import BaseService


class TaskService(BaseService):
    """Service for task business logic."""
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.task_repo = TaskRepository(db)
    
    def create_task(self, task_in: TaskCreate) -> TaskOut:
        """Create a new task."""
        try:
            self.logger.info(f"Creating task: {task_in.title}")
            
            if not task_in.title or not task_in.title.strip():
                raise ValidationError("Task title cannot be empty")
            
            task = self.task_repo.create_with_tags(task_in)
            self.commit()
            
            self.logger.info(f"Task created successfully: {task.id}")
            return self.task_repo.to_schema(task)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to create task: {str(e)}")
            raise
    
    def get_task(self, task_id: str) -> TaskOut:
        """Get a task by ID."""
        self.logger.debug(f"Fetching task: {task_id}")
        
        task = self.task_repo.get(task_id)
        if not task:
            raise NotFoundError("Task", task_id)
        
        return self.task_repo.to_schema(task)
    
    def list_tasks(
        self, 
        status: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[TaskOut]:
        """List tasks with optional filtering."""
        self.logger.debug(f"Listing tasks with status filter: {status}")
        
        if limit > 1000:
            raise ValidationError("Limit cannot exceed 1000")
        
        tasks = self.task_repo.get_by_status(status or [], skip=skip, limit=limit)
        return [self.task_repo.to_schema(task) for task in tasks]
    
    def update_task(self, task_id: str, update_data: Dict[str, Any]) -> TaskOut:
        """Update a task."""
        try:
            self.logger.info(f"Updating task: {task_id}")
            
            # Validate update data
            if "title" in update_data and not update_data["title"].strip():
                raise ValidationError("Task title cannot be empty")
            
            task = self.task_repo.update_with_tags(task_id, update_data)
            self.commit()
            
            self.logger.info(f"Task updated successfully: {task_id}")
            return self.task_repo.to_schema(task)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to update task {task_id}: {str(e)}")
            raise
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        try:
            self.logger.info(f"Deleting task: {task_id}")
            
            if not self.task_repo.get(task_id):
                raise NotFoundError("Task", task_id)
            
            deleted = self.task_repo.delete(task_id)
            self.commit()
            
            self.logger.info(f"Task deleted successfully: {task_id}")
            return deleted
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to delete task {task_id}: {str(e)}")
            raise
    
    def promote_tasks_to_week(self, task_ids: List[str]) -> List[str]:
        """Promote multiple tasks to week status."""
        try:
            self.logger.info(f"Promoting {len(task_ids)} tasks to week status")
            
            updated_ids = []
            for task_id in task_ids:
                task = self.task_repo.get(task_id)
                if task:
                    self.task_repo.update_with_tags(task_id, {"status": "week"})
                    updated_ids.append(task_id)
            
            self.commit()
            self.logger.info(f"Successfully promoted {len(updated_ids)} tasks to week")
            return updated_ids
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to promote tasks to week: {str(e)}")
            raise