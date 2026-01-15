from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timedelta, date

from app.repositories import TaskRepository, GoalRepository, ProjectRepository
from app.schemas import TaskCreate, TaskOut
from app.exceptions import NotFoundError, ValidationError
from .base import BaseService


class TaskService(BaseService):
    """Service for multi-tenant task business logic."""
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.task_repo = TaskRepository(db)
        self.goal_repo = GoalRepository(db)
        self.project_repo = ProjectRepository(db)
    
    def create_task(self, task_in: TaskCreate, user_id: str) -> Tuple[TaskOut, bool]:
        """Create a new task for specific user.

        Returns:
            tuple[TaskOut, bool]: (task, was_created) where was_created is True for new tasks, False for idempotent returns
        """
        try:
            self.logger.info(f"Creating task for user {user_id}: {task_in.title}")

            if not task_in.title or not task_in.title.strip():
                raise ValidationError("Task title cannot be empty")

            # Default status to "week" if not provided
            if task_in.status is None:
                task_in.status = "week"

            # Check for idempotent case before calling repository
            was_created = True
            if task_in.client_request_id:
                from app.models import Task
                existing_task = self.db.execute(
                    select(Task).where(
                        Task.user_id == user_id,
                        Task.client_request_id == task_in.client_request_id
                    )
                ).scalar_one_or_none()
                if existing_task:
                    was_created = False
                    self.logger.info(f"Idempotent task request: returning existing task {existing_task.id}")
                    return self.task_repo.to_schema(existing_task), was_created

            # Handle goal linking at creation time
            goal_ids_to_link = []
            original_goal_id = task_in.goal_id  # Save for backward compatibility

            # Collect goal IDs from both new 'goals' array and legacy 'goal_id' field
            if task_in.goals:
                goal_ids_to_link.extend(task_in.goals)
            if task_in.goal_id:
                goal_ids_to_link.append(task_in.goal_id)

            # Remove duplicates while preserving order
            goal_ids_to_link = list(dict.fromkeys(goal_ids_to_link))

            # If we're going to create goal links, don't save legacy goal_id to avoid duplication
            if goal_ids_to_link:
                # Clear goal_id to prevent it being saved to database
                task_in.goal_id = None

            task = self.task_repo.create_with_tags(task_in, user_id)

            if goal_ids_to_link:
                self._link_task_to_goals(task.id, user_id, goal_ids_to_link)
                # For backward compatibility, temporarily store original goal_id on task instance
                # This will be used by to_schema method and not persisted to database
                task._original_goal_id = original_goal_id

            self.commit()

            self.logger.info(f"Task created successfully: {task.id}")
            return self.task_repo.to_schema(task), was_created

        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to create task: {str(e)}")
            raise

    def _link_task_to_goals(self, task_id: str, user_id: str, goal_ids: List[str]):
        """Link a task to multiple goals with validation. Only weekly goals allowed."""
        from app.models import Goal, TaskGoal
        import uuid

        try:
            self.logger.info(f"Linking task {task_id} to {len(goal_ids)} goals")

            # Verify all goals exist and belong to user
            goals = self.db.query(Goal).filter(Goal.id.in_(goal_ids), Goal.user_id == user_id).all()
            goals_found = {goal.id: goal for goal in goals}
            goals_requested = set(goal_ids)

            missing_goals = goals_requested - set(goals_found.keys())
            if missing_goals:
                raise ValidationError(f"Goals not found: {list(missing_goals)}")

            # Validate that all goals are weekly type
            for goal_id in goal_ids:
                goal = goals_found[goal_id]
                if goal.type and goal.type.value != "weekly":
                    raise ValidationError(f"Only weekly goals can have tasks linked to them. Goal {goal_id} is {goal.type.value}")

            # Check which links already exist
            existing_links = self.db.query(TaskGoal).filter(
                TaskGoal.task_id == task_id,
                TaskGoal.goal_id.in_(goal_ids),
                TaskGoal.user_id == user_id
            ).all()

            existing_goal_ids = {link.goal_id for link in existing_links}

            # Create new links for goals that aren't already linked
            for goal_id in goal_ids:
                if goal_id not in existing_goal_ids:
                    link = TaskGoal(
                        id=f"taskgoal_{uuid.uuid4()}",
                        task_id=task_id,
                        goal_id=goal_id,
                        user_id=user_id
                    )
                    self.db.add(link)
                    self.logger.debug(f"Created link: task {task_id} -> goal {goal_id}")

            # Note: commit is handled by the calling method

        except Exception as e:
            self.logger.error(f"Failed to link task {task_id} to goals: {str(e)}")
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
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
        due_date_start: Optional[date] = None,
        due_date_end: Optional[date] = None,
    ) -> List[TaskOut]:
        """List tasks for specific user with optional filtering.

        Defaults to exclude archived and done unless explicitly requested.
        """
        # Normalize default statuses
        if status is None:
            status = ["backlog", "week", "today", "doing", "waiting"]

        # Validate limit
        if limit is not None and limit > 1000:
            raise ValidationError("Limit cannot exceed 1000")

        # Convert date range to datetime boundaries (local naive)
        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None
        if due_date_start:
            start_dt = datetime(due_date_start.year, due_date_start.month, due_date_start.day, 0, 0, 0, 0)
        if due_date_end:
            # inclusive end of day: 23:59:59.999999
            end_dt = datetime(due_date_end.year, due_date_end.month, due_date_end.day, 23, 59, 59, 999999)

        # Log filters (without PII beyond IDs)
        self.logger.debug(
            "Listing tasks | user=%s statuses=%s project=%s goal=%s tags_count=%s has_search=%s date_range=%s..%s skip=%s limit=%s",
            user_id,
            status,
            project_id,
            goal_id,
            len(tags) if tags else 0,
            bool(search),
            start_dt.isoformat() if start_dt else None,
            end_dt.isoformat() if end_dt else None,
            skip,
            limit,
        )

        tasks = self.task_repo.get_filtered(
            user_id=user_id,
            statuses=status,
            project_id=project_id,
            goal_id=goal_id,
            tags=tags,
            search=search,
            due_start=start_dt,
            due_end=end_dt,
            skip=skip,
            limit=limit,
        )

        result = self.task_repo.to_schema_batch(tasks)

        self.logger.debug("List tasks result_count=%d", len(result))
        return result
    
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
        # Validate task ownership
        if task_id:
            task = self.task_repo.get_by_user(task_id, user_id)
            if not task:
                raise NotFoundError("Task", task_id)
        
        # Validate goal ownership
        if goal_id:
            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)
        
        # Validate project ownership
        if project_id:
            project = self.project_repo.get_by_user(project_id, user_id)
            if not project:
                raise NotFoundError("Project", project_id)
        
        return True
    
    def reindex_tasks(self, user_id: str, status: str) -> int:
        """Reindex sort_order values for tasks in a status bucket."""
        try:
            self.logger.info(f"Reindexing tasks for user {user_id} in status {status}")

            count = self.task_repo.reindex_sort_order(user_id, status)
            self.commit()

            self.logger.info(f"Reindexed {count} tasks in status {status}")
            return count

        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to reindex tasks: {str(e)}")
            raise

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
