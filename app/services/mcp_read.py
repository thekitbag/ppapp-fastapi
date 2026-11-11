"""Read-only MCP use cases. No writes or transaction composition live here."""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from app.exceptions import ValidationError
from app.repositories.mcp_read import MCPReadRepository
from app.services.goal import GoalService
from app.services.reporting import ReportingService
from app.services.recommendation_service import RecommendationService
from app.services.recommendation_engine import get_recommendation_engine
from app.schemas import KROut, NextRecommendationQuery
from app.core import settings

LONDON = ZoneInfo('Europe/London')
ACTIVE = ['backlog', 'week', 'today', 'doing', 'waiting']


def utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return utc(value).isoformat().replace('+00:00', 'Z') if value else None


def midnight(value):
    return datetime.combine(value, time.min, LONDON).astimezone(timezone.utc)


class MCPReadService:
    def __init__(self, db, user_id):
        self.db, self.user_id = db, user_id
        self.repo = MCPReadRepository(db, user_id)

    def _graph(self):
        goals = {g.id: g for g in self.repo.goals()}
        links = {}
        for link in self.repo.links():
            links.setdefault(link.task_id, set()).add(link.goal_id)
        return goals, links

    def resolve_goal(self, reference):
        matches = [g for g in self.repo.goals() if g.id == reference or g.plan_ref == reference]
        if len(matches) > 1:
            raise ValidationError('Ambiguous goal reference; supply a unique goal id or plan_ref')
        if not matches:
            raise ValidationError(f"Goal reference '{reference}' not found")
        return matches[0].id

    def _task(self, task, goals, links):
        ids = links.get(task.id, set()) | ({task.goal_id} if task.goal_id else set())
        project = task.project if task.project and task.project.user_id == self.user_id else None
        return dict(id=task.id, title=task.title, description=task.description,
                    status=task.status.value, size=task.size,
                    hard_due_at=iso(task.hard_due_at), soft_due_at=iso(task.soft_due_at),
                    completed_at=iso(task.completed_at), created_at=iso(task.created_at),
                    updated_at=iso(task.updated_at),
                    tags=sorted(t.name for t in task.tags if t.user_id == self.user_id),
                    goals=[dict(id=gid, plan_ref=goals[gid].plan_ref) for gid in sorted(ids) if gid in goals],
                    project=dict(id=project.id, name=project.name) if project else None)

    def list_goals(self, type=None, include_closed=False, include_archived=False):
        goals, links = self._graph()
        counts = {gid: {'open_task_count': 0, 'done_task_count': 0} for gid in goals}
        for task in self.repo.tasks():
            ids = links.get(task.id, set()) | ({task.goal_id} if task.goal_id else set())
            for gid in ids & goals.keys():
                if task.status.value != 'archived':
                    counts[gid]['done_task_count' if task.status.value == 'done' else 'open_task_count'] += 1
        krs = {}
        for kr in self.repo.key_results():
            krs.setdefault(kr.goal_id, []).append(KROut.model_validate(kr).model_dump(mode='json'))
        return {'goals': [dict(
            id=g.id, plan_ref=g.plan_ref, title=g.title, type=g.type.value if g.type else None,
            parent_id=g.parent_goal_id if g.parent_goal_id in goals else None,
            parent_plan_ref=goals[g.parent_goal_id].plan_ref if g.parent_goal_id in goals else None,
            end_date=iso(g.end_date), status=g.status.value, priority=g.priority,
            is_closed=g.is_closed, is_archived=g.is_archived,
            key_results=krs.get(g.id, []), **counts[g.id],
        ) for g in goals.values() if (not type or (g.type and g.type.value == type))
            and (include_closed or not g.is_closed) and (include_archived or not g.is_archived)]}

    def get_goal_tree(self):
        tree = GoalService(self.db).get_goals_tree(self.user_id)
        return {'goals': [g.model_dump(mode='json') for g in tree]}

    def list_tasks(self, status=None, goal=None, tag=None, due_before=None, updated_since=None, limit=200):
        statuses = [status] if isinstance(status, str) else status
        goal_id = self.resolve_goal(goal) if goal else None
        cutoff = midnight(due_before) if due_before else None
        tasks = self.repo.tasks(ACTIVE if statuses is None else statuses, goal_id, tag,
                                cutoff, utc(updated_since), limit + 1)
        goals, links = self._graph()
        return {'tasks': [self._task(t, goals, links) for t in tasks[:limit]],
                'limit': limit, 'truncated': len(tasks) > limit}

    def get_week(self, week_commencing):
        if week_commencing.weekday() != 0:
            raise ValidationError('week_commencing must be a Monday')
        start, end = midnight(week_commencing), midnight(week_commencing + timedelta(days=7))
        goals, links = self._graph()
        tasks = self.repo.tasks()
        render = lambda t: self._task(t, goals, links)
        return dict(week_commencing=week_commencing.isoformat(), timezone='Europe/London',
            weekly_goals=[g for g in self.list_goals(include_closed=True)['goals']
                if g['type'] == 'weekly' and g['end_date'] and start <= utc(datetime.fromisoformat(g['end_date'])) < end],
            completed_tasks=[render(t) for t in tasks if t.completed_at and start <= utc(t.completed_at) < end],
            unfinished_snapshot={'as_of': iso(datetime.now(timezone.utc)), 'historical': False,
                'description': 'Current unfinished week/today/doing tasks; not historical slippage.',
                'tasks': [render(t) for t in tasks if t.status.value in ['week', 'today', 'doing']]},
            reflections=[render(t) for t in tasks if start <= utc(t.created_at) < end
                         and any(tag.name == 'reflection' and tag.user_id == self.user_id for tag in t.tags)])

    def get_insights(self, from_date, to_date):
        if to_date < from_date:
            raise ValidationError('to must be on or after from')
        start, end = midnight(from_date), midnight(to_date + timedelta(days=1))
        # Existing reports use inclusive endpoints; preserve their calculations.
        inclusive_end = end - timedelta(microseconds=1)
        reports = ReportingService(self.db)
        counts = {}
        for task in self.repo.tasks():
            if task.completed_at and start <= utc(task.completed_at) < end:
                for tag in task.tags:
                    if tag.user_id == self.user_id:
                        counts[tag.name] = counts.get(tag.name, 0) + 1
        return dict(measure='completed_story_points', timezone='Europe/London',
            summary=reports.summary_report(self.user_id, start, inclusive_end).model_dump(mode='json'),
            breakdown=reports.breakdown_report(self.user_id, start, inclusive_end).model_dump(mode='json'),
            tag_counts=counts)

    def list_tags(self):
        counts = {}
        for task in self.repo.tasks():
            for tag in task.tags:
                if tag.user_id == self.user_id:
                    counts[tag.id] = counts.get(tag.id, 0) + 1
        return {'tags': [dict(id=t.id, name=t.name, task_count=counts.get(t.id, 0)) for t in self.repo.tags()]}

    def recommend_next(self, energy=None, time_window=None, limit=5, window=30):
        query = NextRecommendationQuery(energy=energy, time_window=time_window, limit=limit, window=window)
        return RecommendationService(self.db).next(self.user_id, query,
            get_recommendation_engine(settings.use_llm_prioritization)).model_dump(mode='json')

    def suggest_week(self, limit=5):
        return RecommendationService(self.db).suggest_week(self.user_id, limit).model_dump(mode='json')
