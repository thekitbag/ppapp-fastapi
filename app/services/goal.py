from typing import List
from sqlalchemy.orm import Session

from app.repositories import GoalRepository
from app.schemas import GoalCreate, Goal as GoalSchema, GoalDetail, KROut, KRCreate, TaskGoalLink, TaskGoalLinkResponse, GoalNode, GoalOut
from app.exceptions import NotFoundError, ValidationError
from .base import BaseService


class GoalService(BaseService):
    """Service for goal business logic."""
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.goal_repo = GoalRepository(db)
    
    def create_goal(self, goal_in: GoalCreate, user_id: str) -> GoalSchema:
        """Create a new goal with hierarchy validation."""
        try:
            self.logger.info(f"Creating goal: {goal_in.title}")
            
            if not goal_in.title or not goal_in.title.strip():
                raise ValidationError("Goal title cannot be empty")
            
            # Goals v2: Validate hierarchy rules
            self._validate_goal_hierarchy(goal_in.type, goal_in.parent_goal_id, user_id)
            
            goal = self.goal_repo.create_with_id(goal_in, user_id)
            self.commit()
            
            self.logger.info(f"Goal created successfully: {goal.id}")
            return self.goal_repo.to_schema(goal)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to create goal: {str(e)}")
            raise
    
    def get_goal(self, goal_id: str, user_id: str) -> GoalSchema:
        """Get a goal by ID."""
        self.logger.debug(f"Fetching goal: {goal_id}")
        
        goal = self.goal_repo.get_by_user(goal_id, user_id)
        if not goal:
            raise NotFoundError("Goal", goal_id)
        
        return self.goal_repo.to_schema(goal)
    
    def list_goals(self, user_id: str, skip: int = 0, limit: int = 100, is_closed: bool = None, include_archived: bool = False) -> List[GoalSchema]:
        """List goals with optional is_closed filter and archive exclusion."""
        self.logger.debug(f"Listing goals (is_closed={is_closed}, include_archived={include_archived})")

        if limit > 1000:
            raise ValidationError("Limit cannot exceed 1000")
        goals = self.goal_repo.list_goals(
            user_id,
            skip=skip,
            limit=limit,
            is_closed=is_closed,
            include_archived=include_archived,
        )

        return [self.goal_repo.to_schema(goal) for goal in goals]
    
    def update_goal(self, goal_id: str, user_id: str, goal_update: dict) -> GoalSchema:
        """Update a goal with hierarchy validation."""
        try:
            self.logger.info(f"Updating goal: {goal_id}")
            
            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)
            
            # Goals v2: Validate hierarchy rules if type or parent is being changed
            new_type = goal_update.get("type", goal.type.value if goal.type else None)
            new_parent_id = goal_update.get("parent_goal_id", goal.parent_goal_id)
            
            if "type" in goal_update or "parent_goal_id" in goal_update:
                self._validate_goal_hierarchy(new_type, new_parent_id, user_id)
                
            # Check for cycles if parent is being changed
            if "parent_goal_id" in goal_update and new_parent_id:
                if self._would_create_cycle(goal_id, new_parent_id):
                    raise ValidationError("Cannot set parent: would create a cycle in the goal hierarchy")
            
            # Update goal attributes
            for field, value in goal_update.items():
                if hasattr(goal, field):
                    setattr(goal, field, value)
            
            self.commit()
            self.db.refresh(goal)
            
            self.logger.info(f"Goal updated successfully: {goal_id}")
            return self.goal_repo.to_schema(goal)
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to update goal {goal_id}: {str(e)}")
            raise
    
    def delete_goal(self, goal_id: str, user_id: str) -> bool:
        """Delete a goal."""
        try:
            self.logger.info(f"Deleting goal: {goal_id}")
            
            if not self.goal_repo.get_by_user(goal_id, user_id):
                raise NotFoundError("Goal", goal_id)
            
            deleted = self.goal_repo.delete_by_user(goal_id, user_id)
            self.commit()
            
            self.logger.info(f"Goal deleted successfully: {goal_id}")
            return deleted
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to delete goal {goal_id}: {str(e)}")
            raise
    
    def get_goal_detail(self, goal_id: str, user_id: str) -> GoalDetail:
        """Get a goal with its key results and linked tasks (with batched queries to avoid N+1)."""
        from app.models import Goal, GoalKR, TaskGoal, Task
        from app.schemas import GoalSummary, TaskOut
        
        self.logger.debug(f"Fetching goal detail: {goal_id}")
        
        # Get goal
        goal = self.goal_repo.get_by_user(goal_id, user_id)
        if not goal:
            raise NotFoundError("Goal", goal_id)
        
        # Batch fetch key results
        key_results = (
            self.db.query(GoalKR)
            .filter(GoalKR.goal_id == goal_id, GoalKR.user_id == user_id)
            .all()
        )
        
        # Batch fetch task links
        task_links = (
            self.db.query(TaskGoal)
            .filter(TaskGoal.goal_id == goal_id, TaskGoal.user_id == user_id)
            .all()
        )
        task_ids = [link.task_id for link in task_links]
        
        # Batch fetch all tasks
        tasks = []
        if task_ids:
            tasks = self.db.query(Task).filter(Task.id.in_(task_ids), Task.user_id == user_id).all()
        
        # Batch fetch all task-goal links for these tasks (to populate goals field)
        all_task_goal_links = []
        goal_ids_to_fetch = set()
        if task_ids:
            all_task_goal_links = (
                self.db.query(TaskGoal)
                .filter(TaskGoal.task_id.in_(task_ids), TaskGoal.user_id == user_id)
                .all()
            )
            goal_ids_to_fetch = {link.goal_id for link in all_task_goal_links}
        
        # Batch fetch all goals for the tasks
        all_goals = {}
        if goal_ids_to_fetch:
            goals_list = (
                self.db.query(Goal)
                .filter(Goal.id.in_(goal_ids_to_fetch), Goal.user_id == user_id)
                .all()
            )
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
        
        goal_type = getattr(goal, 'type', None)
        if goal_type is not None and hasattr(goal_type, 'value'):
            goal_type = goal_type.value
        return GoalDetail(
            id=goal.id,
            title=goal.title,
            description=goal.description,
            type=goal_type,
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
    
    def create_key_result(self, goal_id: str, user_id: str, kr_data: KRCreate) -> KROut:
        """Create a key result for a goal."""
        from app.models import GoalKR
        import uuid
        
        try:
            self.logger.info(f"Creating key result for goal: {goal_id}")
            
            # Verify goal exists
            if not self.goal_repo.get_by_user(goal_id, user_id):
                raise NotFoundError("Goal", goal_id)
            
            db_kr = GoalKR(
                id=str(uuid.uuid4()),
                goal_id=goal_id,
                name=kr_data.name,
                target_value=kr_data.target_value,
                unit=kr_data.unit,
                baseline_value=kr_data.baseline_value,
                user_id=user_id,
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
    
    def delete_key_result(self, goal_id: str, user_id: str, kr_id: str) -> bool:
        """Delete a key result."""
        from app.models import GoalKR
        
        try:
            self.logger.info(f"Deleting key result: {kr_id}")
            
            # Verify goal exists
            if not self.goal_repo.get_by_user(goal_id, user_id):
                raise NotFoundError("Goal", goal_id)
            
            db_kr = self.db.query(GoalKR).filter(
                GoalKR.id == kr_id, 
                GoalKR.goal_id == goal_id,
                GoalKR.user_id == user_id
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
    
    def link_tasks_to_goal(self, goal_id: str, user_id: str, link_data: TaskGoalLink) -> TaskGoalLinkResponse:
        """Link tasks to a goal. Only weekly goals can have linked tasks."""
        from app.models import Task, TaskGoal
        import uuid
        
        try:
            self.logger.info(f"Linking {len(link_data.task_ids)} tasks to goal: {goal_id}")
            
            # Verify goal exists and is weekly
            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)
            
            # Goals v2: Only weekly goals can have tasks
            if goal.type and goal.type.value != "weekly":
                raise ValidationError("Only weekly goals can have tasks linked to them. Annual and quarterly goals should link to their child goals instead.")
            
            # Verify tasks exist and belong to user
            tasks = self.db.query(Task).filter(Task.id.in_(link_data.task_ids), Task.user_id == user_id).all()
            task_ids_found = {task.id for task in tasks}
            task_ids_requested = set(link_data.task_ids)
            
            missing_tasks = task_ids_requested - task_ids_found
            if missing_tasks:
                raise ValidationError(f"Tasks not found: {list(missing_tasks)}")
            
            # Check which tasks are already linked
            existing_links = self.db.query(TaskGoal).filter(
                TaskGoal.goal_id == goal_id,
                TaskGoal.task_id.in_(link_data.task_ids),
                TaskGoal.user_id == user_id
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
                    user_id=user_id,
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
    
    def unlink_tasks_from_goal(self, goal_id: str, user_id: str, link_data: TaskGoalLink) -> TaskGoalLinkResponse:
        """Unlink tasks from a goal."""
        from app.models import TaskGoal
        
        try:
            self.logger.info(f"Unlinking {len(link_data.task_ids)} tasks from goal: {goal_id}")
            
            # Verify goal exists
            if not self.goal_repo.get_by_user(goal_id, user_id):
                raise NotFoundError("Goal", goal_id)
            
            # Find existing links to remove
            existing_links = self.db.query(TaskGoal).filter(
                TaskGoal.goal_id == goal_id,
                TaskGoal.task_id.in_(link_data.task_ids),
                TaskGoal.user_id == user_id
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
    
    # Goals v2: Hierarchy and validation methods
    
    def _validate_goal_hierarchy(self, goal_type: str, parent_goal_id: str = None, user_id: str = None):
        """Validate goal hierarchy rules."""
        if not goal_type:
            return  # No validation needed for null type
            
        if goal_type == "annual":
            if parent_goal_id:
                raise ValidationError("Annual goals cannot have a parent goal")
        elif goal_type == "quarterly":
            if not parent_goal_id:
                raise ValidationError("Quarterly goals must have an annual parent goal")
            parent = self.goal_repo.get_by_user(parent_goal_id, user_id) if user_id else self.goal_repo.get(parent_goal_id)
            if not parent:
                raise ValidationError(f"Parent goal not found: {parent_goal_id}")
            if parent.type.value != "annual":
                raise ValidationError("Quarterly goals must have an annual parent (not quarterly or weekly)")
        elif goal_type == "weekly":
            if not parent_goal_id:
                raise ValidationError("Weekly goals must have a quarterly parent goal")
            parent = self.goal_repo.get_by_user(parent_goal_id, user_id) if user_id else self.goal_repo.get(parent_goal_id)
            if not parent:
                raise ValidationError(f"Parent goal not found: {parent_goal_id}")
            if parent.type.value != "quarterly":
                raise ValidationError("Weekly goals must have a quarterly parent (not annual or weekly)")
    
    def _would_create_cycle(self, goal_id: str, parent_goal_id: str) -> bool:
        """Check if setting parent would create a cycle in the hierarchy."""
        if not parent_goal_id or goal_id == parent_goal_id:
            return goal_id == parent_goal_id
            
        # Walk up the parent chain to see if we reach goal_id
        current_parent_id = parent_goal_id
        visited = set()
        
        while current_parent_id and current_parent_id not in visited:
            if current_parent_id == goal_id:
                return True
            visited.add(current_parent_id)
            
            parent_goal = self.goal_repo.get(current_parent_id)
            if not parent_goal:
                break
            current_parent_id = parent_goal.parent_goal_id
            
        return False
    
    def get_goals_tree(self, user_id: str, include_tasks: bool = False, include_closed: bool = False, include_archived: bool = False) -> List[GoalNode]:
        """Get hierarchical tree of goals (Annual → Quarterly → Weekly)."""
        try:
            self.logger.debug(f"Building goals tree (include_closed={include_closed}, include_archived={include_archived})")
            from app.models import Goal

            # Get goals for this user with optional closed and archived filters
            query = self.db.query(Goal).filter(Goal.user_id == user_id)
            if not include_closed:
                query = query.filter(Goal.is_closed == False)
            if not include_archived:
                query = query.filter(Goal.is_archived == False)

            all_goals = query.all()
            
            # Build lookup maps
            goals_by_id = {goal.id: goal for goal in all_goals}
            children_by_parent = {}
            
            for goal in all_goals:
                parent_id = goal.parent_goal_id
                if parent_id not in children_by_parent:
                    children_by_parent[parent_id] = []
                children_by_parent[parent_id].append(goal)
            
            # Get root goals (annual goals with no parent)
            root_goals = children_by_parent.get(None, [])
            
            def build_tree_node(goal) -> GoalNode:
                # Get children for this goal
                children_goals = children_by_parent.get(goal.id, [])

                # Compute path showing ancestry
                path_parts = []
                current_goal = goal
                while current_goal.parent_goal_id:
                    parent_goal = goals_by_id.get(current_goal.parent_goal_id)
                    if parent_goal:
                        path_parts.insert(0, parent_goal.title)
                        current_goal = parent_goal
                    else:
                        break

                path = " › ".join(path_parts) if path_parts else None

                # Convert to GoalNode
                node_data = {
                    "id": goal.id,
                    "title": goal.title,
                    "description": goal.description,
                    "type": goal.type.value if goal.type else None,
                    "parent_goal_id": goal.parent_goal_id,
                    "end_date": goal.end_date,
                    "status": goal.status.value if goal.status else "on_target",
                    "is_closed": goal.is_closed,
                    "closed_at": goal.closed_at,
                    "created_at": goal.created_at,
                    "path": path,
                    "children": [build_tree_node(child) for child in sorted(children_goals, key=lambda g: (-g.priority, g.end_date or g.created_at, g.created_at))]
                }
                
                # Add tasks for weekly goals if requested
                if include_tasks and goal.type and goal.type.value == "weekly":
                    # Get linked tasks for this weekly goal
                    task_links = [link.task for link in goal.task_links]
                    from app.repositories.task import TaskRepository
                    task_repo = TaskRepository(self.db)
                    node_data["tasks"] = [task_repo.to_schema(task) for task in task_links]
                
                return GoalNode(**node_data)
            
            # Build tree starting from root goals (annuals), sorted by priority (desc), then end_date, then created_at
            root_goals_sorted = sorted(root_goals, key=lambda g: (-g.priority, g.end_date or g.created_at, g.created_at))
            tree = [build_tree_node(goal) for goal in root_goals_sorted]
            
            self.logger.debug(f"Built goals tree with {len(tree)} root nodes")
            return tree
            
        except Exception as e:
            self.logger.error(f"Failed to build goals tree: {str(e)}")
            raise
    
    def get_goals_by_type(self, user_id: str, goal_type: str, parent_id: str = None, include_archived: bool = False) -> List[GoalOut]:
        """Get goals filtered by type and optionally by parent, excluding archived goals by default."""
        try:
            self.logger.debug(f"Getting goals by type: {goal_type}, parent: {parent_id}, include_archived: {include_archived}")
            try:
                goals = self.goal_repo.list_goals_by_type(
                    user_id,
                    goal_type,
                    parent_id=parent_id,
                    include_archived=include_archived,
                )
            except ValueError:
                raise ValidationError("Invalid goal type")

            return [self.goal_repo.to_schema(goal) for goal in goals]
            
        except Exception as e:
            self.logger.error(f"Failed to get goals by type {goal_type}: {str(e)}")
            raise

    def close_goal(self, goal_id: str, user_id: str) -> GoalSchema:
        """Close a goal and its descendants by setting is_closed=True and closed_at=now."""
        try:
            self.logger.info(f"Closing goal: {goal_id}")

            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)

            # Recursive closure function
            def close_recursive(current_goal):
                # Idempotent check at individual level
                if not current_goal.is_closed:
                    current_goal.is_closed = True
                    current_goal.closed_at = now
                    self.db.add(current_goal)
                
                # Recurse for children
                # Accessing .children triggers lazy load if not eager loaded
                for child in current_goal.children:
                    close_recursive(child)

            # Apply recursion
            close_recursive(goal)

            self.commit()
            self.db.refresh(goal)

            self.logger.info(f"Goal and descendants closed successfully: {goal_id}")
            return self.goal_repo.to_schema(goal)

        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to close goal {goal_id}: {str(e)}")
            raise

    def reopen_goal(self, goal_id: str, user_id: str) -> GoalSchema:
        """Reopen a goal by setting is_closed=False and closed_at=NULL."""
        try:
            self.logger.info(f"Reopening goal: {goal_id}")

            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)

            # Idempotent: if already open, return current state
            if not goal.is_closed:
                self.logger.info(f"Goal {goal_id} already open")
                return self.goal_repo.to_schema(goal)

            # Reopen the goal
            goal.is_closed = False
            goal.closed_at = None

            self.commit()
            self.db.refresh(goal)

            self.logger.info(f"Goal reopened successfully: {goal_id}")
            return self.goal_repo.to_schema(goal)

        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to reopen goal {goal_id}: {str(e)}")
            raise

    def archive_goal(self, goal_id: str, user_id: str) -> GoalSchema:
        """Archive a goal by setting is_archived=True."""
        try:
            self.logger.info(f"Archiving goal: {goal_id}")

            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)

            # Idempotent: if already archived, return current state
            if goal.is_archived:
                self.logger.info(f"Goal {goal_id} already archived")
                return self.goal_repo.to_schema(goal)

            # Archive the goal
            goal.is_archived = True

            self.commit()
            self.db.refresh(goal)

            self.logger.info(f"Goal archived successfully: {goal_id}")
            return self.goal_repo.to_schema(goal)

        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to archive goal {goal_id}: {str(e)}")
            raise

    def unarchive_goal(self, goal_id: str, user_id: str) -> GoalSchema:
        """Unarchive a goal by setting is_archived=False."""
        try:
            self.logger.info(f"Unarchiving goal: {goal_id}")

            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)

            # Idempotent: if already unarchived, return current state
            if not goal.is_archived:
                self.logger.info(f"Goal {goal_id} already unarchived")
                return self.goal_repo.to_schema(goal)

            # Unarchive the goal
            goal.is_archived = False

            self.commit()
            self.db.refresh(goal)

            self.logger.info(f"Goal unarchived successfully: {goal_id}")
            return self.goal_repo.to_schema(goal)

        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to unarchive goal {goal_id}: {str(e)}")
            raise

    def update_goal_priority(self, goal_id: str, user_id: str, new_priority: float) -> GoalSchema:
        """Update a goal's priority value. Higher values = higher priority (displayed first)."""
        try:
            self.logger.info(f"Updating priority for goal {goal_id} to {new_priority}")

            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)

            # Update priority
            goal.priority = new_priority

            self.commit()
            self.db.refresh(goal)

            self.logger.info(f"Goal priority updated successfully: {goal_id}")
            return self.goal_repo.to_schema(goal)

        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to update priority for goal {goal_id}: {str(e)}")
            raise

    def reorder_goal(self, goal_id: str, user_id: str, direction: str) -> GoalSchema:
        """
        Smart reordering with self-healing.
        Swaps a goal with its adjacent sibling (same parent_id and type).
        Automatically fixes duplicate priorities by re-indexing siblings.

        Args:
            goal_id: The goal to reorder
            user_id: The user ID
            direction: "up" or "down"
        """
        try:
            self.logger.info(f"Reordering goal {goal_id} {direction}")

            from app.models import Goal

            # Validate direction
            if direction not in ["up", "down"]:
                raise ValidationError("Direction must be 'up' or 'down'")

            # Get the target goal
            goal = self.goal_repo.get_by_user(goal_id, user_id)
            if not goal:
                raise NotFoundError("Goal", goal_id)

            siblings = self.goal_repo.list_siblings_for_reorder(user_id, goal)

            # Find current index
            try:
                current_index = next(i for i, g in enumerate(siblings) if g.id == goal_id)
            except StopIteration:
                raise ValidationError(f"Goal {goal_id} not found in sibling list")

            # Determine neighbor index
            if direction == "up":
                neighbor_index = current_index - 1
            else:  # down
                neighbor_index = current_index + 1

            # Guard: out of bounds check
            if neighbor_index < 0 or neighbor_index >= len(siblings):
                self.logger.info(f"Goal {goal_id} already at {direction}most position")
                return self.goal_repo.to_schema(goal)

            # Check for priority collisions in the sibling list
            priorities = [g.priority for g in siblings]
            has_collisions = len(priorities) != len(set(priorities))

            if has_collisions:
                # Self-healing: Re-index entire sibling list with spacing of 10
                self.logger.info(f"Detected priority collisions, re-indexing {len(siblings)} siblings")

                # Calculate base priority (start high, go down by 10 each)
                base_priority = len(siblings) * 10
                for i, sibling in enumerate(siblings):
                    sibling.priority = base_priority - (i * 10)
                    self.db.add(sibling)

                # Re-fetch after normalization to get clean state
                self.commit()
                self.db.refresh(goal)

                # Re-sort after normalization
                siblings.sort(key=lambda g: (-g.priority, g.created_at))
                current_index = next(i for i, g in enumerate(siblings) if g.id == goal_id)

                if direction == "up":
                    neighbor_index = current_index - 1
                else:
                    neighbor_index = current_index + 1

                if neighbor_index < 0 or neighbor_index >= len(siblings):
                    return self.goal_repo.to_schema(goal)

            # Swap priorities
            target_goal = siblings[current_index]
            neighbor_goal = siblings[neighbor_index]

            target_priority = target_goal.priority
            neighbor_priority = neighbor_goal.priority

            target_goal.priority = neighbor_priority
            neighbor_goal.priority = target_priority

            self.db.add(target_goal)
            self.db.add(neighbor_goal)

            self.commit()
            self.db.refresh(goal)

            self.logger.info(f"Goal reordered successfully: {goal_id}")
            return self.goal_repo.to_schema(goal)

        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to reorder goal {goal_id}: {str(e)}")
            raise
