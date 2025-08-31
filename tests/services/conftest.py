import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Task, Project, Goal, Tag


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


@pytest.fixture
def sample_task_data():
    """Sample task data for testing."""
    return {
        "title": "Test Task",
        "description": "A test task",
        "status": "backlog",
        "tags": ["test", "sample"]
    }


@pytest.fixture
def sample_project_data():
    """Sample project data for testing.""" 
    return {
        "name": "Test Project",
        "color": "#ff0000"
    }


@pytest.fixture
def sample_goal_data():
    """Sample goal data for testing."""
    return {
        "title": "Test Goal",
        "type": "personal"
    }