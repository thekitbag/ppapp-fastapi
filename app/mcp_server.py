"""PAT-only, stateless MCP adapter. Read and write tools share owned services and atomic operations."""
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
from mcp.types import ToolAnnotations, CallToolResult
from pydantic import Field, PlainValidator, ValidationError as InputValidationError
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.db import get_db
from app.exceptions import AppException
from app.services.tokens import TokenService, require_scope
from app.services.mcp_read import MCPReadService
from app.services.mcp_write import MCPWriteService
from app.mcp_schemas import BatchGoal, BatchTask
from app.schemas import GoalType, GoalStatus, Status

logger = logging.getLogger(__name__)
identity_context = ContextVar('mcp_identity', default=None)
WRITE_TOOLS = {'create_task', 'update_task', 'create_goal', 'update_goal', 'bulk_create'}
UNSET = object()


def omitted():
    return UNSET


def nullable_text(value):
    if value is not None and not isinstance(value, str):
        raise ValueError('Expected text or null')
    return value


# Keep the underlying annotation `str`: the SDK otherwise JSON-parses strings
# in Optional[str] fields (e.g. the literal "null" becomes None). The validator
# and its input schema still accept actual JSON null without parsing text.
NullableText = Annotated[str, PlainValidator(nullable_text, json_schema_input_type=str | None)]
# Pydantic factories preserve omission separately from an explicit JSON null.
# The SDK passes every validated argument, so ordinary None defaults lose that distinction.
PatchText = Annotated[str, PlainValidator(nullable_text, json_schema_input_type=str | None), Field(default_factory=omitted)]
PatchDate = Annotated[datetime | None, Field(default_factory=omitted)]
PatchStatus = Annotated[Status | None, Field(default_factory=omitted)]
PatchSize = Annotated[int | None, Field(default_factory=omitted)]
PatchGoalStatus = Annotated[GoalStatus | None, Field(default_factory=omitted)]
PatchBool = Annotated[bool, Field(default_factory=omitted, strict=True)]
PatchList = Annotated[list[str], Field(default_factory=omitted)]


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
        instructions='Eigentask goals cascade annual → quarterly → weekly. Prefer plan_ref over IDs. '
                     'Read tools require read scope; writes and bulk previews require write scope. '
                     'Before bulk_create commit, call dry_run=true and show the resolved preview to the user for approval. '
                     'After approval, submit the same batch with dry_run=false. No delete tools are available.',
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=['api.eigentask.co.uk', 'localhost:*', '127.0.0.1:*'],
            allowed_origins=['https://api.eigentask.co.uk', 'http://localhost:*', 'http://127.0.0.1:*']))
    # SDK validation/transport error logs can include user-supplied arguments.
    sdk_logger = logging.getLogger('mcp')
    sdk_logger.handlers = [logging.NullHandler()]
    sdk_logger.propagate = False
    limiter = RateLimiter()

    def failure(code, message, details=None):
        error = {'code': code, 'message': message}
        if details:
            error['details'] = details
        return CallToolResult(isError=True, content=[], structuredContent={'error': error})

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
            write = name in WRITE_TOOLS
            require_scope(identity, 'write' if write else 'read')
            if not limiter.allow(identity['token_id']):
                outcome = 'rate_limited'
                return failure('rate_limited', '120 tool calls per minute exceeded; retry after 60 seconds')
            service = MCPWriteService if write else MCPReadService
            data = await run_in_threadpool(with_db, lambda db: jsonable_encoder(
                getattr(service(db, identity['user_id']), name)(**arguments)))
            invalid = name == 'bulk_create' and not data['valid']
            if invalid:
                outcome = 'invalid_request'
            return CallToolResult(content=[], structuredContent=data, isError=invalid)
        except HTTPException as exc:
            outcome = 'forbidden'
            return failure('forbidden', exc.detail)
        except InputValidationError as exc:
            outcome = 'invalid_request'
            details = [{'path': '.'.join(map(str, item['loc'])), 'message': item['msg']}
                       for item in exc.errors(include_input=False, include_url=False)]
            return failure('invalid_request', 'Invalid tool arguments', details)
        except IntegrityError:
            outcome = 'conflict'
            return failure('conflict', 'A duplicate or concurrent reference change prevented this operation; refresh before retrying')
        except AppException as exc:
            outcome = 'invalid_request'
            return failure('invalid_request', exc.message)
        except Exception:
            outcome = 'failed'
            return failure('internal_error', 'Eigentask could not complete this operation. Read current state before retrying a write.')
        finally:
            logger.info('mcp tool=%s user_id=%s duration_ms=%.1f outcome=%s',
                        name, identity['user_id'], (time.monotonic() - started) * 1000, outcome)

    common = (' Goals cascade annual → quarterly → weekly; prefer plan_ref to goal ID. '
              'Task statuses: backlog=unscheduled, week=this week, today=today, doing=in progress, '
              'waiting=blocked, done=completed, archived=hidden.')

    def tool(description, write=False):
        scope = ' Write scope required.' if write else ' Read scope required.'
        return mcp.tool(description=description + common + scope,
                        annotations=ToolAnnotations(readOnlyHint=not write, destructiveHint=write, openWorldHint=False))

    @tool('List goals with direct task counts, key results and parent plan references. Closed and archived goals are excluded by default.')
    async def list_goals(type: GoalType | None = None, include_closed: bool = False, include_archived: bool = False) -> dict[str, Any]:
        return await call('list_goals', type=type, include_closed=include_closed, include_archived=include_archived)

    @tool('Read the open, unarchived annual/quarterly/weekly goal hierarchy with plan references.')
    async def get_goal_tree() -> dict[str, Any]:
        return await call('get_goal_tree')

    @tool('List tasks, filtered before limiting. goal accepts ID or plan_ref; tag is an exact name. '
          'due_before is an exclusive Europe/London date cutoff for either deadline; updated_since is an inclusive ISO timestamp. '
          'Default statuses are all active statuses. Results use stable creation/ID ordering; truncated indicates more matches.')
    async def list_tasks(status: Status | list[Status] | None = None, goal: NullableText = None,
                         tag: NullableText = None, due_before: date | None = None,
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

    @tool('Create a task, defaulting to backlog. goals accepts IDs or plan_refs; tags are names created if missing. '
          'project accepts an owned ID or unique exact name. Size is story points: 1, 2, 3, 5, 8, 13 or 21. '
          'Returns the same task shape as list_tasks.', write=True)
    async def create_task(title: str, description: NullableText = None, goals: list[str] | None = None,
                          tags: list[str] | None = None, status: Status = 'backlog',
                          soft_due_at: datetime | None = None, hard_due_at: datetime | None = None,
                          size: int | None = None, project: NullableText = None) -> dict[str, Any]:
        return await call('create_task', title=title, description=description, goals=goals or [],
                          tags=tags or [], status=status, soft_due_at=soft_due_at, hard_due_at=hard_due_at,
                          size=size, project=project)

    @tool('Partially update an owned task and its tag/goal links atomically. Omitted fields are unchanged; '
          'null clears description, due dates or size. Size is story points: 1, 2, 3, 5, 8, 13 or 21. '
          'add_goals/remove_goals accept IDs or plan_refs. '
          'status=done sets completed_at through the existing task service; other statuses clear it.', write=True)
    async def update_task(task_id: str, title: PatchText, description: PatchText, status: PatchStatus,
                          size: PatchSize,
                          add_tags: PatchList, remove_tags: PatchList, add_goals: PatchList, remove_goals: PatchList,
                          soft_due_at: PatchDate, hard_due_at: PatchDate) -> dict[str, Any]:
        values = dict(title=title, description=description, status=status, size=size, add_tags=add_tags,
                      remove_tags=remove_tags, add_goals=add_goals, remove_goals=remove_goals,
                      soft_due_at=soft_due_at, hard_due_at=hard_due_at)
        changes = {key: value for key, value in values.items() if value is not UNSET}
        return await call('update_task', task_id=task_id, **changes)

    @tool('Create a goal. Annual goals have no parent; quarterly goals require an annual parent and weekly goals '
          'require a quarterly parent. parent accepts ID or plan_ref. plan_ref must be unique for your account.', write=True)
    async def create_goal(type: GoalType, title: str, parent: NullableText = None,
                          end_date: datetime | None = None, plan_ref: NullableText = None,
                          description: NullableText = None) -> dict[str, Any]:
        return await call('create_goal', type=type, title=title, parent=parent, end_date=end_date,
                          plan_ref=plan_ref, description=description)

    @tool('Partially update a goal selected by ID or plan_ref. Omitted fields stay unchanged; null clears end_date, '
          'description or plan_ref. closed=true closes this goal and descendants and sets closed_at; false reopens only '
          'this goal and clears closed_at. archived independently archives/unarchives this goal. parent accepts an owned '
          'goal ID or plan_ref: weekly under quarterly, quarterly under annual, annual without a parent (null). '
          'Rejects cycles and foreign goals. All changes are atomic. status is on_target, at_risk or off_target. '
          'Rejects duplicate plan_ref.', write=True)
    async def update_goal(goal: str, title: PatchText, status: PatchGoalStatus,
                          end_date: PatchDate, plan_ref: PatchText, description: PatchText,
                          closed: PatchBool, archived: PatchBool, parent: PatchText) -> dict[str, Any]:
        values = dict(title=title, status=status, end_date=end_date, plan_ref=plan_ref, description=description,
                      closed=closed, archived=archived, parent=parent)
        changes = {key: value for key, value in values.items() if value is not UNSET}
        return await call('update_goal', goal=goal, **changes)

    @tool('Create goals and tasks together. ALWAYS call with dry_run=true first (the default), show the fully resolved '
          'preview and errors to the user, and obtain approval before resubmitting the same batch with dry_run=false. '
          'Dry runs write no tasks, goals, tags or links. Commit writes everything or nothing in one transaction. '
          'Items may carry a unique temporary key; goal parent and task goals can reference a batch goal by key or plan_ref. '
          'Forward references are supported; duplicates, ambiguous references, cycles and foreign-user references are rejected. '
          'At most 1000 items per batch. A changed database is revalidated at commit time.', write=True)
    async def bulk_create(goals: Annotated[list[BatchGoal], Field(default_factory=list)],
                          tasks: Annotated[list[BatchTask], Field(default_factory=list)],
                          dry_run: Annotated[bool, Field(strict=True)] = True) -> dict[str, Any]:
        return await call('bulk_create', goals=goals, tasks=tasks, dry_run=dry_run)

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
