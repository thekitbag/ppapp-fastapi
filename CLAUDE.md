# Claude Code Assistant Notes

## MCP

- `app/mcp_server.py` serves eight read tools and five write tools at `/mcp`, using the official SDK's stateless Streamable HTTP transport. Its session manager runs in the parent application's lifespan.
- Authentication is PAT-only (`Authorization: Bearer et_pat_...`), never a browser cookie. Cookie-authenticated `/api/v1/tokens` endpoints and web Settings manage tokens. Plaintext is returned once; only SHA-256 hashes are stored.
- Read tools delegate to `MCPReadService`, scoped repositories, and existing goal/report/recommendation services. Never add direct database queries to the MCP adapter.
- Write tools delegate to `MCPWriteService` and existing task/goal services. `atomic(db)` makes nested service commits flush only, then commits once; failures roll back the entire operation. Standalone REST service calls still commit normally.
- `bulk_create` requires write scope even for previews and defaults to `dry_run=true`. The planner performs SELECTs only. Show the resolved preview to the user and obtain approval before committing the same batch with `dry_run=false`. Temporary goal keys and plan references support forward references. Revalidate at commit time; expose no delete tools.
- Tool results contain data once in `structuredContent`, with an empty `content` array. Return explicit `CallToolResult` objects so the SDK does not duplicate JSON as text. Clients must read `structuredContent`; Claude Code, Inspector and the Python SDK are verified.
- Patch factories preserve omitted fields separately from explicit nulls. Null clears nullable description/date/plan-reference fields; title and status cannot be null. Keep tag and goal-link changes inside the task update's transaction.
- `plan_ref` is nullable, case-sensitive and unique per user. Prefer it over IDs when referring to goals.
- `update_goal` accepts sparse `closed`, `archived` and nullable `parent` patches with write scope. Closing cascades to owned descendants; reopening clears only the selected goal's `closed_at`. Archiving is independent and affects only that goal. Resolve parent IDs/plan references within the user, lock the target and supplied parent, and apply all changes in one transaction. Quarterly goals require an annual parent, weekly goals require a quarterly parent, and annual goals have no parent. Legacy orphans can still be closed/archived without supplying a parent, or repaired by assigning a valid parent.
- On Windows use `.venv/Scripts/python.exe`; do not rewrite the Mac-compatible Makefile. Run `python -m pytest tests` in an activated environment. PostgreSQL migration tests require `MCP_TEST_DATABASE_URL` pointing to a **local** admin DB; they create/drop their own disposable database.
- Regenerate REST schemas with `python scripts/export_openapi.py`, then run `npm run generate:api` in the sibling frontend. Review generated diffs.
- For normal local startup: configure a development database and JWT secret, apply migrations, then `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Create a token in web Settings. See `docs/mcp-m1-handover.md` for connection commands and the existing fresh-PostgreSQL migration limitation.
- M2 and M2.1 have been merged. M2.2 is local on `feat/mcp-goal-lifecycle` in both repositories; see `docs/mcp-m2-2-handover.md`. Do not push, open a PR or deploy without explicit instruction. Take and verify a fresh backup before an approved deployment.

## Test Environment Setup
**IMPORTANT**: Always activate the virtual environment and use the Makefile for testing:
```bash
source env/bin/activate && make test
```
- The virtual environment is in `env/` (not `venv/`)
- The Makefile sets the correct `PYTHONPATH=/Users/markgray/projects/ppapp-fastapi`
- Direct pytest commands may fail due to missing environment setup

## Architecture (Updated Sept 2025)

**Current Architecture**: Clean service-based pattern with v1 API
- All endpoints are now under `/api/v1/` prefix
- Service layer in `/app/services/` handles business logic
- Controllers in `/app/api/v1/` are thin and use dependency injection
- Database access only through services, not direct in controllers

**Legacy Cleanup Completed**:
- ❌ Removed `/app/routers/` (legacy direct-DB access)
- ❌ Removed `/app/main_legacy.py` 
- ✅ All endpoints migrated to `/app/api/v1/` service pattern

**Current Endpoints**:
- `/api/v1/tasks` - Task CRUD with TaskService
- `/api/v1/projects` - Project CRUD with ProjectService  
- `/api/v1/goals` - Goals and key results with GoalService
- `/api/v1/health` - Health check
- `/api/v1/recommendations` - Task recommendations

**Service Pattern Example**:
```python
# Controller (thin)
@router.post("", response_model=TaskOut)
def create_task(
    payload: TaskCreate,
    task_service: TaskService = Depends(get_task_service)
):
    return task_service.create_task(payload)

# Service (business logic)
def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    return TaskService(db)
```

## Database Migrations
- Use Alembic for all schema changes
- Always test both upgrade AND downgrade functions
- Use `server_default=sa.text('CURRENT_TIMESTAMP')` not Python callables
- Drop indexes and tables in reverse order in downgrade()

## Goals & Key Results Implementation
- Many-to-many relationship: Task ↔ Goal via `task_goals` table
- `TaskGoal` junction table with optional `weight` field
- Goals have `key_results` (GoalKR table) with target/baseline values
- Backward compatibility: kept deprecated `goal_id` field on Task model
