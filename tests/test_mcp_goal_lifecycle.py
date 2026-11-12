import pytest
from pydantic import ValidationError as InputError
from test_mcp_read import database, seed
from app.models import Goal
from app.exceptions import ValidationError
from app.services.mcp_write import MCPWriteService


def test_goal_lifecycle_cascade_reopen_and_archive(database):
    db, _ = database
    seed(db)
    service = MCPWriteService(db, 'a')
    archived = service.update_goal('A1', archived=True)
    assert archived['is_archived'] and not archived['is_closed'] and archived['closed_at'] is None
    assert not db.get(Goal, 'aquarter').is_archived
    assert not db.get(Goal, 'aquarter').is_closed
    service.update_goal('A1', archived=False)
    closed = service.update_goal('A1', closed=True, archived=True)
    assert closed['is_closed'] and closed['closed_at'] and closed['is_archived']
    assert all(db.get(Goal, gid).is_closed for gid in ('aannual', 'aquarter', 'aweekly'))
    timestamp = closed['closed_at']
    assert service.update_goal('A1', closed=True)['closed_at'] == timestamp
    renamed = service.update_goal('A1', title='Renamed')
    assert renamed['is_closed'] and renamed['is_archived'] and renamed['closed_at'] == timestamp
    reopened = service.update_goal('A1', closed=False, archived=False)
    assert not reopened['is_closed'] and reopened['closed_at'] is None and not reopened['is_archived']
    assert db.get(Goal, 'aweekly').is_closed
    assert service.update_goal('W1', closed=False)['closed_at'] is None


def test_reparent_each_level_and_repair_legacy_orphans(database):
    db, _ = database
    seed(db)
    service = MCPWriteService(db, 'a')
    annual = service.create_goal(type='annual', title='New annual', plan_ref='A2')
    assert service.update_goal('Q1', parent='A2')['parent_goal_id'] == annual['id']
    quarter = service.create_goal(type='quarterly', title='New quarter', parent='A2')
    assert service.update_goal('W1', parent=quarter['id'])['parent_goal_id'] == quarter['id']
    assert service.update_goal('A2', parent=None)['parent_goal_id'] is None
    db.get(Goal, 'aquarter').parent_goal_id = None
    db.get(Goal, 'aweekly').parent_goal_id = None
    db.commit()
    assert service.update_goal('Q1', closed=True)['is_closed']
    assert service.update_goal('Q1', parent='A1')['parent_goal_id'] == 'aannual'
    assert service.update_goal('W1', parent='Q1')['parent_goal_id'] == 'aquarter'
    changed = service.update_goal('W1', status='at_risk')
    assert changed['parent_goal_id'] == 'aquarter'


@pytest.mark.parametrize('goal,parent', [('A1','Q1'), ('Q1','W1'), ('W1','A1'), ('Q1',None), ('W1',None), ('A1','A1'), ('Q1','Q1')])
def test_invalid_hierarchy_and_cycles(database, goal, parent):
    db, _ = database
    seed(db)
    before = {g.id: g.parent_goal_id for g in db.query(Goal)}
    with pytest.raises(ValidationError):
        MCPWriteService(db, 'a').update_goal(goal, parent=parent, title='Must roll back')
    assert {g.id: g.parent_goal_id for g in db.query(Goal)} == before


def test_cycle_with_legacy_untyped_goals_is_rejected(database):
    db, _ = database
    seed(db)
    for gid in ('aannual', 'aquarter', 'aweekly'):
        db.get(Goal, gid).type = None
    db.commit()
    with pytest.raises(ValidationError, match='cycle'):
        MCPWriteService(db, 'a').update_goal('A1', parent='W1')


@pytest.mark.parametrize('changes', [{'closed':None}, {'archived':None}, {'closed':'false'}, {'archived':1}])
def test_lifecycle_requires_real_booleans(database, changes):
    db, _ = database
    seed(db)
    with pytest.raises(InputError):
        MCPWriteService(db, 'a').update_goal('A1', **changes)


def test_goal_ownership_and_cascade_guard(database):
    db, _ = database
    seed(db)
    service = MCPWriteService(db, 'a')
    with pytest.raises(ValidationError):
        service.update_goal('bannual', closed=True)
    with pytest.raises(ValidationError):
        service.update_goal('Q1', parent='bannual')
    db.get(Goal, 'bquarter').parent_goal_id = 'aannual'
    db.commit()
    service.update_goal('A1', closed=True)
    assert not db.get(Goal, 'bquarter').is_closed


def test_late_failure_rolls_back_goal_fields_and_descendants(database, monkeypatch):
    db, _ = database
    seed(db)
    service = MCPWriteService(db, 'a')
    title = db.get(Goal, 'aquarter').title
    annual = service.create_goal(type='annual', title='New parent', plan_ref='A2')
    def fail(*args):
        raise RuntimeError('injected late failure')
    monkeypatch.setattr(service.goals, 'archive_goal', fail)
    with pytest.raises(RuntimeError):
        service.update_goal('Q1', title='Changed', parent=annual['id'], closed=True, archived=True)
    db.expire_all()
    assert db.get(Goal, 'aquarter').title == title
    assert db.get(Goal, 'aquarter').parent_goal_id == 'aannual'
    assert not db.get(Goal, 'aquarter').is_closed
    assert not db.get(Goal, 'aweekly').is_closed
