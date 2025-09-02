from datetime import datetime, timezone
from app.services.recommendations import prioritize_tasks, _calculate_project_due_proximity
from types import SimpleNamespace
import math

class _Tag(SimpleNamespace):
    pass

class _Task(SimpleNamespace):
    pass

class _Goal(SimpleNamespace):
    pass

class _TaskGoal(SimpleNamespace):
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

def _mk_goal(title, description=None):
    return _Goal(
        id=f"goal_{title.lower().replace(' ', '_')}",  # Replace spaces with underscores
        title=title,
        description=description,
    )

def test_goal_linked_factor():
    """Test that tasks linked to goals get a boost in priority."""
    
    # Create tasks
    t1 = _mk_task("Task without goal", status="todo", sort_order=0)
    t2 = _mk_task("Task with goal", status="todo", sort_order=0)
    
    # Create goal
    goal = _mk_goal("Improve Product")
    
    # Mock database session
    class MockDB:
        def __init__(self):
            self.current_model = None
            
        def query(self, model):
            self.current_model = model
            return self
            
        def filter(self, condition):
            return self
            
        def all(self):
            model_str = str(self.current_model) if self.current_model else ""
            print(f"DEBUG: Mock DB querying model: {model_str}")
            if "TaskGoal" in model_str:
                # Return task-goal link only for t2 - make sure goal_id matches the goal created above
                result = [SimpleNamespace(task_id="Task with goal", goal_id="goal_improve_product")]
                print(f"DEBUG: Returning TaskGoal links: {[(r.task_id, r.goal_id) for r in result]}")
                return result
            elif "Goal" in model_str and "TaskGoal" not in model_str:
                # Return goal objects - make sure the goal has the expected ID
                print(f"DEBUG: Returning Goal objects: {[(goal.id, goal.title)]}")
                return [goal]
            print(f"DEBUG: Returning empty result for model: {model_str}")
            return []
            
        def in_(self, ids):
            return self
    
    mock_db = MockDB()
    
    # Debug: Print goal information
    print(f"DEBUG: Created goal ID: {goal.id}")
    print(f"DEBUG: Created goal title: {goal.title}")
    
    # Test prioritization with goals
    ranked = prioritize_tasks([t1, t2], db=mock_db)
    
    # Debug: Print results
    print(f"DEBUG: Task 1 - {ranked[0].task.title}: goal_linked={ranked[0].factors['goal_linked']}, why='{ranked[0].why}'")
    print(f"DEBUG: Task 2 - {ranked[1].task.title}: goal_linked={ranked[1].factors['goal_linked']}, why='{ranked[1].why}'")
    
    # Task with goal should rank higher due to goal_linked factor
    assert ranked[0].task.title == "Task with goal"
    assert ranked[0].factors["goal_linked"] == 1.0
    assert ranked[1].factors["goal_linked"] == 0.0
    
    # Check that goal appears in explanation
    assert "improve product" in ranked[0].why.lower()

def test_goal_linked_explanation():
    """Test that goal linking appears in explanations."""
    
    # Create task
    t1 = _mk_task("Important task", status="todo")
    
    # Create goals
    goal1 = _mk_goal("Marketing Campaign")
    goal2 = _mk_goal("Product Launch")
    
    # Mock database session
    class MockDB:
        def __init__(self):
            self.current_model = None
            
        def query(self, model):
            self.current_model = model
            return self
            
        def filter(self, condition):
            return self
            
        def all(self):
            if self.current_model and "TaskGoal" in str(self.current_model):
                # Return multiple task-goal links
                return [
                    SimpleNamespace(task_id="Important task", goal_id="goal_marketing_campaign"),
                    SimpleNamespace(task_id="Important task", goal_id="goal_product_launch")
                ]
            elif self.current_model and "Goal" in str(self.current_model):
                return [goal1, goal2]
            return []
            
        def in_(self, ids):
            return self
    
    mock_db = MockDB()
    
    # Test prioritization
    ranked = prioritize_tasks([t1], db=mock_db)
    
    # Should show multiple goals in explanation
    why = ranked[0].why.lower()
    assert "linked to 2 goals" in why or ("marketing campaign" in why and "product launch" in why)

def test_goal_linked_weight():
    """Test that goal_linked weight (0.10) is applied correctly."""
    now = datetime.now(timezone.utc)
    
    # Create tasks - both have same status to isolate goal effect
    t1 = _mk_task("No goal task", status="backlog", sort_order=0)
    t2 = _mk_task("Goal task", status="backlog", sort_order=0)
    
    # Create goal
    goal = _mk_goal("Test Goal")
    
    # Mock database session
    class MockDB:
        def __init__(self):
            self.current_model = None
            
        def query(self, model):
            self.current_model = model
            return self
            
        def filter(self, condition):
            return self
            
        def all(self):
            if self.current_model and "TaskGoal" in str(self.current_model):
                return [SimpleNamespace(task_id="Goal task", goal_id="goal_test_goal")]
            elif self.current_model and "Goal" in str(self.current_model):
                return [goal]
            return []
            
        def in_(self, ids):
            return self
    
    mock_db = MockDB()
    
    # Test prioritization
    ranked = prioritize_tasks([t1, t2], db=mock_db)
    
    # Task with goal should score higher due to goal_linked factor
    goal_task = next(r for r in ranked if r.task.title == "Goal task")
    no_goal_task = next(r for r in ranked if r.task.title == "No goal task")
    
    # The goal task should have additional score from goal_linked factor
    assert goal_task.score > no_goal_task.score
    assert goal_task.factors["goal_linked"] == 1.0
    assert no_goal_task.factors["goal_linked"] == 0.0
    
    # Score difference should be approximately the goal_linked weight (0.10) 
    # as a percentage of max possible score
    expected_boost = (0.10 / sum([10, 5, 2, 0.12, 0.10])) * 100  # ~0.58%
    assert abs((goal_task.score - no_goal_task.score) - expected_boost) < 0.1