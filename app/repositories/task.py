from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid
import time
from datetime import datetime

from app.models import Task, Tag
from app.schemas import TaskCreate, TaskOut
from app.exceptions import NotFoundError
from .base import BaseRepository


class TaskRepository(BaseRepository[Task, TaskCreate, dict]):
    """Repository for Task operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, Task)
    
    def _gen_id(self, prefix: str = "task") -> str:
        """Generate unique ID with prefix."""
        return f"{prefix}_{uuid.uuid4()}"
    
    def get_or_create_tag(self, name: str) -> Tag:
        """Get existing tag or create new one."""
        tag = self.db.execute(
            select(Tag).where(Tag.name == name)
        ).scalar_one_or_none()
        
        if tag:
            return tag
            
        tag = Tag(id=self._gen_id("tag"), name=name)
        self.db.add(tag)
        self.db.flush()
        return tag
    
    def create_with_tags(self, task_in: TaskCreate) -> Task:
        """Create task with tags."""
        task_data = task_in.model_dump(exclude={"tags"})
        
        # Set sort_order if not provided - use current timestamp in milliseconds
        if "sort_order" not in task_data or task_data["sort_order"] is None:
            task_data["sort_order"] = time.time() * 1000  # epoch milliseconds
        
        task = Task(
            id=self._gen_id("task"),
            **task_data
        )
        
        self.db.add(task)
        
        if task_in.tags:
            tags = [self.get_or_create_tag(tag_name) for tag_name in task_in.tags]
            task.tags = tags
        
        self.db.flush()
        self.db.refresh(task)
        return task
    
    def update_with_tags(self, task_id: str, update_data: dict) -> Task:
        """Update task including tags."""
        task = self.get(task_id)
        if not task:
            raise NotFoundError("Task", task_id)
        
        # Handle tags separately
        if "tags" in update_data:
            tag_names = update_data.pop("tags")
            if tag_names is not None:
                tags = [self.get_or_create_tag(name) for name in tag_names]
                task.tags = tags
        
        # Update other fields with proper type conversion
        for field, value in update_data.items():
            if value is not None and hasattr(task, field):
                # Convert datetime strings to datetime objects
                if field in ['hard_due_at', 'soft_due_at', 'created_at', 'updated_at'] and isinstance(value, str):
                    try:
                        # Handle ISO format with timezone
                        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except ValueError:
                        # Skip invalid datetime strings
                        continue
                setattr(task, field, value)
        
        self.db.flush()
        self.db.refresh(task)
        return task
    
    def get_by_status(self, status: List[str], skip: int = 0, limit: int = 100) -> List[Task]:
        """Get tasks filtered by status."""
        query = select(Task)
        if status:
            query = query.where(Task.status.in_(status))
        
        return self.db.execute(
            query.order_by(Task.status, Task.sort_order.asc(), Task.created_at.asc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
    
    def to_schema(self, task: Task) -> TaskOut:
        """Convert Task model to TaskOut schema."""
        return TaskOut(
            id=task.id,
            title=task.title,
            status=task.status.value,
            sort_order=task.sort_order,
            tags=[tag.name for tag in task.tags],
            effort_minutes=task.effort_minutes,
            hard_due_at=task.hard_due_at,
            soft_due_at=task.soft_due_at,
            project_id=task.project_id,
            goal_id=task.goal_id,
            created_at=task.created_at,
            updated_at=task.updated_at
        )