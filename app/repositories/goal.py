from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.orm import aliased
import uuid

from app.models import Goal, GoalTypeEnum
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
        return super().get_by_user(goal_id, user_id)
    
    def get_multi_by_user(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Goal]:
        """Get goals for specific user."""
        return super().get_multi_by_user(
            user_id,
            skip=skip,
            limit=limit,
            order_by=[Goal.created_at.desc()],
        )
    
    def delete_by_user(self, goal_id: str, user_id: str) -> bool:
        """Delete a goal by ID for specific user."""
        return super().delete_by_user(goal_id, user_id)

    def list_goals(
        self,
        user_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
        is_closed: Optional[bool] = None,
        include_archived: bool = False,
    ) -> List[Goal]:
        """List goals within user scope with standard filtering/ordering."""
        query = self.db.query(Goal).filter(Goal.user_id == user_id)

        if not include_archived:
            query = query.filter(Goal.is_archived == False)

        if is_closed is not None:
            query = query.filter(Goal.is_closed == is_closed)

        return (
            query.order_by(Goal.priority.desc(), Goal.end_date.asc().nullslast(), Goal.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_goals_by_type(
        self,
        user_id: str,
        goal_type: str,
        *,
        parent_id: Optional[str] = None,
        include_archived: bool = False,
    ) -> List[Goal]:
        """List goals by type within a user scope, filtering out closed parents for child goal types."""
        try:
            type_enum = GoalTypeEnum(goal_type)
        except Exception as e:
            raise ValueError("Invalid goal type") from e

        query = self.db.query(Goal).filter(Goal.type == type_enum, Goal.user_id == user_id)

        if not include_archived:
            query = query.filter(Goal.is_archived == False)

        if parent_id:
            query = query.filter(Goal.parent_goal_id == parent_id)
        elif goal_type == "annual":
            query = query.filter(Goal.parent_goal_id.is_(None))
        else:
            ParentGoal = aliased(Goal)
            query = query.outerjoin(ParentGoal, Goal.parent_goal_id == ParentGoal.id)
            query = query.filter((ParentGoal.id == None) | (ParentGoal.is_closed == False))

        return query.order_by(Goal.priority.desc(), Goal.end_date.asc().nullslast(), Goal.created_at.asc()).all()

    def list_siblings_for_reorder(self, user_id: str, goal: Goal) -> List[Goal]:
        """List reorder-eligible siblings for a given goal within user scope."""
        query = self.db.query(Goal).filter(
            Goal.user_id == user_id,
            Goal.is_archived == False,
            Goal.is_closed == False,
        )

        if goal.parent_goal_id is not None:
            query = query.filter(Goal.parent_goal_id == goal.parent_goal_id)
        else:
            query = query.filter(Goal.parent_goal_id.is_(None))

        if goal.type is not None:
            query = query.filter(Goal.type == goal.type)
        else:
            query = query.filter(Goal.type.is_(None))

        siblings = query.all()
        siblings.sort(key=lambda g: (-g.priority, g.created_at))
        return siblings
    
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
            is_closed=goal.is_closed,
            closed_at=goal.closed_at,
            is_archived=goal.is_archived,
            priority=goal.priority,
            created_at=goal.created_at
        )
