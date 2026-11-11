"""Verify actual PostgreSQL visibility and rollback, not just SQLite behavior."""
import os
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from test_mcp_write import week_batch
from app.db import Base
from app.models import User, ProviderEnum, Task, Goal, Tag, TaskGoal
from app.services.mcp_write import MCPWriteService

pytestmark = pytest.mark.skipif(not os.getenv('MCP_TEST_DATABASE_URL'), reason='Local PostgreSQL admin database required')


@pytest.fixture
def pg_sessions():
    url = sa.engine.make_url(os.environ['MCP_TEST_DATABASE_URL'])
    assert url.host in ('localhost', '127.0.0.1'), 'Only local disposable databases are permitted'
    name='mcp_writes_'+uuid.uuid4().hex
    admin=sa.create_engine(url,isolation_level='AUTOCOMMIT')
    with admin.connect() as conn: conn.execute(sa.text(f'CREATE DATABASE {name}'))
    engine=sa.create_engine(url.set(database=name))
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,autoflush=False)
    with sessions() as db:
        db.add(User(id='a',provider=ProviderEnum.google,provider_sub='a',email='a@example.com'))
        db.commit()
    try: yield sessions
    finally:
        engine.dispose()
        with admin.connect() as conn: conn.execute(sa.text(f'DROP DATABASE {name} WITH (FORCE)'))
        admin.dispose()


def count_rows(sessions):
    with sessions() as db:
        return tuple(db.query(model).count() for model in (Task,Goal,Tag,TaskGoal))


def test_other_connections_see_no_partial_batch_and_exactly_one_commit(pg_sessions,monkeypatch):
    original=MCPWriteService._create_task
    def observed(self,*args):
        result=original(self,*args)
        assert count_rows(pg_sessions)==(0,0,0,0)
        return result
    monkeypatch.setattr(MCPWriteService,'_create_task',observed)
    with pg_sessions() as db:
        commits=[]
        sa.event.listen(db,'after_commit',lambda session: commits.append(True))
        result=MCPWriteService(db,'a').bulk_create(**week_batch(),dry_run=False)
        assert result['committed'] and commits==[True]
    assert count_rows(pg_sessions)==(1,3,1,1)


def test_late_postgres_failure_rolls_back_every_table(pg_sessions,monkeypatch):
    original=MCPWriteService._create_task
    def failed(self,*args):
        original(self,*args)
        raise RuntimeError('after all inserts')
    monkeypatch.setattr(MCPWriteService,'_create_task',failed)
    with pg_sessions() as db, pytest.raises(RuntimeError):
        MCPWriteService(db,'a').bulk_create(**week_batch(),dry_run=False)
    assert count_rows(pg_sessions)==(0,0,0,0)


def test_postgres_due_dates_null_clearing_and_omission(pg_sessions):
    with pg_sessions() as db:
        service=MCPWriteService(db,'a')
        task=service.create_task(title='TZ capture',description='Keep',hard_due_at='2040-01-01T12:00:00+01:00')
        assert task['hard_due_at']=='2040-01-01T11:00:00Z'
        changed=service.update_task(task['id'],status='done')
        assert changed['description']=='Keep' and changed['hard_due_at']==task['hard_due_at']
        cleared=service.update_task(task['id'],description=None,hard_due_at=None)
        assert cleared['description'] is None and cleared['hard_due_at'] is None
        assert cleared['completed_at']==changed['completed_at']


def test_commit_revalidates_a_preview_after_database_changes(pg_sessions):
    with pg_sessions() as db:
        assert MCPWriteService(db,'a').bulk_create(**week_batch())['valid']
    with pg_sessions() as concurrent:
        MCPWriteService(concurrent,'a').create_goal(type='annual',title='Concurrent capture',plan_ref='A2')
    with pg_sessions() as db:
        result=MCPWriteService(db,'a').bulk_create(**week_batch(),dry_run=False)
        assert not result['valid'] and not result['committed']
    assert count_rows(pg_sessions)==(0,1,0,0)
