import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import io
import json
from app.main import app
from app.models import StatusEnum, GoalTypeEnum

client = TestClient(app)

class TestTaskVisibility:
    """Test task visibility improvements (no hard limit)."""
    
    def test_create_many_tasks_and_list_all(self):
        """Test creating >100 tasks and listing them all."""
        # Create 120 tasks
        task_ids = []
        for i in range(120):
            resp = client.post('/api/v1/tasks', json={
                'title': f'Test task {i}',
                'status': 'backlog'
            })
            assert resp.status_code == 201
            task_ids.append(resp.json()['id'])
        
        # List all tasks without limit - should return all 120
        resp = client.get('/api/v1/tasks')
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) >= 120
        
        # Test with explicit limit
        resp = client.get('/api/v1/tasks?limit=50')
        assert resp.status_code == 200
        assert len(resp.json()) == 50
        
        # Clean up
        for task_id in task_ids:
            client.delete(f'/api/v1/tasks/{task_id}')
    
    def test_pagination_with_skip(self):
        """Test pagination using skip parameter."""
        # Create some test tasks
        task_ids = []
        for i in range(10):
            resp = client.post('/api/v1/tasks', json={
                'title': f'Pagination test {i}',
                'status': 'week'
            })
            assert resp.status_code == 201
            task_ids.append(resp.json()['id'])
        
        # Test pagination
        resp = client.get('/api/v1/tasks?limit=5&skip=0')
        assert resp.status_code == 200
        page1 = resp.json()
        assert len(page1) == 5
        
        resp = client.get('/api/v1/tasks?limit=5&skip=5')
        assert resp.status_code == 200
        page2 = resp.json()
        assert len(page2) == 5
        
        # Ensure no overlap
        page1_ids = {task['id'] for task in page1}
        page2_ids = {task['id'] for task in page2}
        assert len(page1_ids & page2_ids) == 0
        
        # Clean up
        for task_id in task_ids:
            client.delete(f'/api/v1/tasks/{task_id}')


class TestTaskDefaultPlacement:
    """Test that new tasks default to 'week' status."""
    
    def test_create_task_without_status_defaults_to_week(self):
        """Test task creation without status defaults to 'week'."""
        resp = client.post('/api/v1/tasks', json={
            'title': 'Task without status'
        })
        assert resp.status_code == 201
        task = resp.json()
        assert task['status'] == 'week'
        
        # Clean up
        client.delete(f'/api/v1/tasks/{task["id"]}')
    
    def test_create_task_with_explicit_status(self):
        """Test task creation with explicit status still works."""
        resp = client.post('/api/v1/tasks', json={
            'title': 'Task with explicit status',
            'status': 'backlog'
        })
        assert resp.status_code == 201
        task = resp.json()
        assert task['status'] == 'backlog'
        
        # Clean up
        client.delete(f'/api/v1/tasks/{task["id"]}')


class TestTaskArchiving:
    """Test task archiving functionality."""
    
    def test_archive_task(self):
        """Test archiving a task."""
        # Create task
        resp = client.post('/api/v1/tasks', json={
            'title': 'Task to archive',
            'status': 'done'
        })
        assert resp.status_code == 201
        task = resp.json()
        task_id = task['id']
        
        # Archive the task
        resp = client.patch(f'/api/v1/tasks/{task_id}', json={
            'status': 'archived'
        })
        assert resp.status_code == 200
        updated_task = resp.json()
        assert updated_task['status'] == 'archived'
        
        # Clean up
        client.delete(f'/api/v1/tasks/{task_id}')
    
    def test_archived_tasks_excluded_from_default_list(self):
        """Test that archived tasks are excluded from default task list."""
        # Create a regular task
        resp = client.post('/api/v1/tasks', json={
            'title': 'Regular task',
            'status': 'week'
        })
        regular_task = resp.json()
        
        # Create and archive a task
        resp = client.post('/api/v1/tasks', json={
            'title': 'Task to archive',
            'status': 'done'
        })
        task_to_archive = resp.json()
        
        client.patch(f'/api/v1/tasks/{task_to_archive["id"]}', json={
            'status': 'archived'
        })
        
        # List tasks without filter - should exclude archived
        resp = client.get('/api/v1/tasks')
        assert resp.status_code == 200
        tasks = resp.json()
        
        task_ids = {task['id'] for task in tasks}
        assert regular_task['id'] in task_ids
        assert task_to_archive['id'] not in task_ids
        
        # List archived tasks specifically
        resp = client.get('/api/v1/tasks?status=archived')
        assert resp.status_code == 200
        archived_tasks = resp.json()
        
        archived_ids = {task['id'] for task in archived_tasks}
        assert task_to_archive['id'] in archived_ids
        assert regular_task['id'] not in archived_ids
        
        # Clean up
        client.delete(f'/api/v1/tasks/{regular_task["id"]}')
        client.delete(f'/api/v1/tasks/{task_to_archive["id"]}')


class TestGoalCadence:
    """Test goal cadence updates."""
    
    def test_create_goal_with_new_cadences(self):
        """Test creating goals with new cadence options."""
        cadences = ['annual', 'quarterly', 'weekly']
        
        for cadence in cadences:
            resp = client.post('/api/v1/goals', json={
                'title': f'Test {cadence} goal',
                'type': cadence
            })
            assert resp.status_code == 201
            goal = resp.json()
            assert goal['type'] == cadence
            
            # Clean up
            client.delete(f'/api/v1/goals/{goal["id"]}')
    
    def test_invalid_goal_cadence_rejected(self):
        """Test that invalid cadences like 'monthly' are rejected."""
        resp = client.post('/api/v1/goals', json={
            'title': 'Test goal with invalid cadence',
            'type': 'monthly'
        })
        # Should fail validation
        assert resp.status_code == 422


class TestTrelloImport:
    """Test Trello import functionality."""
    
    def test_import_trello_json_basic(self):
        """Test basic Trello JSON import."""
        # Sample Trello JSON structure
        trello_json = {
            "lists": [
                {
                    "name": "Backlog",
                    "cards": [
                        {
                            "name": "Important task from Trello",
                            "desc": "Task description",
                            "closed": False
                        }
                    ]
                },
                {
                    "name": "To Do",
                    "cards": [
                        {
                            "name": "This week task",
                            "desc": "Another task",
                            "closed": False
                        }
                    ]
                }
            ]
        }
        
        # Convert to JSON string and create file-like object
        json_content = json.dumps(trello_json)
        json_file = io.BytesIO(json_content.encode('utf-8'))
        
        # Make import request
        resp = client.post(
            '/api/v1/import/trello',
            files={'file': ('trello_export.json', json_file, 'application/json')}
        )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result['imported_tasks'] == 2
        assert len(result['task_ids']) == 2
        
        # Verify tasks were created
        for task_id in result['task_ids']:
            resp = client.get(f'/api/v1/tasks/{task_id}')
            assert resp.status_code == 200
            task = resp.json()
            assert task['title'] in ['Important task from Trello', 'This week task']
            
            # Clean up
            client.delete(f'/api/v1/tasks/{task_id}')
    
    def test_import_trello_csv_basic(self):
        """Test basic Trello CSV import."""
        csv_content = """Card Name,List,Description
Task from CSV,Backlog,Description here
Another CSV task,To Do,Another description"""
        
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        
        resp = client.post(
            '/api/v1/import/trello',
            files={'file': ('trello_export.csv', csv_file, 'text/csv')}
        )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result['imported_tasks'] == 2
        
        # Verify and clean up
        for task_id in result['task_ids']:
            resp = client.get(f'/api/v1/tasks/{task_id}')
            assert resp.status_code == 200
            client.delete(f'/api/v1/tasks/{task_id}')
    
    def test_import_unsupported_file_format(self):
        """Test that unsupported file formats are rejected."""
        text_file = io.BytesIO(b"Some random text content")
        
        resp = client.post(
            '/api/v1/import/trello',
            files={'file': ('document.txt', text_file, 'text/plain')}
        )
        
        assert resp.status_code == 400
        assert "Only JSON and CSV files are supported" in resp.json()['detail']


class TestIntegration:
    """Integration tests combining multiple features."""
    
    def test_full_workflow_with_new_features(self):
        """Test a complete workflow using the new features."""
        # Create a goal with new cadence
        goal_resp = client.post('/api/v1/goals', json={
            'title': 'Weekly sprint goal',
            'type': 'weekly'
        })
        assert goal_resp.status_code == 201
        goal = goal_resp.json()
        
        # Create task without status (should default to week)
        task_resp = client.post('/api/v1/tasks', json={
            'title': 'Sprint task'
        })
        assert task_resp.status_code == 201
        task = task_resp.json()
        assert task['status'] == 'week'
        
        # Complete the task
        client.patch(f'/api/v1/tasks/{task["id"]}', json={'status': 'done'})
        
        # Archive the task
        archived_resp = client.patch(f'/api/v1/tasks/{task["id"]}', json={'status': 'archived'})
        assert archived_resp.status_code == 200
        
        # Verify task doesn't appear in default list
        tasks_resp = client.get('/api/v1/tasks')
        task_ids = {t['id'] for t in tasks_resp.json()}
        assert task['id'] not in task_ids
        
        # But appears in archived list
        archived_resp = client.get('/api/v1/tasks?status=archived')
        archived_ids = {t['id'] for t in archived_resp.json()}
        assert task['id'] in archived_ids
        
        # Clean up
        client.delete(f'/api/v1/tasks/{task["id"]}')
        client.delete(f'/api/v1/goals/{goal["id"]}')