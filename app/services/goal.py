from typing import List
from sqlalchemy.orm import Session

from app.repositories import GoalRepository
from app.schemas import GoalCreate, Goal as GoalSchema, GoalDetail, KROut, KRCreate, TaskGoalLink, TaskGoalLinkResponse
from app.exceptions import NotFoundError, ValidationError
from .base import BaseService


class GoalService(BaseService):
    """Service for goal business logic."""
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.goal_repo = GoalRepository(db)
    
    def create_goal(self, goal_in: GoalCreate) -> GoalSchema:
        """Create a new goal."""
        try:
            self.logger.info(f"Creating goal: {goal_in.title}")
            
            if not goal_in.title or not goal_in.title.strip():
                raise ValidationError("Goal title cannot be empty")
            
            goal = self.goal_repo.create_with_id(goal_in)
            self.commit()
            
            self.logger.info(f"Goal created successfully: {goal.id}")
            return self.goal_repo.to_schema(goal)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to create goal: {str(e)}")
            raise
    
    def get_goal(self, goal_id: str) -> GoalSchema:
        """Get a goal by ID."""
        self.logger.debug(f"Fetching goal: {goal_id}")
        
        goal = self.goal_repo.get(goal_id)
        if not goal:
            raise NotFoundError("Goal", goal_id)
        
        return self.goal_repo.to_schema(goal)
    
    def list_goals(self, skip: int = 0, limit: int = 100) -> List[GoalSchema]:
        """List goals."""
        self.logger.debug("Listing goals")
        
        if limit > 1000:
            raise ValidationError("Limit cannot exceed 1000")
        
        goals = self.goal_repo.get_multi(skip=skip, limit=limit)
        return [self.goal_repo.to_schema(goal) for goal in goals]
    
    def delete_goal(self, goal_id: str) -> bool:
        """Delete a goal."""
        try:
            self.logger.info(f"Deleting goal: {goal_id}")
            
            if not self.goal_repo.get(goal_id):
                raise NotFoundError("Goal", goal_id)
            
            deleted = self.goal_repo.delete(goal_id)
            self.commit()
            
            self.logger.info(f"Goal deleted successfully: {goal_id}")
            return deleted
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to delete goal {goal_id}: {str(e)}")
            raise
    
    def get_goal_detail(self, goal_id: str) -> GoalDetail:
        """Get a goal with its key results and linked tasks (with batched queries to avoid N+1)."""
        from app.models import Goal, GoalKR, TaskGoal, Task
        from app.schemas import GoalSummary, TaskOut
        
        self.logger.debug(f"Fetching goal detail: {goal_id}")
        
        # Get goal
        goal = self.goal_repo.get(goal_id)
        if not goal:
            raise NotFoundError("Goal", goal_id)
        
        # Batch fetch key results
        key_results = self.db.query(GoalKR).filter(GoalKR.goal_id == goal_id).all()
        
        # Batch fetch task links
        task_links = self.db.query(TaskGoal).filter(TaskGoal.goal_id == goal_id).all()
        task_ids = [link.task_id for link in task_links]
        
        # Batch fetch all tasks
        tasks = []
        if task_ids:
            tasks = self.db.query(Task).filter(Task.id.in_(task_ids)).all()
        
        # Batch fetch all task-goal links for these tasks (to populate goals field)
        all_task_goal_links = []
        goal_ids_to_fetch = set()
        if task_ids:
            all_task_goal_links = self.db.query(TaskGoal).filter(TaskGoal.task_id.in_(task_ids)).all()
            goal_ids_to_fetch = {link.goal_id for link in all_task_goal_links}
        
        # Batch fetch all goals for the tasks
        all_goals = {}
        if goal_ids_to_fetch:
            goals_list = self.db.query(Goal).filter(Goal.id.in_(goal_ids_to_fetch)).all()
            all_goals = {g.id: g for g in goals_list}
        
        # Group task-goal links by task_id
        task_goals_map = {}
        for link in all_task_goal_links:
            if link.task_id not in task_goals_map:
                task_goals_map[link.task_id] = []
            task_goals_map[link.task_id].append(link.goal_id)
        
        # Build TaskOut objects with goals populated
        task_out_list = []
        for task in tasks:
            # Get goals for this task
            task_goal_ids = task_goals_map.get(task.id, [])
            task_goals = [all_goals[gid] for gid in task_goal_ids if gid in all_goals]
            
            task_out = TaskOut(
                id=task.id,
                title=task.title,
                status=task.status.value,
                sort_order=task.sort_order,
                tags=[tag.name for tag in task.tags],
                effort_minutes=task.effort_minutes,
                hard_due_at=task.hard_due_at,
                soft_due_at=task.soft_due_at,
                project_id=task.project_id,
                goal_id=task.goal_id,  # Keep for backward compatibility - DEPRECATED
                goals=[GoalSummary(id=g.id, title=g.title) for g in task_goals],
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            task_out_list.append(task_out)
        
        return GoalDetail(
            id=goal.id,
            title=goal.title,
            description=goal.description,
            type=(goal.type.value if getattr(goal, 'type', None) is not None else None),
            created_at=goal.created_at,
            key_results=[KROut(
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
    
    def create_key_result(self, goal_id: str, kr_data: KRCreate) -> KROut:
        """Create a key result for a goal."""
        from app.models import GoalKR
        import uuid
        
        try:
            self.logger.info(f"Creating key result for goal: {goal_id}")
            
            # Verify goal exists
            if not self.goal_repo.get(goal_id):
                raise NotFoundError("Goal", goal_id)
            
            db_kr = GoalKR(
                id=str(uuid.uuid4()),
                goal_id=goal_id,
                name=kr_data.name,
                target_value=kr_data.target_value,
                unit=kr_data.unit,
                baseline_value=kr_data.baseline_value,
            )
            self.db.add(db_kr)
            self.commit()
            self.db.refresh(db_kr)
            
            self.logger.info(f"Key result created successfully: {db_kr.id}")
            
            return KROut(
                id=db_kr.id,
                goal_id=db_kr.goal_id,
                name=db_kr.name,
                target_value=db_kr.target_value,
                unit=db_kr.unit,
                baseline_value=db_kr.baseline_value,
                created_at=db_kr.created_at,
            )
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to create key result for goal {goal_id}: {str(e)}")
            raise
    
    def delete_key_result(self, goal_id: str, kr_id: str) -> bool:
        """Delete a key result."""
        from app.models import GoalKR
        
        try:
            self.logger.info(f"Deleting key result: {kr_id}")
            
            # Verify goal exists
            if not self.goal_repo.get(goal_id):
                raise NotFoundError("Goal", goal_id)
            
            db_kr = self.db.query(GoalKR).filter(
                GoalKR.id == kr_id, 
                GoalKR.goal_id == goal_id
            ).first()
            
            if not db_kr:
                raise NotFoundError("Key result", kr_id)
            
            self.db.delete(db_kr)
            self.commit()
            
            self.logger.info(f"Key result deleted successfully: {kr_id}")
            return True
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to delete key result {kr_id}: {str(e)}")
            raise
    
    def link_tasks_to_goal(self, goal_id: str, link_data: TaskGoalLink) -> TaskGoalLinkResponse:
        """Link tasks to a goal."""
        from app.models import Task, TaskGoal
        import uuid
        
        try:
            self.logger.info(f"Linking {len(link_data.task_ids)} tasks to goal: {goal_id}")
            
            # Verify goal exists
            if not self.goal_repo.get(goal_id):
                raise NotFoundError("Goal", goal_id)
            
            # Verify tasks exist
            tasks = self.db.query(Task).filter(Task.id.in_(link_data.task_ids)).all()
            task_ids_found = {task.id for task in tasks}
            task_ids_requested = set(link_data.task_ids)
            
            missing_tasks = task_ids_requested - task_ids_found
            if missing_tasks:
                raise ValidationError(f"Tasks not found: {list(missing_tasks)}")
            
            # Check which tasks are already linked
            existing_links = self.db.query(TaskGoal).filter(
                TaskGoal.goal_id == goal_id,
                TaskGoal.task_id.in_(link_data.task_ids)
            ).all()
            already_linked = {link.task_id for link in existing_links}
            
            # Create new links for tasks not already linked
            to_link = task_ids_requested - already_linked
            linked = []
            
            for task_id in to_link:
                db_link = TaskGoal(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    goal_id=goal_id,
                )
                self.db.add(db_link)
                linked.append(task_id)
            
            self.commit()
            
            self.logger.info(f"Successfully linked {len(linked)} tasks to goal {goal_id}")
            
            return TaskGoalLinkResponse(
                linked=linked,
                already_linked=list(already_linked)
            )
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to link tasks to goal {goal_id}: {str(e)}")
            raise
    
    def unlink_tasks_from_goal(self, goal_id: str, link_data: TaskGoalLink) -> TaskGoalLinkResponse:
        """Unlink tasks from a goal."""
        from app.models import TaskGoal
        
        try:
            self.logger.info(f"Unlinking {len(link_data.task_ids)} tasks from goal: {goal_id}")
            
            # Verify goal exists
            if not self.goal_repo.get(goal_id):
                raise NotFoundError("Goal", goal_id)
            
            # Find existing links to remove
            existing_links = self.db.query(TaskGoal).filter(
                TaskGoal.goal_id == goal_id,
                TaskGoal.task_id.in_(link_data.task_ids)
            ).all()
            
            unlinked = []
            for link in existing_links:
                unlinked.append(link.task_id)
                self.db.delete(link)
            
            not_linked = set(link_data.task_ids) - set(unlinked)
            
            self.commit()
            
            self.logger.info(f"Successfully unlinked {len(unlinked)} tasks from goal {goal_id}")
            
            return TaskGoalLinkResponse(
                linked=unlinked,  # Actually unlinked
                already_linked=list(not_linked)  # Were not linked to begin with
            )
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to unlink tasks from goal {goal_id}: {str(e)}")
            raise
