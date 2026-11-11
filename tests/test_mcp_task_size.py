"""Task-size patches through the real MCP transport and existing reporting flow."""
import asyncio

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from test_mcp_read import database, seed
from app.db import get_db
from app.main import create_app
from app.models import Task
from app.schemas import FIBONACCI_SIZES
from app.services.mcp_write import MCPWriteService
from app.services.tokens import TokenService


@pytest.mark.parametrize('size', sorted(FIBONACCI_SIZES))
def test_resize_accepts_the_existing_rest_and_ui_scale(database, size):
    db, _ = database
    task = MCPWriteService(db, 'a').create_task(title='Unsized')
    assert MCPWriteService(db, 'a').update_task(task['id'], size=size)['size'] == size


def test_bulk_task_size_is_already_supported(database):
    db, _ = database
    service = MCPWriteService(db, 'a')
    batch = {'tasks': [{'title': 'Sized capture', 'size': 13}]}
    preview = service.bulk_create(**batch)
    assert preview['tasks'][0]['size'] == 13 and db.query(Task).count() == 0
    result = service.bulk_create(**batch, dry_run=False)
    assert result['tasks'][0]['size'] == 13


def test_size_patches_and_insights_over_sdk_http(database):
    db, sessions = database
    seed(db)
    # A completed but unsized task is initially excluded from story-point totals.
    db.get(Task, 'atask').size = None
    db.commit()
    app = create_app()
    def provide_db():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = provide_db
    _, writer = TokenService(db).create('a', 'Size writer', ['read', 'write'])
    _, reader = TokenService(db).create('a', 'Size reader', ['read'])
    _, other = TokenService(db).create('b', 'Other writer', ['write'])

    async def run():
        async with app.router.lifespan_context(app):
            async def exercise(token, mode):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                    headers={'Authorization': 'Bearer '+token}) as client:
                    async with streamable_http_client('http://localhost:8000/mcp', http_client=client) as (read, send, _):
                        async with ClientSession(read, send) as session:
                            await session.initialize()
                            async def call(name, args):
                                result = await session.call_tool(name, args)
                                assert result.content == []
                                return result
                            if mode != 'writer':
                                rejected = await call('update_task', {'task_id': 'atask', 'size': 8})
                                assert rejected.isError
                                expected = 'forbidden' if mode == 'reader' else 'invalid_request'
                                assert rejected.structuredContent['error']['code'] == expected
                                return
                            tool = next(t for t in (await session.list_tools()).tools if t.name == 'update_task')
                            assert 'size' in tool.inputSchema['properties']
                            assert tool.inputSchema['required'] == ['task_id']
                            assert 'story points' in tool.description
                            window = {'from': '2026-10-19', 'to': '2026-10-25'}
                            before = await call('get_insights', window)
                            assert before.structuredContent['summary']['impact_score'] == 0
                            sized = await call('update_task', {'task_id': 'atask', 'size': 3})
                            assert not sized.isError and sized.structuredContent['size'] == 3
                            completed_at = sized.structuredContent['completed_at']
                            changed = await call('update_task', {'task_id': 'atask', 'size': 8})
                            assert changed.structuredContent['size'] == 8
                            assert changed.structuredContent['completed_at'] == completed_at
                            preserved = await call('update_task', {'task_id': 'atask', 'description': 'Keep size'})
                            assert preserved.structuredContent['size'] == 8
                            invalid = await call('update_task', {'task_id': 'atask', 'size': 4})
                            assert invalid.isError and invalid.structuredContent['error']['code'] == 'invalid_request'
                            insights = await call('get_insights', window)
                            assert insights.structuredContent['summary']['impact_score'] == 8
                            assert insights.structuredContent['breakdown']['total_impact'] == 8
                            cleared = await call('update_task', {'task_id': 'atask', 'size': None})
                            assert cleared.structuredContent['size'] is None
                            assert cleared.structuredContent['completed_at'] == completed_at
                            insights = await call('get_insights', window)
                            assert insights.structuredContent['summary']['impact_score'] == 0
            await exercise(reader, 'reader')
            await exercise(other, 'other')
            await exercise(writer, 'writer')
    asyncio.run(run())
    db.expire_all()
    assert db.get(Task, 'atask').size is None
    assert db.get(Task, 'btask').size == 3
