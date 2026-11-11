# MCP milestone 1 handover

## Baseline and prerequisite commits

Baseline before changes: Python 3.11 backend **361 passed**; frontend **328 passed, 8 skipped**. Frontend build and TypeScript checks passed. No pre-existing test failures. The initial frontend setup/test overlap was discarded and rerun sequentially.

Dependency changes: Pydantic 2.12.5 / core 2.41.5, PyJWT 2.10.1, Uvicorn 0.38.0; uvloop is excluded on Windows. FastAPI 0.111.0, Starlette 0.37.2 and AnyIO 4.10.0 stay pinned.

| Repository | Commit | Change | Full suites after prerequisite |
| --- | --- | --- | --- |
| Backend | `6a52630` | Runtime dependency upgrades | Backend 361 passed; frontend 328 passed, 8 skipped |
| Backend | `eb90811` | Shared recommendation orchestration | Backend 361 passed; frontend 328 passed, 8 skipped |
| Backend | `340c7af` | Content/credential/exception log redaction | Backend 363 passed; frontend 328 passed, 8 skipped |
| Backend | `24098fa` | PAT lifecycle and goal references | Included in final M1 verification |
| Backend | `29387c6` | Eight stateless HTTP read tools and integration tests | Included in final M1 verification |
| Frontend | `4b0c04e` | Regenerated pre-MCP API types | Types and build passed |
| Frontend | `07e54b6` | Settings, goal forms, regenerated M1 types | Included in final M1 verification |

Both repositories use `feat/mcp-server`. The original untracked `docs/mcp-server-brief.md` was preserved and not committed.

## Final automated verification (11 November 2026)

- Backend: **371 passed** on Python **3.11.18** and **3.13.14**, including PostgreSQL migration checks.
- Frontend: **333 passed, 8 skipped**; TypeScript and production build passed.
- The official Python SDK's in-process Streamable HTTP client exercised all eight tools, the exact `from`/`to` insights schema, cookie rejection, revoked/incorrect tokens, write-only scope rejection, host/origin checks and cross-user access attempts.
- PostgreSQL: both new migrations upgraded, downgraded and upgraded again against populated isolated databases; old rows survived, nullable references worked, and database uniqueness rejected duplicates while allowing the same reference in different users.
- Fresh SQLite migration replay from base to head passed.
- MCP Inspector **2.13.0** CLI listed exactly eight tools and successfully called `list_goals` against the running local API. Inspector dependencies are isolated under `.venv/inspector`, outside application dependencies.

### Existing PostgreSQL migration limitation

Fresh PostgreSQL replay fails in existing revision `81f80f37840f` because it tries to drop `tasks_pkey` while `task_tags_task_id_fkey` depends on it. This predates M1. Historical migrations were not rewritten. New-migration tests bootstrap the current model schema in a disposable database, stamp the new head, downgrade to `20260228_report001`, then exercise upgrade/downgrade with existing rows. A separate repair is needed before relying on a fresh PostgreSQL install. No production database was accessed during M1 implementation; the later deployment preparation below used read-only connection checks.

## Generated contract diffs

The initial checked-in schema/types were stale. Regeneration caught up nine existing routes: goal archive, close, priority, reopen, reorder and unarchive, plus reports breakdown, goal progress and summary. Existing goal, task and reporting fields/types were also refreshed. Those changes are generated catch-up, not new REST behavior.

The dependency-only schema change is `RecommendationItem.factors.additionalProperties = true`; its existing unrestricted dictionary behavior is unchanged.

M1 adds `/api/v1/tokens` and `/api/v1/tokens/{token_id}`, the `TokenCreate`, `TokenCreated` and `TokenOut` schemas, and `plan_ref` on `GoalCreate`, `GoalDetail`, `GoalNode`, `GoalOut` and `GoalUpdate`. MCP is a separate protocol route and is not represented as REST operations in OpenAPI.

Regenerate with `python scripts/export_openapi.py` in the backend, then `npm run generate:api` in the frontend. Both generated files are committed.

## What reads mean

- Tools: `list_goals`, `get_goal_tree`, `list_tasks`, `get_week`, `get_insights`, `list_tags`, `recommend_next`, `suggest_week`.
- `get_insights` measures **completed story points**, not hours. It preserves the existing reports' attribution rules. Unsized tasks add no points but do count toward completion-window tag counts.
- Weeks use Europe/London Monday midnight through the following Monday midnight, including daylight-saving changes. Reflections are selected by creation date. The unfinished section is explicitly a current snapshot, not historical slippage.
- `due_before` excludes the supplied local calendar date; either hard or soft deadline may match. `updated_since` is inclusive. Naive stored timestamps are treated as UTC.
- Task lists default to active statuses, stable creation/ID order, a limit of 200, and explicit truncation metadata. Goal counts are direct linked-task counts and exclude archived tasks. Tag counts include all task statuses.
- Read tools require `read`; a `write`-only token cannot read. M1 exposes no MCP writes. Recommendation tools only return suggestions.

## Local connection

An isolated acceptance API is running at `http://localhost:8000/mcp`, using `.venv/mcp-local.sqlite3`, with a read-only PAT. This contains local test data, not your production tasks. Its client configuration is `.venv/mcp-local.json`; treat it as a credential file and keep it untracked.

The `eigentask-local` server has already been registered in your user-level Claude configuration (`C:\Users\MarkGray\.claude.json`). After Mark signed in, Claude Code successfully invoked all eight read tools once against the running HTTP API: `list_goals`, `get_goal_tree`, `list_tasks`, `get_week` (Monday 2026-11-09), `get_insights` (2026-11-09 through 2026-11-11), `list_tags`, `recommend_next` and `suggest_week`. All eight returned successful tool results; Claude reported no errors or permission denials. Empty results were expected in this isolated database. The SDK and Inspector checks also passed. The local acceptance transcript is kept under ignored `.venv/claude-connection-check.jsonl`.

For a normal development API with your chosen local database: install `requirements.txt`, configure `DATABASE_URL` and `JWT_SECRET`, apply Alembic migrations, and run `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Run `npm run dev` in the frontend and create a read token in Settings. Windows interpreters are `.venv/Scripts/python.exe` (3.13) and `.venv311/Scripts/python.exe` (3.11); the shared Makefile is unchanged.

Connection command for a newly created local token:

```powershell
claude mcp add --transport http --scope user eigentask-local http://localhost:8000/mcp --header "Authorization: Bearer <your-local-token>"
```

After an explicitly approved production deployment, create a separate production token in Settings and connect with:

```powershell
claude mcp add --transport http --scope user eigentask https://api.eigentask.co.uk/mcp --header "Authorization: Bearer <your-production-token>"
```

Do not reuse the local acceptance token in production. Token values were not printed in this chat or stored in the server database. Copy-once UI values remain only in component memory.

### Manual login checks after upgrading PyJWT

- Microsoft: from a logged-out browser, sign in, verify the account and tasks, refresh, then log out.
- Google: repeat the same flow.
- Both: verify a pre-upgrade session works until expiry; verify another account's data is inaccessible; cancel/deny sign-in and confirm a safe return to the app.

These checks need the owner's interactive provider login; automated tests do not replace them.

## Delivery boundary

### Verified production database and proposed backup

Read-only inspection of the running Fly API on 11 November 2026 verified that `eigentask-api` connects to **Neon**, not a Fly Postgres cluster. Database: `neondb`; role: `neondb_owner`; server: PostgreSQL **17.11**; region: AWS London (`eu-west-2`). App host: `ep-wandering-silence-ab67kued-pooler.eu-west-2.aws.neon.tech`. The direct backup host `ep-wandering-silence-ab67kued.eu-west-2.aws.neon.tech` was independently connected to and verified. TLS and channel binding are required. No Fly proxy is needed. Production health returned HTTP 200.

Matching `pg_dump` and `pg_restore` 17.11 clients were extracted locally from the official EDB Windows binaries into `.venv/pg17-client`; no database server was installed or changed. `scripts/backup_production.py` fetches the existing password through authenticated Fly SSH into memory, passes it only in the pg_dump child's environment, creates an exclusive binary custom-format archive, runs `pg_restore --list`, and writes a SHA-256 companion file. It never deploys or restores. Five isolated safety tests passed, covering previews, existing-file protection, binary output, failure handling and credential handling. The real backup has **not** been run.

Exact proposed PowerShell command (works from any directory):

```powershell
& 'C:\Users\MarkGray\LocalProjects\Eigentask\ppapp-fastapi\.venv311\Scripts\python.exe' 'C:\Users\MarkGray\LocalProjects\Eigentask\ppapp-fastapi\scripts\backup_production.py' --output 'C:\Users\MarkGray\Backups\Eigentask\eigentask-before-m1-2026-11-11.dump'
```

The underlying pg_dump invocation uses `--format=custom --host=ep-wandering-silence-ab67kued.eu-west-2.aws.neon.tech --port=5432 --username=neondb_owner --dbname=neondb --no-password`, with `PGSSLMODE=require` and `PGCHANNELBINDING=require`. The password never appears in the command, transcript or backup-side logs. The archive is written as binary output without PowerShell redirection. Validation lists archive contents only; it does not claim to have tested a full restore.

M1 provides tokens, goal plan references and eight read tools. M2 write tools and transaction changes must wait for explicit instruction. No push, PR or deployment is authorised. Before deployment, inspect the actual Fly database configuration, supply an exact custom-format pg_dump backup command and wait for approval. Verify the resulting archive before migrations.

M2 has not started. Local Claude Code acceptance is complete. Remaining interactive acceptance checks are the Microsoft/Google checklist above and checks against production after an approved deployment. The Claude-side planning skill, MCP OAuth, task-status history and time tracking remain follow-ups.
