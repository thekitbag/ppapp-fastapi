from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid

from app.models import Goal
from app.schemas import GoalCreate, Goal as GoalSchema
from app.exceptions import NotFoundError
from .base import BaseRepository


class GoalRepository(BaseRepository[Goal, GoalCreate, dict]):
    """Repository for Goal operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, Goal)
    
    def _gen_id(self, prefix: str = "goal") -> str:
        """Generate unique ID with prefix."""
        return f"{prefix}_{uuid.uuid4()}"
    
    def create_with_id(self, goal_in: GoalCreate, user_id: str) -> Goal:
        """Create goal with generated ID for specific user."""
        goal_data = goal_in.model_dump()
        goal = Goal(
            id=self._gen_id("goal"),
            user_id=user_id,
            **goal_data
        )
        
        self.db.add(goal)
        self.db.flush()
        self.db.refresh(goal)
        return goal
    
    def get_by_user(self, goal_id: str, user_id: str) -> Optional[Goal]:
        """Get a goal by ID for specific user."""
        return self.db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        ).scalar_one_or_none()
    
    def get_multi_by_user(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Goal]:
        """Get goals for specific user."""
        result = self.db.execute(
            select(Goal).where(Goal.user_id == user_id)
            .order_by(Goal.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
        
        return list(result)
    
    def delete_by_user(self, goal_id: str, user_id: str) -> bool:
        """Delete a goal by ID for specific user."""
        goal = self.get_by_user(goal_id, user_id)
        if not goal:
            return False
        
        self.db.delete(goal)
        return True
    
    def to_schema(self, goal: Goal) -> GoalSchema:
        """Convert Goal model to Goal schema."""
        goal_type = getattr(goal, 'type', None)
        if goal_type is not None and hasattr(goal_type, 'value'):
            goal_type = goal_type.value
            
        goal_status = getattr(goal, 'status', None)
        if goal_status is not None and hasattr(goal_status, 'value'):
            goal_status = goal_status.value
        elif goal_status is None:
            goal_status = "on_target"
            
        return GoalSchema(
            id=goal.id,
            title=goal.title,
            description=goal.description,
            type=goal_type,
            parent_goal_id=goal.parent_goal_id,
            end_date=goal.end_date,
            status=goal_status,
            created_at=goal.created_at
        )
