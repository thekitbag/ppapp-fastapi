from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func
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

    def _calculate_sort_order(self, user_id: str, status: str, insert_at: str) -> float:
        """Calculate sort_order for new task based on position preference."""
        if insert_at == "top":
            # Get minimum sort_order in the bucket
            result = self.db.execute(
                select(func.min(Task.sort_order)).where(
                    Task.user_id == user_id,
                    Task.status == status
                )
            ).scalar()
            if result is None:
                # No tasks in bucket, use current timestamp
                return float(int(time.time() * 1000))
            return result - 1

        elif insert_at == "bottom":
            # Get maximum sort_order in the bucket
            result = self.db.execute(
                select(func.max(Task.sort_order)).where(
                    Task.user_id == user_id,
                    Task.status == status
                )
            ).scalar()
            if result is None:
                # No tasks in bucket, use current timestamp
                return float(int(time.time() * 1000))
            return result + 1

        else:
            # Default fallback - use current timestamp
            return float(int(time.time() * 1000))
    
    def get_or_create_tag(self, name: str, user_id: str) -> Tag:
        """Get existing tag for user or create new one."""
        tag = self.db.execute(
            select(Tag).where(Tag.name == name, Tag.user_id == user_id)
        ).scalar_one_or_none()
        
        if tag:
            return tag
            
        tag = Tag(id=self._gen_id("tag"), name=name, user_id=user_id)
        self.db.add(tag)
        self.db.flush()
        return tag
    
    def create_with_tags(self, task_in: TaskCreate, user_id: str) -> Task:
        """Create task with tags for specific user."""
        task_data = task_in.model_dump(exclude={"tags", "insert_at"})

        # Calculate sort_order based on insert_at preference
        if "sort_order" not in task_data or task_data["sort_order"] is None:
            task_data["sort_order"] = self._calculate_sort_order(
                user_id,
                task_in.status,
                task_in.insert_at or "top"
            )

        task = Task(
            id=self._gen_id("task"),
            user_id=user_id,  # Set user_id for multi-tenancy
            **task_data
        )

        self.db.add(task)

        if task_in.tags:
            tags = [self.get_or_create_tag(tag_name, user_id) for tag_name in task_in.tags]
            task.tags = tags

        self.db.flush()
        self.db.refresh(task)
        return task
    
    def update_with_tags(self, task_id: str, user_id: str, update_data: dict) -> Task:
        """Update task including tags for specific user."""
        task = self.get_by_user(task_id, user_id)
        if not task:
            raise NotFoundError("Task", task_id)
        
        # Handle tags separately
        if "tags" in update_data:
            tag_names = update_data.pop("tags")
            if tag_names is not None:
                tags = [self.get_or_create_tag(name, user_id) for name in tag_names]
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
    
    def get_by_user(self, task_id: str, user_id: str) -> Optional[Task]:
        """Get a task by ID for specific user."""
        return self.db.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user_id)
        ).scalar_one_or_none()
    
    def get_by_status(self, user_id: str, status: List[str], skip: int = 0, limit: int = 100) -> List[Task]:
        """Get tasks filtered by status for specific user."""
        query = select(Task).where(Task.user_id == user_id)
        if status:  # Only filter if status list is not empty
            query = query.where(Task.status.in_(status))
        
        result = self.db.execute(
            query.order_by(Task.sort_order.asc(), Task.created_at.asc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
        
        return result
    
    def delete_by_user(self, task_id: str, user_id: str) -> bool:
        """Delete a task by ID for specific user."""
        task = self.get_by_user(task_id, user_id)
        if not task:
            return False

        self.db.delete(task)
        return True

    def reindex_sort_order(self, user_id: str, status: str) -> int:
        """Reindex sort_order values for tasks in a status bucket to small consecutive numbers."""
        # Get all tasks in the status bucket, ordered by current sort_order and created_at
        tasks = self.db.execute(
            select(Task).where(
                Task.user_id == user_id,
                Task.status == status
            ).order_by(Task.sort_order.asc(), Task.created_at.asc())
        ).scalars().all()

        if not tasks:
            return 0

        # Update sort_order to consecutive integers starting from 1
        for i, task in enumerate(tasks, start=1):
            task.sort_order = float(i)

        self.db.flush()
        return len(tasks)
    
    def to_schema_batch(self, tasks: List[Task]) -> List[TaskOut]:
        """Convert multiple Task models to TaskOut schemas efficiently (avoids N+1 queries)."""
        if not tasks:
            return []
        
        from app.models import TaskGoal, Goal  # Import here to avoid circular imports
        from app.schemas import GoalSummary
        
        # Get all task IDs
        task_ids = [task.id for task in tasks]
        
        # Batch fetch all task-goal links for this user only
        task_goal_links = self.db.query(TaskGoal).filter(
            TaskGoal.task_id.in_(task_ids),
            TaskGoal.user_id == tasks[0].user_id  # All tasks should belong to same user
        ).all()
        
        # Group links by task_id
        task_goals_map = {}
        goal_ids = set()
        for link in task_goal_links:
            if link.task_id not in task_goals_map:
                task_goals_map[link.task_id] = []
            task_goals_map[link.task_id].append(link.goal_id)
            goal_ids.add(link.goal_id)
        
        # Batch fetch all goals for this user only
        goals_dict = {}
        if goal_ids:
            goals = self.db.query(Goal).filter(
                Goal.id.in_(goal_ids),
                Goal.user_id == tasks[0].user_id
            ).all()
            goals_dict = {goal.id: goal for goal in goals}
        
        # Build TaskOut objects
        result = []
        for task in tasks:
            linked_goal_ids = task_goals_map.get(task.id, [])
            linked_goals = [goals_dict[goal_id] for goal_id in linked_goal_ids if goal_id in goals_dict]
            
            result.append(TaskOut(
                id=task.id,
                title=task.title,
                description=task.description,
                status=task.status.value,
                sort_order=task.sort_order,
                tags=sorted([tag.name for tag in task.tags], reverse=True),
                size=task.size.value if task.size else None,
                effort_minutes=task.effort_minutes,
                hard_due_at=task.hard_due_at,
                soft_due_at=task.soft_due_at,
                energy=task.energy.value if task.energy else None,
                project_id=task.project_id,
                goal_id=task.goal_id,  # Keep for backward compatibility
                goals=[GoalSummary(id=g.id, title=g.title) for g in linked_goals],
                created_at=task.created_at,
                updated_at=task.updated_at
            ))
        
        return result
    
    def to_schema(self, task: Task) -> TaskOut:
        """Convert Task model to TaskOut schema."""
        # Get linked goals for this task
        from app.models import TaskGoal, Goal  # Import here to avoid circular imports
        from app.schemas import GoalSummary
        
        task_goal_links = self.db.query(TaskGoal).filter(
            TaskGoal.task_id == task.id,
            TaskGoal.user_id == task.user_id
        ).all()
        goal_ids = [link.goal_id for link in task_goal_links]
        task_goals = []
        if goal_ids:
            task_goals = self.db.query(Goal).filter(
                Goal.id.in_(goal_ids),
                Goal.user_id == task.user_id
            ).all()
        
        return TaskOut(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            sort_order=task.sort_order,
            tags=sorted([tag.name for tag in task.tags], reverse=True),
            size=task.size.value if task.size else None,
            effort_minutes=task.effort_minutes,
            hard_due_at=task.hard_due_at,
            soft_due_at=task.soft_due_at,
            energy=task.energy.value if task.energy else None,
            project_id=task.project_id,
            goal_id=task.goal_id,  # Keep for backward compatibility
            goals=[GoalSummary(id=g.id, title=g.title) for g in task_goals],
            created_at=task.created_at,
            updated_at=task.updated_at
        )
