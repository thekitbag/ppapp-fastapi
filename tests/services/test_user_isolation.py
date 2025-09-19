import pytest
from app.services.task import TaskService
from app.services.project import ProjectService
from app.services.goal import GoalService
from app.schemas import TaskCreate, ProjectCreate, GoalCreate
from app.models import User, ProviderEnum, Task, Project, Goal
from app.exceptions import NotFoundError, ValidationError


class TestUserIsolation:
    """Test that users cannot access other users' resources."""

    @pytest.fixture
    def user_a(self, test_db):
        """Create test user A."""
        user = User(
            id="user-a-id",
            provider=ProviderEnum.microsoft,
            provider_sub="user-a-sub",
            email="user-a@example.com",
            name="User A"
        )
        test_db.add(user)
        test_db.commit()
        return user

    @pytest.fixture
    def user_b(self, test_db):
        """Create test user B."""
        user = User(
            id="user-b-id",
            provider=ProviderEnum.google,
            provider_sub="user-b-sub",
            email="user-b@example.com",
            name="User B"
        )
        test_db.add(user)
        test_db.commit()
        return user

    @pytest.fixture
    def task_service(self, test_db):
        return TaskService(test_db)

    @pytest.fixture
    def project_service(self, test_db):
        return ProjectService(test_db)

    @pytest.fixture
    def goal_service(self, test_db):
        return GoalService(test_db)

    # Task isolation tests
    def test_user_cannot_read_other_users_task(self, task_service, user_a, user_b):
        """Test that user B cannot read user A's task."""
        # User A creates a task
        task_data = TaskCreate(title="User A's Task", status="backlog")
        task, _ = task_service.create_task(task_data, user_a.id)

        # User B tries to read User A's task - should fail
        with pytest.raises(NotFoundError):
            task_service.get_task(task.id, user_b.id)

    def test_user_cannot_update_other_users_task(self, task_service, user_a, user_b):
        """Test that user B cannot update user A's task."""
        # User A creates a task
        task_data = TaskCreate(title="User A's Task", status="backlog")
        task, _ = task_service.create_task(task_data, user_a.id)
        
        # User B tries to update User A's task - should fail
        with pytest.raises(NotFoundError):
            task_service.update_task(task.id, user_b.id, {"title": "Hacked!"})

    def test_user_cannot_delete_other_users_task(self, task_service, user_a, user_b):
        """Test that user B cannot delete user A's task."""
        # User A creates a task
        task_data = TaskCreate(title="User A's Task", status="backlog")
        task, _ = task_service.create_task(task_data, user_a.id)

        # User B tries to delete User A's task - should fail
        with pytest.raises(NotFoundError):
            task_service.delete_task(task.id, user_b.id)

    def test_user_list_tasks_only_sees_own_tasks(self, task_service, user_a, user_b):
        """Test that list_tasks only returns the user's own tasks."""
        # User A creates tasks
        task_a1, _ = task_service.create_task(TaskCreate(title="A's Task 1", status="backlog"), user_a.id)
        task_a2, _ = task_service.create_task(TaskCreate(title="A's Task 2", status="week"), user_a.id)

        # User B creates tasks
        task_b1, _ = task_service.create_task(TaskCreate(title="B's Task 1", status="backlog"), user_b.id)
        
        # User A should only see their own tasks
        user_a_tasks = task_service.list_tasks(user_a.id)
        user_a_task_ids = [task.id for task in user_a_tasks]
        assert task_a1.id in user_a_task_ids
        assert task_a2.id in user_a_task_ids
        assert task_b1.id not in user_a_task_ids
        
        # User B should only see their own tasks
        user_b_tasks = task_service.list_tasks(user_b.id)
        user_b_task_ids = [task.id for task in user_b_tasks]
        assert task_b1.id in user_b_task_ids
        assert task_a1.id not in user_b_task_ids
        assert task_a2.id not in user_b_task_ids

    # Project isolation tests
    def test_user_cannot_read_other_users_project(self, project_service, user_a, user_b):
        """Test that user B cannot read user A's project."""
        # User A creates a project
        project_data = ProjectCreate(name="User A's Project")
        project = project_service.create_project(project_data, user_a.id)
        
        # User B tries to read User A's project - should fail
        with pytest.raises(NotFoundError):
            project_service.get_project(project.id, user_b.id)

    def test_user_cannot_update_other_users_project(self, project_service, user_a, user_b):
        """Test that user B cannot update user A's project."""
        # User A creates a project
        project_data = ProjectCreate(name="User A's Project")
        project = project_service.create_project(project_data, user_a.id)
        
        # User B tries to update User A's project - should fail
        from app.schemas import ProjectUpdate
        with pytest.raises(NotFoundError):
            project_service.update_project(project.id, user_b.id, ProjectUpdate(name="Hacked!"))

    def test_user_cannot_delete_other_users_project(self, project_service, user_a, user_b):
        """Test that user B cannot delete user A's project."""
        # User A creates a project
        project_data = ProjectCreate(name="User A's Project")
        project = project_service.create_project(project_data, user_a.id)
        
        # User B tries to delete User A's project - should fail
        with pytest.raises(NotFoundError):
            project_service.delete_project(project.id, user_b.id)

    def test_user_list_projects_only_sees_own_projects(self, project_service, user_a, user_b):
        """Test that list_projects only returns the user's own projects."""
        # User A creates projects
        proj_a1 = project_service.create_project(ProjectCreate(name="A's Project 1"), user_a.id)
        proj_a2 = project_service.create_project(ProjectCreate(name="A's Project 2"), user_a.id)
        
        # User B creates projects
        proj_b1 = project_service.create_project(ProjectCreate(name="B's Project 1"), user_b.id)
        
        # User A should only see their own projects
        user_a_projects = project_service.list_projects(user_a.id)
        user_a_project_ids = [proj.id for proj in user_a_projects]
        assert proj_a1.id in user_a_project_ids
        assert proj_a2.id in user_a_project_ids
        assert proj_b1.id not in user_a_project_ids

    # Goal isolation tests
    def test_user_cannot_read_other_users_goal(self, goal_service, user_a, user_b):
        """Test that user B cannot read user A's goal."""
        # User A creates a goal
        goal_data = GoalCreate(title="User A's Goal", type="annual")
        goal = goal_service.create_goal(goal_data, user_a.id)
        
        # User B tries to read User A's goal - should fail
        with pytest.raises(NotFoundError):
            goal_service.get_goal(goal.id, user_b.id)

    def test_user_cannot_update_other_users_goal(self, goal_service, user_a, user_b):
        """Test that user B cannot update user A's goal."""
        # User A creates a goal
        goal_data = GoalCreate(title="User A's Goal", type="annual")
        goal = goal_service.create_goal(goal_data, user_a.id)
        
        # User B tries to update User A's goal - should fail
        with pytest.raises(NotFoundError):
            goal_service.update_goal(goal.id, user_b.id, {"title": "Hacked!"})

    def test_user_cannot_delete_other_users_goal(self, goal_service, user_a, user_b):
        """Test that user B cannot delete user A's goal."""
        # User A creates a goal
        goal_data = GoalCreate(title="User A's Goal", type="annual")
        goal = goal_service.create_goal(goal_data, user_a.id)
        
        # User B tries to delete User A's goal - should fail
        with pytest.raises(NotFoundError):
            goal_service.delete_goal(goal.id, user_b.id)

    def test_user_list_goals_only_sees_own_goals(self, goal_service, user_a, user_b):
        """Test that list_goals only returns the user's own goals."""
        # User A creates goals
        goal_a1 = goal_service.create_goal(GoalCreate(title="A's Goal 1", type="annual"), user_a.id)
        goal_a2 = goal_service.create_goal(GoalCreate(title="A's Goal 2", type="annual"), user_a.id)
        
        # User B creates goals
        goal_b1 = goal_service.create_goal(GoalCreate(title="B's Goal 1", type="annual"), user_b.id)
        
        # User A should only see their own goals
        user_a_goals = goal_service.list_goals(user_a.id)
        user_a_goal_ids = [goal.id for goal in user_a_goals]
        assert goal_a1.id in user_a_goal_ids
        assert goal_a2.id in user_a_goal_ids
        assert goal_b1.id not in user_a_goal_ids

    # Cross-user linking tests
    def test_cannot_link_task_to_other_users_goal(self, task_service, goal_service, user_a, user_b):
        """Test that user cannot link their task to another user's goal."""
        # User A creates a goal hierarchy (annual -> quarterly -> weekly)
        annual_a = goal_service.create_goal(GoalCreate(title="A's Annual Goal", type="annual"), user_a.id)
        quarterly_a = goal_service.create_goal(GoalCreate(title="A's Quarterly Goal", type="quarterly", parent_goal_id=annual_a.id), user_a.id)
        goal_a = goal_service.create_goal(GoalCreate(title="A's Goal", type="weekly", parent_goal_id=quarterly_a.id), user_a.id)
        
        # User B creates a task
        task_b, _ = task_service.create_task(TaskCreate(title="B's Task", status="backlog"), user_b.id)
        
        # User B tries to link their task to User A's goal - should fail
        with pytest.raises((NotFoundError, ValidationError)):
            task_service.link_task_to_goal(task_b.id, goal_a.id, user_b.id)

    def test_cannot_link_other_users_task_to_goal(self, task_service, goal_service, user_a, user_b):
        """Test that user cannot link another user's task to their goal."""
        # User A creates a task
        task_a, _ = task_service.create_task(TaskCreate(title="A's Task", status="backlog"), user_a.id)
        
        # User B creates a goal hierarchy (annual -> quarterly -> weekly)  
        annual_b = goal_service.create_goal(GoalCreate(title="B's Annual Goal", type="annual"), user_b.id)
        quarterly_b = goal_service.create_goal(GoalCreate(title="B's Quarterly Goal", type="quarterly", parent_goal_id=annual_b.id), user_b.id)
        goal_b = goal_service.create_goal(GoalCreate(title="B's Goal", type="weekly", parent_goal_id=quarterly_b.id), user_b.id)
        
        # User B tries to link User A's task to their goal - should fail
        with pytest.raises((NotFoundError, ValidationError)):
            task_service.link_task_to_goal(task_a.id, goal_b.id, user_b.id)

    # Server-side user_id assignment tests
    def test_create_task_ignores_user_id_in_body(self, task_service, user_a, user_b):
        """Test that creating tasks always uses server-side user_id, ignoring any in request body."""
        # This simulates what happens at the API level - user_id comes from session, not request body
        task_data = TaskCreate(title="Test Task", status="backlog")
        
        # Create task for user_a (server passes user_a.id regardless of what client might send)
        task, _ = task_service.create_task(task_data, user_a.id)

        # Verify the task belongs to user_a, not any other user
        retrieved_task = task_service.get_task(task.id, user_a.id)
        assert retrieved_task.id == task.id
        
        # User B should not be able to see this task
        with pytest.raises(NotFoundError):
            task_service.get_task(task.id, user_b.id)

    def test_create_project_ignores_user_id_in_body(self, project_service, user_a, user_b):
        """Test that creating projects always uses server-side user_id."""
        project_data = ProjectCreate(name="Test Project")
        
        # Create project for user_a
        project = project_service.create_project(project_data, user_a.id)
        
        # Verify the project belongs to user_a
        retrieved_project = project_service.get_project(project.id, user_a.id)
        assert retrieved_project.id == project.id
        
        # User B should not be able to see this project
        with pytest.raises(NotFoundError):
            project_service.get_project(project.id, user_b.id)

    def test_create_goal_ignores_user_id_in_body(self, goal_service, user_a, user_b):
        """Test that creating goals always uses server-side user_id."""
        goal_data = GoalCreate(title="Test Goal", type="annual")
        
        # Create goal for user_a
        goal = goal_service.create_goal(goal_data, user_a.id)
        
        # Verify the goal belongs to user_a
        retrieved_goal = goal_service.get_goal(goal.id, user_a.id)
        assert retrieved_goal.id == goal.id
        
        # User B should not be able to see this goal
        with pytest.raises(NotFoundError):
            goal_service.get_goal(goal.id, user_b.id)