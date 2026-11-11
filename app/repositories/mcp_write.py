"""Owned reference lookup and task link adjustments for composed writes."""
from sqlalchemy import or_
from app.models import Goal, Project, Task, TaskGoal
from app.exceptions import ValidationError


class MCPWriteRepository:
    def __init__(self, db, user_id):
        self.db, self.user_id = db, user_id

    def resolve_project(self, reference):
        if reference is None:
            return None
        matches = self.db.query(Project).filter(Project.user_id == self.user_id,
            or_(Project.id == reference, Project.name == reference)).all()
        if not matches:
            raise ValidationError(f"Project reference '{reference}' not found")
        if len(matches) > 1:
            raise ValidationError('Ambiguous project reference; supply a unique project ID')
        return matches[0].id

    def task(self, task_id):
        task = self.db.query(Task).filter(Task.id == task_id, Task.user_id == self.user_id).populate_existing().with_for_update().first()
        if task is None:
            raise ValidationError(f"Task '{task_id}' not found")
        return task

    def remove_goal_links(self, task, goal_ids):
        # Include old unowned junction rows only when both endpoint records are
        # owned. Other users' rows can never be selected or deleted.
        links = self.db.query(TaskGoal).join(Goal, Goal.id == TaskGoal.goal_id).filter(
            TaskGoal.task_id == task.id, TaskGoal.goal_id.in_(goal_ids),
            Goal.user_id == self.user_id,
            or_(TaskGoal.user_id == self.user_id, TaskGoal.user_id.is_(None))).all()
        for link in links:
            self.db.delete(link)
        if task.goal_id in goal_ids:
            task.goal_id = None

    def existing_goal_ids(self, task):
        ids = {gid for (gid,) in self.db.query(TaskGoal.goal_id).join(Goal, Goal.id == TaskGoal.goal_id).filter(
            TaskGoal.task_id == task.id, Goal.user_id == self.user_id,
            or_(TaskGoal.user_id == self.user_id, TaskGoal.user_id.is_(None))).all()}
        if task.goal_id:
            ids.add(task.goal_id)
        return ids
