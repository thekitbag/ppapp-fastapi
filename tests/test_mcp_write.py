import asyncio

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import event

from test_mcp_read import database, seed
from app.db import get_db
from app.main import create_app
from app.models import Task, Goal, Tag, TaskGoal, Project
from app.schemas import TaskCreate
from app.exceptions import ValidationError, ConflictError
from app.services.base import atomic
from app.services.goal import GoalService
from app.services.task import TaskService
from app.services.tokens import TokenService
from app.services.mcp_write import MCPWriteService


def counts(db):
    return tuple(db.query(model).count() for model in (Task, Goal, Tag, TaskGoal))


def week_batch():
    return dict(goals=[
        {'key':'q', 'type':'quarterly', 'title':'Quarter', 'plan_ref':'Q2', 'parent':'a'},
        {'key':'a', 'type':'annual', 'title':'Annual', 'plan_ref':'A2'},
        {'key':'w', 'type':'weekly', 'title':'Week', 'parent':'q', 'plan_ref':'W2'},
    ], tasks=[{'key':'capture', 'title':'Follow up', 'goals':['w'], 'tags':['delegated'], 'status':'week'}])


def test_create_and_update_goals_with_owned_references(database):
    db, _ = database
    seed(db)
    service = MCPWriteService(db, 'a')
    quarter = service.create_goal(type='quarterly', title='New quarter', parent='A1', plan_ref=' Q2 ')
    assert quarter['parent_goal_id'] == 'aannual' and quarter['plan_ref'] == 'Q2'
    weekly = service.create_goal(type='weekly', title='New week', parent=quarter['id'])
    updated = service.update_goal(weekly['id'], status='at_risk', plan_ref='W2', description='Keep this')
    assert updated['status'] == 'at_risk'
    assert service.update_goal('W2', description=None)['title'] == 'New week'
    assert service.update_goal('W2', plan_ref=None)['plan_ref'] is None
    with pytest.raises(ConflictError):
        service.update_goal(quarter['id'], plan_ref='A1')
    with pytest.raises(ValidationError):
        service.create_goal(type='weekly', title='Foreign parent', parent='bquarter')
    with pytest.raises(ValidationError):
        service.update_goal('bannual', title='Foreign edit')
    assert db.get(Goal, 'bannual').title == 'b annual'


def test_task_capture_and_partial_null_updates(database):
    db, _ = database
    seed(db)
    service = MCPWriteService(db, 'a')
    task = service.create_task(title=' Capture ', description='Keep', goals=['A1','aannual'],
                               tags=[' delegated ', 'delegated'], project='a project', size=3,
                               hard_due_at='2040-12-31T12:00:00Z')
    assert task['title'] == 'Capture' and task['status'] == 'backlog'
    assert task['tags'] == ['delegated'] and task['project']['id'] == 'aproject'
    assert len(task['goals']) == 1
    done = service.update_task(task['id'], status='done', description=None, hard_due_at=None,
                                add_tags=['reflection'], remove_tags=['delegated'],
                                add_goals=['W1'], remove_goals=['aannual'])
    assert done['completed_at'] and done['description'] is None and done['hard_due_at'] is None
    assert done['tags'] == ['reflection'] and done['goals'] == [{'id':'aweekly','plan_ref':'W1'}]
    assert service.update_task(task['id'], title='Renamed')['completed_at'] == done['completed_at']
    reopened = service.update_task(task['id'], status='week')
    assert reopened['completed_at'] is None and reopened['tags'] == ['reflection']
    assert service.create_task(title='Already done', status='done')['completed_at'] is not None


def test_update_removes_owned_legacy_links_and_preserves_other_users(database):
    db, _ = database
    seed(db)
    db.get(Task, 'aactive').goal_id = 'aannual'
    db.get(TaskGoal, 'alink').user_id = None
    db.commit()
    service = MCPWriteService(db, 'a')
    assert service.update_task('aactive', remove_goals=['A1'])['goals'] == []
    assert service.update_task('atask', remove_goals=['W1'])['goals'] == []
    before = counts(db)
    with pytest.raises(ValidationError):
        service.update_task('btask', description='Foreign edit')
    with pytest.raises(ValidationError):
        service.update_task('atask', add_goals=['bweekly'])
    with pytest.raises(ValidationError):
        service.create_task(title='Foreign project', project='bproject')
    assert counts(db) == before and db.get(Task, 'btask').description == 'b reflection notes'


def test_update_link_failure_rolls_back_task_and_tags(database, monkeypatch):
    db, _ = database
    seed(db)
    service = MCPWriteService(db, 'a')
    original = GoalService.link_tasks_to_goal
    def fail_after_link(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError('injected late failure')
    monkeypatch.setattr(GoalService, 'link_tasks_to_goal', fail_after_link)
    before = counts(db)
    with pytest.raises(RuntimeError):
        service.update_task('aactive', title='Must roll back', add_tags=['new tag'], add_goals=['W1'])
    db.expire_all()
    assert db.get(Task,'aactive').title == 'a active'
    assert counts(db) == before


def test_preview_is_resolved_stable_and_issues_no_dml(database):
    db, _ = database
    seed(db)
    service = MCPWriteService(db, 'a')
    writes=[]
    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in ('INSERT','UPDATE','DELETE'):
            writes.append(statement)
    event.listen(db.bind, 'before_cursor_execute', record)
    try:
        preview = service.bulk_create(**week_batch())
        assert preview == service.bulk_create(**week_batch())
    finally:
        event.remove(db.bind, 'before_cursor_execute', record)
    assert writes == []
    assert preview['valid'] and preview['dry_run'] and not preview['committed']
    assert preview['tags_to_create'] == ['delegated']
    assert preview['goals'][0]['parent']['key'] == 'a'
    assert preview['tasks'][0]['goals'][0]['key'] == 'w'


def test_bulk_commits_once_with_forward_references(database):
    db, _ = database
    seed(db)
    commits=[]
    event.listen(db, 'after_commit', lambda session: commits.append(True))
    batch=week_batch()
    batch['goals'][0]['parent']='A2'
    batch['tasks'][0]['goals']=['w','W2']
    result = MCPWriteService(db,'a').bulk_create(**batch, dry_run=False)
    assert result['committed'] and not result['dry_run'] and commits == [True]
    goals = {goal['key']:goal for goal in result['goals']}
    assert goals['q']['parent_goal_id'] == goals['a']['id']
    assert goals['w']['parent_goal_id'] == goals['q']['id']
    assert result['tasks'][0]['goals'] == [{'id':goals['w']['id'],'plan_ref':'W2'}]


@pytest.mark.parametrize('mutation', ['bad_reference','duplicate_ref','duplicate_key','cycle','foreign_parent','foreign_project'])
def test_invalid_batch_does_not_write_anything(database, mutation):
    db, _ = database
    seed(db)
    batch = week_batch()
    if mutation == 'bad_reference': batch['tasks'][0]['goals'] = ['missing']
    if mutation == 'duplicate_ref': batch['goals'][0]['plan_ref'] = 'A1'
    if mutation == 'duplicate_key': batch['tasks'][0]['key'] = 'a'
    if mutation == 'cycle': batch['goals'][1]['parent'] = 'w'
    if mutation == 'foreign_parent': batch['goals'][0]['parent'] = 'bannual'
    if mutation == 'foreign_project': batch['tasks'][0]['project'] = 'bproject'
    before = counts(db)
    service = MCPWriteService(db,'a')
    for dry_run in (True, False):
        result = service.bulk_create(**batch, dry_run=dry_run)
        assert not result['valid'] and not result['committed'] and result['errors']
        assert counts(db) == before


def test_bulk_late_failure_rolls_back_goals_tasks_tags_and_links(database, monkeypatch):
    db, _ = database
    seed(db)
    before = counts(db)
    batch=week_batch()
    batch['tasks'].append({'title':'Second task','tags':['another new tag'],'goals':['w']})
    original=MCPWriteService._create_task
    calls=[]
    def fail_after_second(self, *args):
        result=original(self,*args)
        calls.append(result)
        if len(calls)==2: raise RuntimeError('failure after all inserts')
        return result
    monkeypatch.setattr(MCPWriteService,'_create_task',fail_after_second)
    with pytest.raises(RuntimeError):
        MCPWriteService(db,'a').bulk_create(**batch,dry_run=False)
    assert len(calls)==2 and counts(db)==before


def test_nested_failure_cannot_be_swallowed_and_rest_still_commits(database):
    db, sessions = database
    with pytest.raises(RuntimeError):
        with atomic(db):
            TaskService(db).create_task(TaskCreate(title='Roll back'), 'a')
            try:
                with atomic(db): raise ValueError('nested error')
            except ValueError: pass
    assert db.query(Task).count()==0
    created,_=TaskService(db).create_task(TaskCreate(title='Standalone REST service'), 'a')
    with sessions() as other:
        assert other.get(Task,created.id) is not None


@pytest.mark.parametrize('arguments', [
    {'title':'Invalid size','size':4}, {'title':'Invalid tag','tags':[' ']},
    {'title':'Dates reversed','soft_due_at':'2040-02-01T00:00:00Z','hard_due_at':'2040-01-01T00:00:00Z'},
    {'title':' '},
])
def test_invalid_capture_never_creates_records(database,arguments):
    from pydantic import ValidationError as InputError
    db,_=database
    with pytest.raises((ValidationError,InputError)):
        MCPWriteService(db,'a').create_task(**arguments)
    assert counts(db)==(0,0,0,0)


def test_sparse_deadline_updates_validate_against_existing_values(database):
    db,_=database
    service=MCPWriteService(db,'a')
    task=service.create_task(title='Future',hard_due_at='2040-01-01T12:00:00+01:00')
    assert task['hard_due_at']=='2040-01-01T11:00:00Z'
    with pytest.raises(ValidationError):
        service.update_task(task['id'],soft_due_at='2040-02-01T12:00:00Z')
    assert service.read.task_results([task['id']])[0]['soft_due_at'] is None


def test_ambiguous_references_and_conflicting_patch_changes_are_rejected(database):
    from pydantic import ValidationError as InputError
    db,_=database
    seed(db)
    service=MCPWriteService(db,'a')
    service.create_goal(type='annual',title='Alias collision',plan_ref='aannual')
    db.add(Project(id='second-project',user_id='a',name='a project'))
    db.commit()
    before=counts(db)
    with pytest.raises(ValidationError,match='Ambiguous goal'):
        service.create_task(title='Wrong goal',goals=['aannual'])
    with pytest.raises(ValidationError,match='Ambiguous project'):
        service.create_task(title='Wrong project',project='a project')
    assert not service.bulk_create(tasks=[{'title':'Ambiguous','goals':['aannual']}],dry_run=False)['valid']
    for changes in [{'title':None},{'status':None},{'add_tags':[' same '],'remove_tags':['same']}]:
        with pytest.raises(InputError):
            service.update_task('aactive',**changes)
    with pytest.raises(ValidationError):
        service.update_task('aactive',add_goals=['A1'],remove_goals=['aannual'])
    assert counts(db)==before


@pytest.mark.parametrize('value',['false',0,None])
def test_bulk_commit_requires_an_explicit_boolean(database,value):
    db,_=database
    with pytest.raises(ValidationError):
        MCPWriteService(db,'a').bulk_create(**week_batch(),dry_run=value)
    assert counts(db)==(0,0,0,0)


def test_sdk_writes_scopes_sparse_updates_and_single_payload(database):
    db, sessions = database
    seed(db)
    app=create_app()
    def provide_db():
        with sessions() as session: yield session
    app.dependency_overrides[get_db]=provide_db
    _, secret=TokenService(db).create('a','Write SDK',['read','write'])
    _, read_only=TokenService(db).create('a','Read only',['read'])
    _, other=TokenService(db).create('b','Other writer',['write'])
    async def run():
        async with app.router.lifespan_context(app):
            async def exercise(token, mode):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),headers={'Authorization':'Bearer '+token}) as client:
                    async with streamable_http_client('http://localhost:8000/mcp',http_client=client) as (read,send,_):
                        async with ClientSession(read,send) as session:
                            await session.initialize()
                            tools=(await session.list_tools()).tools
                            assert len(tools)==13
                            patch=next(tool for tool in tools if tool.name=='update_task')
                            assert patch.inputSchema['required']==['task_id']
                            goal_patch=next(tool for tool in tools if tool.name=='update_goal')
                            assert goal_patch.inputSchema['required']==['goal']
                            assert goal_patch.inputSchema['properties']['closed']['type']=='boolean'
                            assert goal_patch.inputSchema['properties']['archived']['type']=='boolean'
                            assert 'null' in str(goal_patch.inputSchema['properties']['parent'])
                            async def call(name,args):
                                result=await session.call_tool(name,args)
                                assert result.content==[]
                                return result
                            if mode=='read':
                                for name,args in [('create_task',{'title':'Forbidden'}),('update_task',{'task_id':'aactive','title':'Forbidden'}),
                                    ('create_goal',{'type':'annual','title':'Forbidden'}),('update_goal',{'goal':'A1','closed':True,'archived':True,'parent':None}),
                                    ('bulk_create',{})]:
                                    result=await call(name,args)
                                    assert result.isError and result.structuredContent['error']['code']=='forbidden'
                                return
                            if mode=='foreign':
                                result=await call('update_goal',{'goal':'aannual','closed':True})
                                assert result.isError
                                result=await call('update_goal',{'goal':'bquarter','parent':'aannual'})
                                assert result.isError
                                result=await call('update_task',{'task_id':'aactive','description':'Foreign'})
                                assert result.isError
                                result=await call('bulk_create',{'tasks':[{'title':'Foreign link','goals':['aweekly']}],'dry_run':False})
                                assert result.isError and not result.structuredContent['committed']
                                return
                            created=await call('create_task',{'title':'SDK capture','description':'Keep','goals':['W1']})
                            assert not created.isError
                            tid=created.structuredContent['id']
                            for text in ['null','{"note":"literal JSON text"}']:
                                literal=await call('update_task',{'task_id':tid,'description':text})
                                assert literal.structuredContent['description']==text
                            await call('update_task',{'task_id':tid,'description':'Keep'})
                            changed=await call('update_task',{'task_id':tid,'status':'done'})
                            assert changed.structuredContent['description']=='Keep' and changed.structuredContent['completed_at']
                            cleared=await call('update_task',{'task_id':tid,'description':None})
                            assert cleared.structuredContent['description'] is None
                            goal=await call('create_goal',{'type':'annual','title':'SDK annual','plan_ref':'SDK','description':'Keep goal description','end_date':'2040-01-01T00:00:00Z'})
                            assert not goal.isError
                            goal=await call('update_goal',{'goal':'SDK','status':'at_risk'})
                            assert goal.structuredContent['title']=='SDK annual'
                            assert goal.structuredContent['description']=='Keep goal description'
                            assert goal.structuredContent['end_date']
                            goal=await call('update_goal',{'goal':'SDK','closed':True,'archived':True,'parent':None})
                            assert not goal.isError and goal.structuredContent['is_closed'] and goal.structuredContent['is_archived']
                            assert goal.structuredContent['closed_at'] and goal.structuredContent['parent_goal_id'] is None
                            goal=await call('update_goal',{'goal':'SDK','closed':False,'archived':False})
                            assert not goal.isError and not goal.structuredContent['is_closed'] and not goal.structuredContent['is_archived']
                            assert goal.structuredContent['closed_at'] is None
                            moved=await call('update_goal',{'goal':'Q1','parent':'SDK'})
                            assert not moved.isError and moved.structuredContent['parent_goal_id']==goal.structuredContent['id']
                            goal=await call('update_goal',{'goal':'SDK','plan_ref':None,'end_date':None,'description':None})
                            assert goal.structuredContent['plan_ref'] is None and goal.structuredContent['end_date'] is None
                            assert goal.structuredContent['description'] is None
                            before=counts(db)
                            preview=await call('bulk_create',week_batch())
                            assert preview.structuredContent['dry_run'] and counts(db)==before
                            committed=await call('bulk_create',{**week_batch(),'dry_run':False})
                            assert committed.structuredContent['committed']
            await exercise(read_only,'read')
            await exercise(other,'foreign')
            await exercise(secret,'write')
    asyncio.run(run())
