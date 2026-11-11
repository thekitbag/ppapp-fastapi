"""Shared recommendation orchestration for REST and other application adapters."""
from app import models, schemas
from app.repositories import TaskRepository
from app.services.base import BaseService
from app.services.recommendations import suggest_week
from app.services.recommendation_engine import RecommendationContext


class RecommendationService(BaseService):
    def _candidates(self, user_id, statuses):
        return self.db.query(models.Task).filter(
            models.Task.user_id == user_id, models.Task.status.in_(statuses)
        ).all()

    def _response(self, tasks, ranked):
        by_id = {task.id: out for task, out in zip(
            tasks, TaskRepository(self.db).to_schema_batch(tasks)
        )}
        return schemas.RecommendationResponse(items=[
            schemas.RecommendationItem(task=by_id[r.task.id], score=r.score,
                                      factors=r.factors, why=r.why)
            for r in ranked
        ])

    def next(self, user_id, query, engine):
        tasks = self._candidates(user_id, ['backlog', 'doing', 'today', 'week'])
        ranked = engine.recommend(RecommendationContext(
            tasks=tasks, db=self.db, energy=query.energy,
            time_window=query.time_window, limit=query.limit,
        ))
        return self._response(tasks, ranked)

    def suggest_week(self, user_id, limit=5):
        tasks = self._candidates(user_id, ['backlog'])
        return self._response(tasks, suggest_week(tasks, db=self.db, limit=limit))
