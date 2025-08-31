from abc import ABC
from sqlalchemy.orm import Session
from app.core.logging import get_logger


class BaseService(ABC):
    """Base service class with common functionality."""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger(self.__class__.__name__)
    
    def commit(self):
        """Commit database transaction."""
        try:
            self.db.commit()
            self.logger.debug("Database transaction committed")
        except Exception as e:
            self.logger.error(f"Database commit failed: {str(e)}")
            self.db.rollback()
            raise
    
    def rollback(self):
        """Rollback database transaction."""
        self.db.rollback()
        self.logger.debug("Database transaction rolled back")