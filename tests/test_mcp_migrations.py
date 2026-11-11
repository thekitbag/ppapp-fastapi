"""New migrations against populated PostgreSQL; never target an existing database."""
import os
import uuid
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.db import Base
from app import models


@pytest.mark.skipif(not os.getenv('MCP_TEST_DATABASE_URL'), reason='Set MCP_TEST_DATABASE_URL to a local PostgreSQL admin database')
def test_postgres_upgrade_downgrade_and_uniqueness(monkeypatch):
    admin_url = sa.engine.make_url(os.environ['MCP_TEST_DATABASE_URL'])
    assert admin_url.host in ('localhost', '127.0.0.1'), 'Migration tests require local PostgreSQL'
    name = 'mcp_migration_' + uuid.uuid4().hex
    admin = sa.create_engine(admin_url, isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE {name}'))
    url = admin_url.set(database=name)
    engine = sa.create_engine(url)
    try:
        # Bootstrap the current schema because an older unrelated historical
        # migration cannot replay on PostgreSQL (dependent tasks primary key).
        Base.metadata.create_all(engine)
        monkeypatch.setenv('DATABASE_URL', url.render_as_string(hide_password=False))
        config = Config('alembic.ini')
        command.stamp(config, 'b12a7c04d002')
        command.downgrade(config, '20260228_report001')
        assert 'api_tokens' not in sa.inspect(engine).get_table_names()
        assert 'plan_ref' not in {c['name'] for c in sa.inspect(engine).get_columns('goals')}
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users(id,provider,provider_sub,email,created_at) VALUES ('a','google','a','a@example.com',CURRENT_TIMESTAMP), ('b','google','b','b@example.com',CURRENT_TIMESTAMP)"))
            conn.execute(sa.text("INSERT INTO goals(id,user_id,title,status,is_closed,is_archived,priority,created_at) VALUES ('old','a','Existing','on_target',false,false,0,CURRENT_TIMESTAMP)"))
        command.upgrade(config, 'head')
        with engine.begin() as conn:
            assert conn.scalar(sa.text("SELECT title FROM goals WHERE id='old'")) == 'Existing'
            assert conn.scalar(sa.text("SELECT plan_ref FROM goals WHERE id='old'")) is None
            conn.execute(sa.text("UPDATE goals SET plan_ref='A1' WHERE id='old'"))
            conn.execute(sa.text("INSERT INTO goals(id,user_id,title,plan_ref,status,is_closed,is_archived,priority,created_at) VALUES ('other','b','Other','A1','on_target',false,false,0,CURRENT_TIMESTAMP)"))
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO goals(id,user_id,title,plan_ref,status,is_closed,is_archived,priority,created_at) VALUES ('duplicate','a','Duplicate','A1','on_target',false,false,0,CURRENT_TIMESTAMP)"))
        command.downgrade(config, '20260228_report001')
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM goals')) == 2
        command.upgrade(config, 'head')
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE {name} WITH (FORCE)'))
        admin.dispose()
