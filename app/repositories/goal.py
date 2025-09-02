from typing import List
from sqlalchemy.orm import Session
import uuid

from app.models import Goal
from app.schemas import GoalCreate, Goal as GoalSchema
from .base import BaseRepository


class GoalRepository(BaseRepository[Goal, GoalCreate, dict]):
    """Repository for Goal operations."""
    
    def __init__(self, db: Session):
        super().__init__(db, Goal)
    
    def _gen_id(self, prefix: str = "goal") -> str:
        """Generate unique ID with prefix."""
        return f"{prefix}_{uuid.uuid4()}"
    
    def create_with_id(self, goal_in: GoalCreate) -> Goal:
        """Create goal with generated ID."""
        goal_data = goal_in.model_dump()
        goal = Goal(
            id=self._gen_id("goal"),
            **goal_data
        )
        
        self.db.add(goal)
        self.db.flush()
        self.db.refresh(goal)
        return goal
    
    def to_schema(self, goal: Goal) -> GoalSchema:
        """Convert Goal model to Goal schema."""
        return GoalSchema(
            id=goal.id,
            title=goal.title,
            description=goal.description,
            type=goal.type,
            created_at=goal.created_at
        )