import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def cleanup_tasks():
    """Clean up tasks created during testing."""
    # Get all tasks
    response = client.get("/api/v1/tasks")
    if response.status_code == 200:
        tasks = response.json()
        # Delete test tasks by checking title patterns
        for task in tasks:
            if any(pattern in task["title"] for pattern in [
                "Task A", "Task B", "Task C", 
                "Backlog Task", "Week Task", 
                "Today", "Doing", "Auto Sort", "Precise Task"
            ]):
                client.delete(f"/api/v1/tasks/{task['id']}")

@pytest.fixture(autouse=True)
def clean_test_data():
    """Clean up test data before and after each test."""
    cleanup_tasks()
    yield
    cleanup_tasks()

def test_drag_reorder_within_bucket():
    """Test dragging to reorder tasks within a bucket maintains correct order."""
    
    import time
    test_id = str(int(time.time() * 1000))  # Unique test ID
    
    # Create 3 tasks in "today" status with explicit sort_order
    task_a = client.post("/api/v1/tasks", json={
        "title": f"DragTest_Task_A_{test_id}", 
        "status": "today",
        "sort_order": 1.0
    })
    assert task_a.status_code == 201
    task_a_id = task_a.json()["id"]
    
    task_b = client.post("/api/v1/tasks", json={
        "title": f"DragTest_Task_B_{test_id}", 
        "status": "today",
        "sort_order": 2.0
    })
    assert task_b.status_code == 201
    task_b_id = task_b.json()["id"]
    
    task_c = client.post("/api/v1/tasks", json={
        "title": f"DragTest_Task_C_{test_id}", 
        "status": "today",
        "sort_order": 3.0
    })
    assert task_c.status_code == 201
    task_c_id = task_c.json()["id"]
    
    # Verify initial order: A(1.0), B(2.0), C(3.0)
    response = client.get("/api/v1/tasks?status=today")
    assert response.status_code == 200
    all_tasks = response.json()
    
    # Filter for our test tasks only
    test_tasks = [t for t in all_tasks if test_id in t["title"]]
    test_tasks.sort(key=lambda x: x["sort_order"])  # Sort by sort_order to verify
    
    assert len(test_tasks) == 3
    assert test_tasks[0]["title"] == f"DragTest_Task_A_{test_id}"
    assert test_tasks[1]["title"] == f"DragTest_Task_B_{test_id}"
    assert test_tasks[2]["title"] == f"DragTest_Task_C_{test_id}"
    
    # Move Task C between A and B by setting sort_order = 1.5
    update_response = client.patch(f"/api/v1/tasks/{task_c_id}", json={
        "sort_order": 1.5
    })
    assert update_response.status_code == 200
    assert update_response.json()["sort_order"] == 1.5
    
    # Verify new order: A(1.0), C(1.5), B(2.0)
    response = client.get("/api/v1/tasks?status=today")
    assert response.status_code == 200
    all_tasks = response.json()
    
    # Filter and sort our test tasks
    test_tasks = [t for t in all_tasks if test_id in t["title"]]
    test_tasks.sort(key=lambda x: x["sort_order"])
    
    assert len(test_tasks) == 3
    assert test_tasks[0]["title"] == f"DragTest_Task_A_{test_id}"
    assert test_tasks[0]["sort_order"] == 1.0
    assert test_tasks[1]["title"] == f"DragTest_Task_C_{test_id}" 
    assert test_tasks[1]["sort_order"] == 1.5
    assert test_tasks[2]["title"] == f"DragTest_Task_B_{test_id}"
    assert test_tasks[2]["sort_order"] == 2.0


def test_cross_bucket_drag_preserves_ordering():
    """Test dragging across buckets maintains within-bucket ordering."""
    
    import time
    test_id = str(int(time.time() * 1000))  # Unique test ID
    
    # Create tasks in different buckets
    backlog_task = client.post("/api/v1/tasks", json={
        "title": f"CrossBucket_Backlog_{test_id}",
        "status": "backlog",
        "sort_order": 100.0
    })
    assert backlog_task.status_code == 201
    backlog_id = backlog_task.json()["id"]
    
    week_task1 = client.post("/api/v1/tasks", json={
        "title": f"CrossBucket_Week_1_{test_id}",
        "status": "week", 
        "sort_order": 200.0
    })
    assert week_task1.status_code == 201
    
    week_task2 = client.post("/api/v1/tasks", json={
        "title": f"CrossBucket_Week_2_{test_id}",
        "status": "week",
        "sort_order": 300.0
    })
    assert week_task2.status_code == 201
    
    # Move backlog task to week bucket with sort_order between the two
    client.patch(f"/api/v1/tasks/{backlog_id}", json={
        "status": "week",
        "sort_order": 250.0
    })
    
    # Verify order within week bucket: Week Task 1, Backlog Task, Week Task 2
    response = client.get("/api/v1/tasks?status=week")
    assert response.status_code == 200
    all_tasks = response.json()
    
    # Filter for our test tasks only
    tasks = [t for t in all_tasks if test_id in t["title"]]
    tasks.sort(key=lambda x: x["sort_order"])  # Sort by sort_order
    
    assert len(tasks) == 3
    assert tasks[0]["title"] == f"CrossBucket_Week_1_{test_id}"
    assert tasks[0]["sort_order"] == 200.0
    assert tasks[1]["title"] == f"CrossBucket_Backlog_{test_id}"
    assert tasks[1]["sort_order"] == 250.0
    assert tasks[2]["title"] == f"CrossBucket_Week_2_{test_id}"
    assert tasks[2]["sort_order"] == 300.0


def test_multiple_status_maintains_bucket_ordering():
    """Test GET with multiple status values maintains per-bucket ordering."""
    
    import time
    test_id = str(int(time.time() * 1000))  # Unique test ID
    
    # Create tasks in different statuses with various sort orders
    client.post("/api/v1/tasks", json={
        "title": f"MultiBucket_Today_1_{test_id}", "status": "today", "sort_order": 10.0
    })
    client.post("/api/v1/tasks", json={
        "title": f"MultiBucket_Today_2_{test_id}", "status": "today", "sort_order": 5.0
    })
    client.post("/api/v1/tasks", json={
        "title": f"MultiBucket_Doing_1_{test_id}", "status": "doing", "sort_order": 30.0
    })
    client.post("/api/v1/tasks", json={
        "title": f"MultiBucket_Doing_2_{test_id}", "status": "doing", "sort_order": 20.0
    })
    
    # Get tasks from multiple buckets
    response = client.get("/api/v1/tasks?status=today&status=doing")
    assert response.status_code == 200
    all_tasks = response.json()
    
    # Filter for our test tasks only
    tasks = [t for t in all_tasks if test_id in t["title"]]
    
    # Should be ordered by status first, then sort_order within each status
    assert len(tasks) == 4
    
    # Verify within-bucket ordering is maintained
    today_tasks = [t for t in tasks if t["status"] == "today"]
    doing_tasks = [t for t in tasks if t["status"] == "doing"]
    
    assert len(today_tasks) == 2
    # Sort by sort_order to verify ordering
    today_tasks.sort(key=lambda x: x["sort_order"])
    assert today_tasks[0]["title"] == f"MultiBucket_Today_2_{test_id}"  # sort_order 5.0
    assert today_tasks[1]["title"] == f"MultiBucket_Today_1_{test_id}"  # sort_order 10.0
    
    assert len(doing_tasks) == 2
    # Sort by sort_order to verify ordering
    doing_tasks.sort(key=lambda x: x["sort_order"])
    assert doing_tasks[0]["title"] == f"MultiBucket_Doing_2_{test_id}"  # sort_order 20.0
    assert doing_tasks[1]["title"] == f"MultiBucket_Doing_1_{test_id}"  # sort_order 30.0


def test_sort_order_auto_assigned_on_create():
    """Test that sort_order is auto-assigned when not provided."""
    
    import time
    test_id = str(int(time.time() * 1000))
    
    # Create task without sort_order
    response = client.post("/api/v1/tasks", json={
        "title": f"AutoSort_Task_1_{test_id}",
        "status": "backlog"
    })
    assert response.status_code == 201
    
    task = response.json()
    assert "sort_order" in task
    assert task["sort_order"] is not None
    assert task["sort_order"] > 0  # Should be epoch milliseconds
    
    # Create another task and verify it has a different sort_order
    response2 = client.post("/api/v1/tasks", json={
        "title": f"AutoSort_Task_2_{test_id}",
        "status": "backlog"
    })
    assert response2.status_code == 201
    
    task2 = response2.json()
    assert task2["sort_order"] != task["sort_order"]


def test_float_precision_preserved():
    """Test that decimal sort_order values are preserved precisely."""
    
    import time
    test_id = str(int(time.time() * 1000))
    
    # Create task with precise decimal sort_order
    response = client.post("/api/v1/tasks", json={
        "title": f"Precise_Task_{test_id}",
        "status": "today",
        "sort_order": 123.456789
    })
    assert response.status_code == 201
    
    task = response.json()
    assert task["sort_order"] == 123.456789
    
    # Update with another precise decimal
    update_response = client.patch(f"/api/v1/tasks/{task['id']}", json={
        "sort_order": 987.123456
    })
    assert update_response.status_code == 200
    
    updated_task = update_response.json()
    assert updated_task["sort_order"] == 987.123456


def test_server_side_ordering_guarantees():
    """Test that API returns tasks in correct order without client-side sorting."""
    
    import time
    test_id = str(int(time.time() * 1000))
    
    # Create tasks with specific sort_order values (out of order chronologically)
    task_c = client.post("/api/v1/tasks", json={
        "title": f"ServerOrder_Task_C_{test_id}",
        "status": "today", 
        "sort_order": 3.0
    })
    assert task_c.status_code == 201
    
    task_a = client.post("/api/v1/tasks", json={
        "title": f"ServerOrder_Task_A_{test_id}",
        "status": "today",
        "sort_order": 1.0  
    })
    assert task_a.status_code == 201
    
    task_b = client.post("/api/v1/tasks", json={
        "title": f"ServerOrder_Task_B_{test_id}",
        "status": "today",
        "sort_order": 2.0
    })
    assert task_b.status_code == 201
    
    # Get tasks without any client-side sorting
    response = client.get("/api/v1/tasks?status=today")
    assert response.status_code == 200
    all_tasks = response.json()
    
    # Filter for our test tasks only (preserving API response order)
    test_tasks = [t for t in all_tasks if test_id in t["title"]]
    
    # Verify server returned them in correct sort_order (API should guarantee this)
    assert len(test_tasks) == 3
    assert test_tasks[0]["title"] == f"ServerOrder_Task_A_{test_id}"  # sort_order 1.0
    assert test_tasks[0]["sort_order"] == 1.0
    assert test_tasks[1]["title"] == f"ServerOrder_Task_B_{test_id}"  # sort_order 2.0  
    assert test_tasks[1]["sort_order"] == 2.0
    assert test_tasks[2]["title"] == f"ServerOrder_Task_C_{test_id}"  # sort_order 3.0
    assert test_tasks[2]["sort_order"] == 3.0
    
    # Also verify sort_order values are in ascending order as returned by API
    for i in range(len(test_tasks) - 1):
        assert test_tasks[i]["sort_order"] <= test_tasks[i + 1]["sort_order"], \
            f"API returned tasks out of order: {test_tasks[i]['sort_order']} > {test_tasks[i+1]['sort_order']}"