"""Read tools and PAT isolation, including the real SDK HTTP client."""
import asyncio
import hashlib
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import create_app
from app.models import User, ProviderEnum, ApiToken, Task, Goal, Tag, TaskGoal, GoalKR, Project
from app.schemas import GoalCreate, GoalUpdate
from app.services.goal import GoalService
from app.services.tokens import TokenService, require_scope
from app.services.mcp_read import MCPReadService, midnight
from app.mcp_server import RateLimiter
from app.exceptions import ConflictError, ValidationError


@pytest.fixture
def database():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        for uid in ['a', 'b']:
            db.add(User(id=uid, provider=ProviderEnum.google, provider_sub=uid, email=uid+'@example.com'))
        db.commit()
        yield db, sessions
    engine.dispose()


def seed(db):
    for uid in ['a', 'b']:
        db.add_all([
            Goal(id=uid+'annual', user_id=uid, title=uid+' annual', type='annual', plan_ref='A1'),
            Goal(id=uid+'quarter', user_id=uid, title=uid+' quarter', type='quarterly', parent_goal_id=uid+'annual', plan_ref='Q1'),
            Goal(id=uid+'weekly', user_id=uid, title=uid+' weekly', type='weekly', parent_goal_id=uid+'quarter',
                 end_date=datetime(2026, 10, 25, 12), plan_ref='W1'),
            Tag(id=uid+'tag', user_id=uid, name='reflection'),
            Project(id=uid+'project', user_id=uid, name=uid+' project'),
        ])
    db.flush()
    for uid in ['a', 'b']:
        task = Task(id=uid+'task', user_id=uid, title=uid+' secret title', description=uid+' reflection notes',
                    status='done', size=3, completed_at=datetime(2026, 10, 25, 12),
                    created_at=datetime(2026, 10, 24, 12), updated_at=datetime(2026, 10, 25, 12),
                    project_id=uid+'project', tags=[db.get(Tag,uid+'tag')])
        db.add(task)
        db.add(Task(id=uid+'active', user_id=uid, title=uid+' active', status='week',
                    hard_due_at=datetime(2026, 10, 25, 12)))
        db.add(Task(id=uid+'backlog', user_id=uid, title=uid+' backlog', status='backlog'))
        db.add(TaskGoal(id=uid+'link', task_id=uid+'task', goal_id=uid+'weekly', user_id=uid))
        db.add(GoalKR(id=uid+'kr', goal_id=uid+'weekly', user_id=uid, name='result', target_value=5))
    db.commit()


def test_pat_lifecycle_and_scope(database):
    db, _ = database
    svc = TokenService(db)
    row, secret = svc.create('a', 'Claude', ['read'])
    assert secret.startswith('et_pat_') and len(secret) >= 50
    assert row.token_hash == hashlib.sha256(secret.encode()).hexdigest()
    assert row.prefix == secret[:8]
    assert row.last_used_at is None
    identity = svc.authenticate('Bearer '+secret)
    assert identity['user_id'] == 'a' and row.last_used_at is not None
    require_scope(identity, 'read')
    with pytest.raises(HTTPException) as exc:
        require_scope(identity, 'write')
    assert exc.value.status_code == 403
    assert svc.list('b') == []
    for auth in [None, 'Bearer wrong', 'Basic '+secret]:
        with pytest.raises(HTTPException):
            svc.authenticate(auth)
    svc.revoke('a', row.id)
    svc.revoke('a', row.id)
    with pytest.raises(HTTPException):
        svc.authenticate('Bearer '+secret)


def test_plan_ref_roundtrip_uniqueness_and_normalization(database):
    db, _ = database
    svc = GoalService(db)
    goal = svc.create_goal(GoalCreate(title='Plan', type='annual', plan_ref=' A1 '), 'a')
    assert goal.plan_ref == 'A1'
    assert svc.get_goal_detail(goal.id, 'a').plan_ref == 'A1'
    assert svc.get_goals_tree('a')[0].plan_ref == 'A1'
    with pytest.raises(ConflictError):
        svc.create_goal(GoalCreate(title='Duplicate', type='annual', plan_ref='A1'), 'a')
    svc.create_goal(GoalCreate(title='Other account', type='annual', plan_ref='A1'), 'b')
    assert svc.update_goal(goal.id, 'a', GoalUpdate(plan_ref=' ').model_dump(exclude_unset=True)).plan_ref is None


def test_all_read_use_cases_and_isolation(database):
    db, _ = database
    seed(db)
    service = MCPReadService(db, 'a')
    goals = service.list_goals()['goals']
    assert len(goals) == 3
    weekly = next(g for g in goals if g['plan_ref'] == 'W1')
    assert weekly['done_task_count'] == 1 and weekly['parent_plan_ref'] == 'Q1'
    assert weekly['key_results'][0]['id'] == 'akr'
    assert service.get_goal_tree()['goals'][0]['children'][0]['children'][0]['plan_ref'] == 'W1'
    task = service.list_tasks(status='done', goal='W1', tag='reflection')['tasks'][0]
    assert task['goals'] == [{'id': 'aweekly', 'plan_ref': 'W1'}]
    assert task['project']['id'] == 'aproject'
    assert service.list_tags()['tags'][0]['task_count'] == 1
    week = service.get_week(datetime(2026, 10, 19).date())
    assert week['completed_tasks'][0]['id'] == 'atask'
    assert week['reflections'][0]['description'] == 'a reflection notes'
    assert not week['unfinished_snapshot']['historical']
    assert week['weekly_goals'][0]['plan_ref'] == 'W1'
    insights = service.get_insights(datetime(2026,10,19).date(), datetime(2026,10,25).date())
    assert insights['summary']['impact_score'] == 3
    assert insights['tag_counts'] == {'reflection': 1}
    for result in [service.recommend_next(), service.suggest_week()]:
        assert result['items']
        assert all(item['task']['id'].startswith('a') for item in result['items'])
    assert db.get(Task, 'abacklog').status.value == 'backlog'
    with pytest.raises(ValidationError):
        service.list_tasks(goal='bweekly')
    with pytest.raises(ValidationError):
        service.get_week(datetime(2026,10,20).date())
    assert len(service.list_tasks(limit=1)['tasks']) == 1
    assert service.list_tasks(limit=1)['truncated']
    assert service.list_tasks(updated_since=datetime(2100,1,1,tzinfo=timezone.utc))['tasks'] == []
    assert service.list_tasks(due_before=datetime(2026,10,26).date())['tasks'][0]['id'] == 'aactive'


def test_dst_week_is_calendar_based():
    from datetime import date
    assert (midnight(date(2026,10,26))-midnight(date(2026,10,19))).total_seconds() == 169*3600


def test_rate_limit_window_and_independent_tokens():
    clock = [0.0]
    limiter = RateLimiter(limit=2, clock=lambda: clock[0])
    assert limiter.allow('a') and limiter.allow('a') and not limiter.allow('a')
    assert limiter.allow('b')
    clock[0] = 60
    assert limiter.allow('a')


def test_token_rest_requires_cookie_and_owns_resources(database, monkeypatch):
    import jwt
    from app.api.v1.auth import get_current_user_dep
    from app.core import settings
    db, sessions = database
    app = create_app()
    def provide_db():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = provide_db
    app.dependency_overrides.pop(get_current_user_dep, None)
    monkeypatch.setattr(settings, 'jwt_secret', 'test-secret-with-at-least-32-bytes')
    def cookie(uid):
        return jwt.encode(dict(user_id=uid, email=uid+'@example.com', name=uid, provider='google'), settings.jwt_secret, algorithm='HS256')
    with TestClient(app) as client:
        assert client.get('/api/v1/tokens').status_code == 401
        _, pat = TokenService(db).create('a', 'Cannot mint with PAT', ['read','write'])
        assert client.post('/api/v1/tokens', headers={'Authorization':'Bearer '+pat}, json={'name':'No','scopes':['read']}).status_code == 401
        client.cookies.set('ppapp_session',cookie('a'))
        created = client.post('/api/v1/tokens', json={'name':'Claude','scopes':['read']})
        assert created.status_code == 201
        assert created.headers['cache-control'] == 'no-store'
        body = created.json()
        assert 'token' in body and 'token_hash' not in body
        assert all('token' not in row and 'token_hash' not in row for row in client.get('/api/v1/tokens').json())
        assert client.post('/api/v1/tokens', json={'name':'','scopes':[]}).status_code == 422
        assert client.post('/api/v1/tokens', headers={'Origin':'https://untrusted.example'}, json={'name':'CSRF','scopes':['read']}).status_code == 403
        client.cookies.set('ppapp_session',cookie('b'))
        assert client.get('/api/v1/tokens').json() == []
        assert client.delete('/api/v1/tokens/'+body['id']).status_code == 404
        client.cookies.set('ppapp_session',cookie('a'))
        assert client.delete('/api/v1/tokens/'+body['id']).status_code == 204


def test_real_sdk_http_client_and_cookie_rejection(database):
    db, sessions = database
    seed(db)
    app = create_app()
    def provide_db():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = provide_db
    row, secret = TokenService(db).create('a', 'SDK', ['read'])
    _, write_only = TokenService(db).create('b', 'Write only', ['write'])
    _, other_read = TokenService(db).create('b', 'Other reader', ['read'])

    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost:8000') as client:
                assert (await client.post('/mcp', cookies={'ppapp_session':'cookie'})).status_code == 401
                assert (await client.post('/mcp', headers={'Authorization':'Bearer wrong'})).status_code == 401
                auth = {'Authorization':'Bearer '+secret}
                assert (await client.post('/mcp', headers={**auth,'Host':'untrusted.example'}, json={})).status_code == 421
                assert (await client.post('/mcp', headers={**auth,'Origin':'https://untrusted.example'}, json={})).status_code == 403
            async def exercise(token, write=False):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                    headers={'Authorization':'Bearer '+token}) as client:
                    async with streamable_http_client('http://localhost:8000/mcp', http_client=client) as (read, send, _):
                        async with ClientSession(read, send) as session:
                            await session.initialize()
                            tools = (await session.list_tools()).tools
                            assert len(tools) == 8
                            insights = next(t for t in tools if t.name == 'get_insights')
                            assert set(insights.inputSchema['properties']) == {'from','to'}
                            if write:
                                result = await session.call_tool('list_goals', {})
                                assert result.isError
                                assert result.structuredContent['error']['code'] == 'forbidden'
                            else:
                                for name, arguments in [('list_goals',{}),('get_goal_tree',{}),
                                    ('list_tasks',{'status':'done','goal':'W1'}),
                                    ('get_week',{'week_commencing':'2026-10-19'}),
                                    ('get_insights',{'from':'2026-10-19','to':'2026-10-25'}),
                                    ('list_tags',{}),('recommend_next',{}),('suggest_week',{})]:
                                    result = await session.call_tool(name, arguments)
                                    assert not result.isError, result
                                    assert 'error' not in result.structuredContent, result
                                    assert 'b secret title' not in str(result)
            await exercise(secret)
            await exercise(write_only, write=True)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), headers={'Authorization':'Bearer '+other_read}) as client:
                async with streamable_http_client('http://localhost:8000/mcp', http_client=client) as (read, send, _):
                    async with ClientSession(read, send) as session:
                        await session.initialize()
                        result = await session.call_tool('list_goals', {})
                        assert all(goal['id'].startswith('b') for goal in result.structuredContent['goals'])
                        result = await session.call_tool('list_tasks', {'goal':'aweekly'})
                        assert result.isError and result.structuredContent['error']['code'] == 'invalid_request'
            TokenService(db).revoke('a', row.id)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
                assert (await client.post('http://localhost:8000/mcp', headers={'Authorization':'Bearer '+secret})).status_code == 401
    asyncio.run(run())
