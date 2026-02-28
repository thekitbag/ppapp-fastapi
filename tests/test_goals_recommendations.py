from datetime import datetime, timedelta, timezone
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

def _mk_task(title, status="backlog", tags=None, hard_due_at=None, soft_due_at=None, sort_order=0, created_at=None, project_id=None):
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
        project_id=project_id,
    )

def _mk_goal(title, description=None, status=None, end_date=None):
    return _Goal(
        id=f"goal_{title.lower().replace(' ', '_')}",
        title=title,
        description=description,
        status=SimpleNamespace(value=status) if status else None,
        end_date=end_date,
    )

def test_goal_linked_factor():
    """Test that tasks linked to goals get a boost in priority."""
    
    # Create tasks
    t1 = _mk_task("Task without goal", status="today", sort_order=0)
    t2 = _mk_task("Task with goal", status="today", sort_order=0)
    
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
            if "TaskGoal" in model_str:
                # Return task-goal link only for t2 - make sure goal_id matches the goal created above
                result = [SimpleNamespace(task_id="Task with goal", goal_id="goal_improve_product")]
                return result
            elif "Goal" in model_str and "TaskGoal" not in model_str:
                # Return goal objects - make sure the goal has the expected ID
                return [goal]
            # Return empty result for other models
            return []
            
        def in_(self, ids):
            return self
    
    mock_db = MockDB()
    
    # Debug: Print goal information
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
    t1 = _mk_task("Important task", status="today")
    
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
    
    # Score difference = goal_linked weight / max_raw * 100
    # SUGGEST-002 default weights (no energy/time_window active):
    # 10+5+2+0.12+0.10+10+15+10 = 52.22 → goal_linked boost ≈ 0.19%
    default_weights_sum = sum([10, 5, 2, 0.12, 0.10, 0, 0, 10, 15, 10])
    expected_boost = (0.10 / default_weights_sum) * 100
    assert abs((goal_task.score - no_goal_task.score) - expected_boost) < 0.1


# ---------------------------------------------------------------------------
# SUGGEST-002: goal health status and urgency scoring
# ---------------------------------------------------------------------------

def _build_mock_db(task_goal_links, goals):
    """Build a minimal mock DB for goal health tests."""
    goals_by_id = {g.id: g for g in goals}

    class _Link:
        def __init__(self, task_id, goal_id):
            self.task_id = task_id
            self.goal_id = goal_id

    links = [_Link(tid, gid) for tid, gid in task_goal_links]

    class _MockDB:
        def __init__(self):
            self._model = None

        def query(self, model):
            self._model = model
            return self

        def filter(self, *args):
            return self

        def all(self):
            model_str = str(self._model) if self._model else ""
            if "TaskGoal" in model_str:
                return links
            if "Goal" in model_str and "TaskGoal" not in model_str:
                return list(goals_by_id.values())
            return []

        def in_(self, ids):
            return self

    return _MockDB()


def test_off_target_goal_boosts_score():
    """Task linked to off_target goal receives goal_status_off_target boost."""
    t = _mk_task("Linked task", status="backlog")
    goal = _mk_goal("Off Goal", status="off_target")
    db = _build_mock_db([(t.id, goal.id)], [goal])

    ranked = prioritize_tasks([t], db=db)

    assert ranked[0].factors["goal_status_off_target"] == 1.0
    assert ranked[0].factors["goal_status_at_risk"] == 0.0
    assert ranked[0].score > 0


def test_at_risk_goal_boosts_score():
    """Task linked to at_risk goal receives goal_status_at_risk boost only."""
    t = _mk_task("Linked task", status="backlog")
    goal = _mk_goal("Risk Goal", status="at_risk")
    db = _build_mock_db([(t.id, goal.id)], [goal])

    ranked = prioritize_tasks([t], db=db)

    assert ranked[0].factors["goal_status_at_risk"] == 1.0
    assert ranked[0].factors["goal_status_off_target"] == 0.0


def test_off_target_outranks_at_risk():
    """Task linked to off_target goal scores higher than task linked to at_risk goal."""
    t_off = _mk_task("Off target task", status="backlog", sort_order=0)
    t_risk = _mk_task("At risk task", status="backlog", sort_order=0)
    goal_off = _mk_goal("Off Target", status="off_target")
    goal_risk = _mk_goal("At Risk", status="at_risk")

    db = _build_mock_db(
        [(t_off.id, goal_off.id), (t_risk.id, goal_risk.id)],
        [goal_off, goal_risk],
    )

    ranked = prioritize_tasks([t_risk, t_off], db=db)
    assert ranked[0].task.id == t_off.id


def test_goal_urgency_near_end_date():
    """Task with goal expiring soon gets non-zero goal_urgency factor."""
    now = datetime.now(timezone.utc)
    t = _mk_task("Urgent task", status="backlog")
    goal = _mk_goal("Near Goal", end_date=now + timedelta(days=3))
    db = _build_mock_db([(t.id, goal.id)], [goal])

    ranked = prioritize_tasks([t], db=db)

    assert ranked[0].factors["goal_urgency"] > 0.5


def test_goal_urgency_why_text():
    """why text mentions 'goal due' when urgency > 0.5."""
    now = datetime.now(timezone.utc)
    t = _mk_task("Urgent task", status="backlog")
    goal = _mk_goal("Near Goal", end_date=now + timedelta(days=2))
    db = _build_mock_db([(t.id, goal.id)], [goal])

    ranked = prioritize_tasks([t], db=db)

    assert "goal due" in ranked[0].why.lower()


def test_no_n_plus_1_goal_fetches():
    """Goal objects are fetched in a single batch query, not per task."""
    t1 = _mk_task("Task A", status="backlog")
    t2 = _mk_task("Task B", status="backlog")
    goal = _mk_goal("Shared Goal", status="at_risk")

    query_count = {"n": 0}

    class _CountingDB:
        def __init__(self):
            self._model = None

        def query(self, model):
            self._model = model
            query_count["n"] += 1
            return self

        def filter(self, *args):
            return self

        def all(self):
            model_str = str(self._model) if self._model else ""
            if "TaskGoal" in model_str:
                return [
                    SimpleNamespace(task_id=t1.id, goal_id=goal.id, user_id=None),
                    SimpleNamespace(task_id=t2.id, goal_id=goal.id, user_id=None),
                ]
            if "Goal" in model_str and "TaskGoal" not in model_str:
                return [goal]
            return []

        def in_(self, ids):
            return self

    db = _CountingDB()
    prioritize_tasks([t1, t2], db=db)

    # Should be at most 3 batched queries: projects, task_goals, goals
    # (not one per task or one per goal link)
    assert query_count["n"] <= 3