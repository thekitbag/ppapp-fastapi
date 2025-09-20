"""Test goal lifecycle functionality (close/reopen, filtering)."""
from fastapi.testclient import TestClient
from app.main import app
import uuid

client = TestClient(app)


def test_close_goal():
    """Test closing a goal sets is_closed=True and closed_at timestamp."""
    # Create proper hierarchy: annual -> quarterly -> weekly
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    assert weekly_goal["is_closed"] is False
    assert weekly_goal["closed_at"] is None

    # Close the weekly goal
    close_response = client.post(f"/api/v1/goals/{weekly_goal['id']}/close")
    assert close_response.status_code == 200
    closed_goal = close_response.json()
    assert closed_goal["is_closed"] is True
    assert closed_goal["closed_at"] is not None
    assert closed_goal["id"] == weekly_goal["id"]


def test_close_goal_idempotent():
    """Test that closing an already closed goal is idempotent."""
    # Create proper hierarchy and get weekly goal
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    first_close = client.post(f"/api/v1/goals/{weekly_goal['id']}/close")
    assert first_close.status_code == 200
    first_closed_goal = first_close.json()

    # Close again - should be idempotent
    second_close = client.post(f"/api/v1/goals/{weekly_goal['id']}/close")
    assert second_close.status_code == 200
    second_closed_goal = second_close.json()

    # Should be the same
    assert first_closed_goal["is_closed"] == second_closed_goal["is_closed"]
    assert first_closed_goal["closed_at"] == second_closed_goal["closed_at"]


def test_reopen_goal():
    """Test reopening a closed goal sets is_closed=False and closed_at=NULL."""
    # Create proper hierarchy and get weekly goal
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    client.post(f"/api/v1/goals/{weekly_goal['id']}/close")

    # Reopen the goal
    reopen_response = client.post(f"/api/v1/goals/{weekly_goal['id']}/reopen")
    assert reopen_response.status_code == 200
    reopened_goal = reopen_response.json()
    assert reopened_goal["is_closed"] is False
    assert reopened_goal["closed_at"] is None
    assert reopened_goal["id"] == weekly_goal["id"]


def test_reopen_goal_idempotent():
    """Test that reopening an already open goal is idempotent."""
    # Create annual goal (open by default)
    annual_goal = client.post("/api/v1/goals", json={"title": "Annual Goal", "type": "annual"}).json()

    # Reopen an already open goal - should be idempotent
    reopen_response = client.post(f"/api/v1/goals/{annual_goal['id']}/reopen")
    assert reopen_response.status_code == 200
    reopened_goal = reopen_response.json()
    assert reopened_goal["is_closed"] is False
    assert reopened_goal["closed_at"] is None


def test_close_nonexistent_goal():
    """Test closing a non-existent goal returns 404."""
    fake_id = f"goal_{uuid.uuid4()}"
    response = client.post(f"/api/v1/goals/{fake_id}/close")
    assert response.status_code == 404


def test_reopen_nonexistent_goal():
    """Test reopening a non-existent goal returns 404."""
    fake_id = f"goal_{uuid.uuid4()}"
    response = client.post(f"/api/v1/goals/{fake_id}/reopen")
    assert response.status_code == 404


def test_list_goals_filter_open():
    """Test filtering goals by is_closed=false."""
    # Create open and closed goals using annual goals (simpler hierarchy)
    open_goal = client.post("/api/v1/goals", json={"title": "Open Goal", "type": "annual"}).json()
    closed_goal = client.post("/api/v1/goals", json={"title": "Closed Goal", "type": "annual"}).json()

    # Close one goal
    client.post(f"/api/v1/goals/{closed_goal['id']}/close")

    # Filter for open goals only
    response = client.get("/api/v1/goals?is_closed=false")
    assert response.status_code == 200
    goals = response.json()

    # Should only contain open goals
    goal_ids = [g["id"] for g in goals]
    assert open_goal["id"] in goal_ids
    assert closed_goal["id"] not in goal_ids

    # Verify all returned goals are open
    assert all(not g["is_closed"] for g in goals)


def test_list_goals_filter_closed():
    """Test filtering goals by is_closed=true."""
    # Create open and closed goals using annual goals (simpler hierarchy)
    open_goal = client.post("/api/v1/goals", json={"title": "Open Goal", "type": "annual"}).json()
    closed_goal = client.post("/api/v1/goals", json={"title": "Closed Goal", "type": "annual"}).json()

    # Close one goal
    client.post(f"/api/v1/goals/{closed_goal['id']}/close")

    # Filter for closed goals only
    response = client.get("/api/v1/goals?is_closed=true")
    assert response.status_code == 200
    goals = response.json()

    # Should only contain closed goals
    goal_ids = [g["id"] for g in goals]
    assert open_goal["id"] not in goal_ids
    assert closed_goal["id"] in goal_ids

    # Verify all returned goals are closed
    assert all(g["is_closed"] for g in goals)


def test_list_goals_no_filter():
    """Test listing all goals without filter returns both open and closed."""
    # Create open and closed goals using annual goals (simpler hierarchy)
    open_goal = client.post("/api/v1/goals", json={"title": "Open Goal", "type": "annual"}).json()
    closed_goal = client.post("/api/v1/goals", json={"title": "Closed Goal", "type": "annual"}).json()

    # Close one goal
    client.post(f"/api/v1/goals/{closed_goal['id']}/close")

    # Get all goals (no filter)
    response = client.get("/api/v1/goals")
    assert response.status_code == 200
    goals = response.json()

    # Should contain both open and closed goals
    goal_ids = [g["id"] for g in goals]
    assert open_goal["id"] in goal_ids
    assert closed_goal["id"] in goal_ids


def test_goals_tree_excludes_closed_by_default():
    """Test that GET /goals/tree excludes closed goals by default."""
    # Create a hierarchy: annual -> quarterly -> weekly
    annual_goal = client.post("/api/v1/goals", json={"title": "Tree Test Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Tree Test Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Tree Test Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    # Close the quarterly goal
    client.post(f"/api/v1/goals/{quarterly_goal['id']}/close")

    # Get tree (default: exclude closed)
    response = client.get("/api/v1/goals/tree")
    assert response.status_code == 200
    tree = response.json()

    # Find our specific annual goal in the tree
    our_annual = None
    for goal in tree:
        if goal["id"] == annual_goal["id"]:
            our_annual = goal
            break

    assert our_annual is not None, "Our annual goal should be in the tree"
    assert len(our_annual["children"]) == 0, "Quarterly goal is closed, so should be excluded from children"


def test_goals_tree_includes_closed_when_requested():
    """Test that GET /goals/tree includes closed goals when include_closed=true."""
    # Create a hierarchy: annual -> quarterly -> weekly
    annual_goal = client.post("/api/v1/goals", json={"title": "Tree Closed Test Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Tree Closed Test Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Tree Closed Test Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    # Close the quarterly goal
    client.post(f"/api/v1/goals/{quarterly_goal['id']}/close")

    # Get tree including closed goals
    response = client.get("/api/v1/goals/tree?include_closed=true")
    assert response.status_code == 200
    tree = response.json()

    # Find our specific annual goal in the tree
    our_annual = None
    for goal in tree:
        if goal["id"] == annual_goal["id"]:
            our_annual = goal
            break

    assert our_annual is not None, "Our annual goal should be in the tree"
    assert len(our_annual["children"]) == 1, "Should contain the closed quarterly goal when include_closed=true"

    quarterly_child = our_annual["children"][0]
    assert quarterly_child["id"] == quarterly_goal["id"]
    assert quarterly_child["is_closed"] is True, "Quarterly goal should be marked as closed"
    assert len(quarterly_child["children"]) == 1, "Quarterly should contain its weekly child"
    assert quarterly_child["children"][0]["id"] == weekly_goal["id"]


def test_goals_tree_closed_parent_hides_open_children():
    """Test that when a parent goal is closed, its open children are hidden from open tree."""
    # Create a hierarchy: annual -> quarterly -> weekly
    annual_goal = client.post("/api/v1/goals", json={"title": "Tree Parent Test Annual Goal", "type": "annual"}).json()
    quarterly_goal = client.post("/api/v1/goals", json={
        "title": "Tree Parent Test Quarterly Goal",
        "type": "quarterly",
        "parent_goal_id": annual_goal["id"]
    }).json()
    weekly_goal = client.post("/api/v1/goals", json={
        "title": "Tree Parent Test Weekly Goal",
        "type": "weekly",
        "parent_goal_id": quarterly_goal["id"]
    }).json()

    # Close the quarterly goal (weekly remains open)
    client.post(f"/api/v1/goals/{quarterly_goal['id']}/close")

    # Get tree (default: exclude closed)
    response = client.get("/api/v1/goals/tree")
    assert response.status_code == 200
    tree = response.json()

    # Find our specific annual goal in the tree
    our_annual = None
    for goal in tree:
        if goal["id"] == annual_goal["id"]:
            our_annual = goal
            break

    assert our_annual is not None, "Our annual goal should be in the tree"
    assert len(our_annual["children"]) == 0, "Weekly goal should be hidden because its parent (quarterly) is closed"


def test_goals_closed_field_in_response():
    """Test that goal responses include is_closed and closed_at fields."""
    # Create an annual goal
    goal_response = client.post("/api/v1/goals", json={"title": "Test Goal", "type": "annual"})
    goal = goal_response.json()

    # Check initial state
    assert "is_closed" in goal
    assert "closed_at" in goal
    assert goal["is_closed"] is False
    assert goal["closed_at"] is None

    # Close the goal and check fields are updated
    close_response = client.post(f"/api/v1/goals/{goal['id']}/close")
    closed_goal = close_response.json()

    assert closed_goal["is_closed"] is True
    assert closed_goal["closed_at"] is not None
    assert isinstance(closed_goal["closed_at"], str)  # Should be ISO datetime string


def test_goal_status_and_end_date_still_updateable():
    """Test that goal status and end_date can still be updated via PATCH."""
    # Create an annual goal
    goal_response = client.post("/api/v1/goals", json={"title": "Test Goal", "type": "annual"})
    goal = goal_response.json()

    # Update status and end_date
    update_data = {
        "status": "at_risk",
        "end_date": "2025-12-31T23:59:59Z"
    }
    update_response = client.patch(f"/api/v1/goals/{goal['id']}", json=update_data)
    assert update_response.status_code == 200
    updated_goal = update_response.json()

    assert updated_goal["status"] == "at_risk"
    assert updated_goal["end_date"] == "2025-12-31T23:59:59"