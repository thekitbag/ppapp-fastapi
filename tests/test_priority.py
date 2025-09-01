from datetime import datetime, timedelta, timezone
from app.services.recommendations import prioritize_tasks, _calculate_project_due_proximity
from types import SimpleNamespace
import math

class _Tag(SimpleNamespace):
    pass

class _Task(SimpleNamespace):
    pass

class _Project(SimpleNamespace):
    pass

def _mk_task(title, status="inbox", tags=None, hard_due_at=None, soft_due_at=None, sort_order=0, created_at=None, project_id=None):
    return _Task(
        id=title,
        title=title,
        status=SimpleNamespace(value=status),
        tags=[_Tag(name=t) for t in (tags or [])],
        hard_due_at=hard_due_at,
        soft_due_at=soft_due_at,
        sort_order=sort_order,
        created_at=created_at or datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        effort_minutes=None,
        project_id=project_id,
    )

def _mk_project(name, milestone_title=None, milestone_due_at=None):
    return _Project(
        id=f"project_{name.lower()}",
        name=name,
        milestone_title=milestone_title,
        milestone_due_at=milestone_due_at,
    )

def test_prioritize_tasks_simple_formula():
    now = datetime.now(timezone.utc)
    t1 = _mk_task("A inbox no due", status="inbox", sort_order=100)
    t2 = _mk_task("B todo due soon goal", status="todo", tags=["goal"], hard_due_at=now + timedelta(hours=2), sort_order=500)
    t3 = _mk_task("C todo no due", status="todo", sort_order=10)
    ranked = prioritize_tasks([t1, t2, t3])
    # B has +10 (todo) +5 (due soon) +2 (goal) + 0 (no project) = 17 out of possible 17.12 -> ~99%
    # C has +10 (todo) = 10 out of 17.12 -> ~58%
    # A has 0 -> 0
    assert ranked[0].task.title == "B todo due soon goal"
    assert ranked[0].score > 98  # Should be around 99%
    assert ranked[0].factors["due_proximity"] == 1
    assert ranked[0].factors["goal_align"] == 1
    assert ranked[0].factors["status_boost"] == 1


def test_calculate_project_due_proximity():
    """Test the project milestone proximity calculation function."""
    now = datetime.now(timezone.utc)
    
    # Test no project
    score, days = _calculate_project_due_proximity(None, now)
    assert score == 0.0
    assert days == 0
    
    # Test project with no milestone
    project_no_milestone = _mk_project("Test")
    score, days = _calculate_project_due_proximity(project_no_milestone, now)
    assert score == 0.0
    assert days == 0
    
    # Test project with past milestone
    project_past = _mk_project("Past", "v1.0", now - timedelta(days=1))
    score, days = _calculate_project_due_proximity(project_past, now)
    assert score == 0.0
    assert days == 0
    
    # Test project due in 1 day (should be high score ~0.88)
    project_1day = _mk_project("Soon", "v1.0", now + timedelta(days=1))
    score, days = _calculate_project_due_proximity(project_1day, now)
    assert days == 1
    assert score > 0.8  # Should be around 0.88
    
    # Test project due in 7 days (should be ~0.5)
    project_7day = _mk_project("Medium", "v1.0", now + timedelta(days=7))
    score, days = _calculate_project_due_proximity(project_7day, now)
    assert days == 7
    assert 0.4 < score < 0.6  # Should be around 0.5
    
    # Test project due in 14 days (should be low ~0.12)
    project_14day = _mk_project("Far", "v1.0", now + timedelta(days=14))
    score, days = _calculate_project_due_proximity(project_14day, now)
    assert days == 14
    assert score < 0.2  # Should be around 0.12


def test_prioritize_tasks_with_project_milestones():
    """Test that tasks linked to projects with near milestones get higher priority."""
    now = datetime.now(timezone.utc)
    
    # Create projects with different milestone dates
    project_soon = _mk_project("WebsiteLaunch", "v1.0 Release", now + timedelta(days=5))
    project_far = _mk_project("Research", "Analysis Done", now + timedelta(days=20))
    
    # Create mock db session
    class MockDB:
        def query(self, model):
            return self
        def filter(self, condition):
            return self
        def all(self):
            return [project_soon, project_far]
    
    mock_db = MockDB()
    
    # Create tasks linked to these projects
    t1 = _mk_task("Task without project", status="todo", sort_order=0)
    t2 = _mk_task("Task with soon milestone", status="todo", sort_order=0, project_id="project_websitelaunch")
    t3 = _mk_task("Task with far milestone", status="todo", sort_order=0, project_id="project_research")
    
    ranked = prioritize_tasks([t1, t2, t3], db=mock_db)
    
    # Task with soon project milestone should rank higher
    assert ranked[0].task.title == "Task with soon milestone"
    assert ranked[0].factors["project_due_proximity"] > 0.3
    # Check that project name is in explanation (case may vary)
    assert "websitelaunch" in ranked[0].why.lower()
    assert "milestone in" in ranked[0].why
    
    # Task with far milestone should have lower project proximity factor
    task_far = next(r for r in ranked if r.task.title == "Task with far milestone")
    assert task_far.factors["project_due_proximity"] < 0.3
    
    # Task without project should have 0 project proximity
    task_no_project = next(r for r in ranked if r.task.title == "Task without project")
    assert task_no_project.factors["project_due_proximity"] == 0.0


def test_project_milestone_explanation_text():
    """Test that project milestone information appears in explanations."""
    now = datetime.now(timezone.utc)
    
    project_1_day = _mk_project("UrgentProject", "Launch", now + timedelta(days=1))
    project_6_days = _mk_project("RegularProject", "Milestone", now + timedelta(days=6))
    
    class MockDB:
        def query(self, model):
            return self
        def filter(self, condition):
            return self
        def all(self):
            return [project_1_day, project_6_days]
    
    mock_db = MockDB()
    
    # Test 1 day milestone
    t1 = _mk_task("Task due in 1 day", status="todo", project_id="project_urgentproject")
    ranked = prioritize_tasks([t1], db=mock_db)
    # Check that project name is in explanation (case may vary, timing may vary by seconds)
    assert "urgentproject" in ranked[0].why.lower()
    assert "milestone in" in ranked[0].why
    
    # Test multiple days milestone  
    t2 = _mk_task("Task due in 6 days", status="todo", project_id="project_regularproject")
    ranked = prioritize_tasks([t2], db=mock_db)
    assert "regularproject" in ranked[0].why.lower()  
    assert "milestone in" in ranked[0].why


def test_project_milestone_weights():
    """Test that project milestone weight (0.12) is applied correctly."""
    now = datetime.now(timezone.utc)
    
    # Create a project with a milestone in 5 days
    project = _mk_project("TestProject", "v1.0", now + timedelta(days=5))
    
    class MockDB:
        def query(self, model):
            return self
        def filter(self, condition):
            return self
        def all(self):
            return [project]
    
    mock_db = MockDB()
    
    # Create tasks - one with project, one without
    t1 = _mk_task("No project task", status="backlog", sort_order=0)
    t2 = _mk_task("Project task", status="backlog", sort_order=0, project_id="project_testproject")
    
    ranked = prioritize_tasks([t1, t2], db=mock_db)
    
    # Task with project milestone should score higher due to project_due_proximity factor
    project_task = next(r for r in ranked if r.task.title == "Project task")
    no_project_task = next(r for r in ranked if r.task.title == "No project task")
    
    # The project task should have additional score from project_due_proximity
    assert project_task.score > no_project_task.score
    assert project_task.factors["project_due_proximity"] > 0
    assert no_project_task.factors["project_due_proximity"] == 0
