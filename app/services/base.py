from abc import ABC
from contextlib import contextmanager
from sqlalchemy.orm import Session
from app.core.logging import get_logger

_BOUNDARY = 'eigentask_atomic_boundary'


@contextmanager
def atomic(db: Session):
    """Own a composed operation's commit; nested services only flush.

    A read may already have started SQLAlchemy's implicit transaction. Joining
    that is safe, but never adopt unrelated pending writes from a caller.
    """
    if _BOUNDARY in db.info:
        try:
            yield
        except BaseException:
            db.info[_BOUNDARY]['failed'] = True
            raise
        return
    if db.new or db.dirty or db.deleted:
        raise RuntimeError('Atomic operations require a session without pending writes')
    boundary = {'failed': False}
    db.info[_BOUNDARY] = boundary
    try:
        yield
        if boundary['failed']:
            raise RuntimeError('A nested operation failed; the transaction cannot commit')
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.info.pop(_BOUNDARY, None)


class BaseService(ABC):
    """Base service class with common functionality."""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger(self.__class__.__name__)
    
    def commit(self):
        """Commit database transaction."""
        try:
            if _BOUNDARY in self.db.info:
                self.db.flush()
                return
            self.db.commit()
            self.logger.debug("Database transaction committed")
        except Exception as e:
            self.logger.error('Database commit failed')
            self.rollback()
            raise
    
    def rollback(self):
        """Rollback database transaction."""
        if _BOUNDARY in self.db.info:
            self.db.info[_BOUNDARY]['failed'] = True
            return
        self.db.rollback()
        self.logger.debug("Database transaction rolled back")
