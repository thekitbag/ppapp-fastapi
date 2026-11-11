"""User-scoped read queries used by the MCP application service."""
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from app.models import Goal, GoalKR, Task, Tag, TaskGoal


class MCPReadRepository:
    def __init__(self, db, user_id):
        self.db, self.user_id = db, user_id

    def goals(self):
        return self.db.query(Goal).filter(Goal.user_id == self.user_id).order_by(
            Goal.priority.desc(), Goal.created_at, Goal.id).all()

    def key_results(self):
        return self.db.query(GoalKR).join(Goal).filter(
            GoalKR.user_id == self.user_id, Goal.user_id == self.user_id).all()

    def tasks(self, statuses=None, goal_id=None, tag=None, due_before=None,
              updated_since=None, limit=None):
        query = self.db.query(Task).options(selectinload(Task.tags), selectinload(Task.project)).filter(
            Task.user_id == self.user_id)
        if statuses is not None:
            query = query.filter(Task.status.in_(statuses))
        if goal_id:
            links = self.db.query(TaskGoal.task_id).join(Goal, Goal.id == TaskGoal.goal_id).filter(
                Goal.id == goal_id, Goal.user_id == self.user_id,
                or_(TaskGoal.user_id == self.user_id, TaskGoal.user_id.is_(None)))
            query = query.filter(or_(Task.goal_id == goal_id, Task.id.in_(links)))
        if tag:
            query = query.filter(Task.tags.any((Tag.user_id == self.user_id) & (Tag.name == tag)))
        if due_before:
            # Include either deadline when it falls before the exclusive cutoff.
            query = query.filter(or_(Task.hard_due_at < due_before, Task.soft_due_at < due_before))
        if updated_since:
            query = query.filter(Task.updated_at >= updated_since)
        query = query.order_by(Task.created_at, Task.id)
        return query.limit(limit).all() if limit is not None else query.all()

    def links(self):
        return self.db.query(TaskGoal).join(Task, Task.id == TaskGoal.task_id).join(
            Goal, Goal.id == TaskGoal.goal_id).filter(
            Task.user_id == self.user_id, Goal.user_id == self.user_id,
            or_(TaskGoal.user_id == self.user_id, TaskGoal.user_id.is_(None))).all()

    def tags(self):
        return self.db.query(Tag).filter(Tag.user_id == self.user_id).order_by(Tag.name, Tag.id).all()
