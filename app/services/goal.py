from typing import List
from sqlalchemy.orm import Session

from app.repositories import GoalRepository
from app.schemas import GoalCreate, Goal as GoalSchema
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