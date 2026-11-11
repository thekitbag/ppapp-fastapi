"""PAT-only, stateless MCP adapter. Milestone 1 exposes read tools only."""
import inspect
import logging
import time
from collections import deque
from contextvars import ContextVar
from datetime import date, datetime
from threading import Lock
from typing import Annotated, Literal, Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations, CallToolResult, TextContent
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.db import get_db
from app.exceptions import AppException
from app.services.tokens import TokenService, require_scope
from app.services.mcp_read import MCPReadService
from app.schemas import GoalType, Status

logger = logging.getLogger(__name__)
identity_context = ContextVar('mcp_identity', default=None)


class RateLimiter:
    def __init__(self, limit=120, clock=time.monotonic):
        self.limit, self.clock = limit, clock
        self.windows = {}
        self.lock = Lock()

    def allow(self, token_id):
        now = self.clock()
        with self.lock:
            self.windows = {key: values for key, values in self.windows.items() if values and values[-1] > now - 60}
            window = self.windows.setdefault(token_id, deque())
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= self.limit:
                return False
            window.append(now)
            return True


def create_mcp(owner):
    mcp = FastMCP('Eigentask', stateless_http=True, json_response=True,
        instructions='Read-only Eigentask tools. Goals cascade annual → quarterly → weekly. '
                     'Prefer plan_ref over opaque goal IDs. No write tools are available in milestone 1.',
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=['api.eigentask.co.uk', 'localhost:*', '127.0.0.1:*'],
            allowed_origins=['https://api.eigentask.co.uk', 'http://localhost:*', 'http://127.0.0.1:*']))
    # SDK validation/transport error logs can include user-supplied arguments.
    sdk_logger = logging.getLogger('mcp')
    sdk_logger.handlers = [logging.NullHandler()]
    sdk_logger.propagate = False
    limiter = RateLimiter()

    def failure(code, message):
        return CallToolResult(isError=True,
            content=[TextContent(type='text', text=message)],
            structuredContent={'error': {'code': code, 'message': message}})

    def with_db(callback):
        provider = owner.dependency_overrides.get(get_db, get_db)
        generator = provider()
        db = next(generator)
        try:
            return callback(db)
        finally:
            generator.close()

    async def call(name, **arguments):
        identity = identity_context.get()
        if identity is None:
            return failure('unauthenticated', 'Personal access token required')
        started = time.monotonic()
        outcome = 'ok'
        try:
            require_scope(identity, 'read')
            if not limiter.allow(identity['token_id']):
                outcome = 'rate_limited'
                return failure('rate_limited', '120 tool calls per minute exceeded; retry after 60 seconds')
            return await run_in_threadpool(with_db, lambda db: jsonable_encoder(
                getattr(MCPReadService(db, identity['user_id']), name)(**arguments)))
        except HTTPException as exc:
            outcome = 'forbidden'
            return failure('forbidden', exc.detail)
        except AppException as exc:
            outcome = 'invalid_request'
            return failure('invalid_request', exc.message)
        except Exception:
            outcome = 'failed'
            return failure('internal_error', 'Eigentask could not complete this read; try again')
        finally:
            logger.info('mcp tool=%s user_id=%s duration_ms=%.1f outcome=%s',
                        name, identity['user_id'], (time.monotonic() - started) * 1000, outcome)

    common = (' Goals cascade annual → quarterly → weekly; prefer plan_ref to goal ID. '
              'Task statuses: backlog=unscheduled, week=this week, today=today, doing=in progress, '
              'waiting=blocked, done=completed, archived=hidden. Read scope required.')

    def tool(description):
        return mcp.tool(description=description + common,
                        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))

    @tool('List goals with direct task counts, key results and parent plan references. Closed and archived goals are excluded by default.')
    async def list_goals(type: GoalType | None = None, include_closed: bool = False, include_archived: bool = False) -> dict[str, Any]:
        return await call('list_goals', type=type, include_closed=include_closed, include_archived=include_archived)

    @tool('Read the open, unarchived annual/quarterly/weekly goal hierarchy with plan references.')
    async def get_goal_tree() -> dict[str, Any]:
        return await call('get_goal_tree')

    @tool('List tasks, filtered before limiting. goal accepts ID or plan_ref; tag is an exact name. '
          'due_before is an exclusive Europe/London date cutoff for either deadline; updated_since is an inclusive ISO timestamp. '
          'Default statuses are all active statuses. Results use stable creation/ID ordering; truncated indicates more matches.')
    async def list_tasks(status: Status | list[Status] | None = None, goal: str | None = None,
                         tag: str | None = None, due_before: date | None = None,
                         updated_since: datetime | None = None,
                         limit: Annotated[int, Field(ge=1, le=1000)] = 200) -> dict[str, Any]:
        return await call('list_tasks', status=status, goal=goal, tag=tag, due_before=due_before,
                          updated_since=updated_since, limit=limit)

    @tool('Review a Monday-starting Europe/London week: weekly goals ending in it, completed tasks, '
          'and reflection-tagged tasks created in it (including descriptions). Unfinished tasks are a CURRENT snapshot, '
          'not a reconstruction of historical slippage.')
    async def get_week(week_commencing: date) -> dict[str, Any]:
        return await call('get_week', week_commencing=week_commencing)

    # The SDK forwards aliases as keyword arguments. A signature adapter preserves
    # the public "from" argument without exposing a Python-only "from_" spelling.
    def insight_signature(from_: Annotated[date, Field(alias='from')], to: date) -> dict[str, Any]:
        pass

    async def get_insights(**arguments) -> dict[str, Any]:
        return await call('get_insights', from_date=arguments['from'], to_date=arguments['to'])

    get_insights.__signature__ = inspect.signature(insight_signature)
    tool('Report completed STORY POINTS, not hours or tracked time, for inclusive from/to dates in Europe/London. '
         'Wraps existing summary and goal breakdown calculations: unsized tasks contribute no points; tag counts include them.')(get_insights)

    @tool('List all owned tags (labels), including unused tags, with counts of owned tasks across all statuses.')
    async def list_tags() -> dict[str, Any]:
        return await call('list_tags')

    @tool('Recommend next tasks using the existing ranking flow. time_window is available minutes; window is the deprecated input. '
          'This reads recommendations and changes no tasks.')
    async def recommend_next(energy: Literal['low', 'medium', 'high'] | None = None,
                             time_window: Literal[15, 30, 60, 120, 240] | None = None,
                             limit: Annotated[int, Field(ge=1, le=1000)] = 5, window: int = 30) -> dict[str, Any]:
        return await call('recommend_next', energy=energy, time_window=time_window, limit=limit, window=window)

    @tool('Suggest backlog tasks for the week using the existing scoring flow. Returns suggestions only; does not promote or create tasks.')
    async def suggest_week(limit: Annotated[int, Field(ge=1, le=1000)] = 5) -> dict[str, Any]:
        return await call('suggest_week', limit=limit)

    class PATMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope['type'] != 'http':
                return await self.app(scope, receive, send)
            authorization = Headers(scope=scope).get('authorization')
            try:
                identity = await run_in_threadpool(with_db, lambda db: TokenService(db).authenticate(authorization))
            except HTTPException as exc:
                return await JSONResponse({'error': exc.detail}, status_code=exc.status_code,
                                           headers=exc.headers)(scope, receive, send)
            marker = identity_context.set(identity)
            try:
                await self.app(scope, receive, send)
            finally:
                identity_context.reset(marker)

    transport = mcp.streamable_http_app()
    return mcp, PATMiddleware(transport)
