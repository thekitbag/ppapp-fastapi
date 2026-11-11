# MCP milestone 1 handover

This records the deployed M1 release. Later local, undeployed M2 work is described in [mcp-m2-handover.md](mcp-m2-handover.md).

## Production outcome — 11 November 2026

**M1 is deployed and production connection checks passed. M2 has not started.**

- Backend PR [#32](https://github.com/thekitbag/ppapp-fastapi/pull/32) was merged by Mark; automatic Fly deployment succeeded for commit `97ca97977cf326ef05a88e1b72183ae1607054a9`.
- Frontend PR [#36](https://github.com/thekitbag/ppapp-web/pull/36) was merged after the backend was healthy; Vercel production deployment succeeded for commit `da62a0d3e4893eaa83ad7c429773fb4387c207f6`.
- Latest-main integration verification: **405 backend tests passed** on Python 3.11 and 3.13; **399 frontend tests passed, 8 skipped**; type checks, build, coverage and CI security audits passed. `follow-redirects` was patched to 1.16.3 after the initial frontend audit failure.
- Production API health returned 200. Anonymous/cookie-only MCP requests and anonymous token management returned 401. Goal `plan_ref` appears in the production REST schema, and the database migration head is `b12a7c04d002`.
- The SDK successfully exercised **all eight production read tools**. MCP Inspector discovered the eight tools. Claude Code then successfully queried annual goals, tasks, insights and tags against the live account, with no errors or permission denials.
- The user-level Claude Code connection **`eigentask`** is registered at `https://api.eigentask.co.uk/mcp` using a read-only PAT named **Claude Code production (M1)**. It belongs to the existing work account containing the production tasks, and can be revoked in Settings. Client credentials are in the ignored `.venv/mcp-production.json` and the user's Claude configuration, never in the server database as plaintext.
- `https://eigentask.co.uk` returned 200; its deployed assets contain the token settings UI and goal plan-reference field. Interactive Microsoft/Google sign-in checks remain for Mark, as listed below.
- Production task/goal counts after deployment match the pre-deployment counts: **1,462 tasks and 171 goals**. Acceptance did not create or change task/goal records.


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

Fresh PostgreSQL replay fails in existing revision `81f80f37840f` because it tries to drop `tasks_pkey` while `task_tags_task_id_fkey` depends on it. This predates M1. Historical migrations were not rewritten. New-migration tests bootstrap the current model schema in a disposable database, stamp the new head, downgrade to `20260228_report001`, then exercise upgrade/downgrade with existing rows. A separate repair is needed before relying on a fresh PostgreSQL install. No production database was accessed during initial M1 implementation. Later deployment preparation used read-only connection checks; production acceptance created a read-only PAT for the existing owner without changing tasks or goals.

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

Production is now deployed and the `eigentask` connection is already registered. For a fresh client or replacement production token, create a read token in Settings and connect with:

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

Matching `pg_dump` and `pg_restore` 17.11 clients were extracted locally from the official EDB Windows binaries into `.venv/pg17-client`; no database server was installed or changed. `scripts/backup_production.py` fetches the existing password through authenticated Fly SSH into memory, passes it only in the pg_dump child's environment, creates an exclusive binary custom-format archive, runs `pg_restore --list`, and writes a SHA-256 companion file. It never deploys or restores. Five isolated safety tests passed, covering previews, existing-file protection, binary output, failure handling and credential handling. The production backup **was run before deployment** and verified with `pg_restore --list`; an independent SHA-256 check matched the saved checksum. Size: **212,109 bytes**. SHA-256: `2e5ddad4871a5f01c4006450a83de442835fb083c9e854e4028a19397d7c1308`. The archive contains the expected users, tasks and goals tables. No full restore was performed.

Executed PowerShell backup command (works from any directory; refuses to overwrite the existing archive):

```powershell
& 'C:\Users\MarkGray\LocalProjects\Eigentask\ppapp-fastapi\.venv311\Scripts\python.exe' 'C:\Users\MarkGray\LocalProjects\Eigentask\ppapp-fastapi\scripts\backup_production.py' --output 'C:\Users\MarkGray\Backups\Eigentask\eigentask-before-m1-2026-11-11.dump'
```

The underlying pg_dump invocation uses `--format=custom --host=ep-wandering-silence-ab67kued.eu-west-2.aws.neon.tech --port=5432 --username=neondb_owner --dbname=neondb --no-password`, with `PGSSLMODE=require` and `PGCHANNELBINDING=require`. The password never appears in the command, transcript or backup-side logs. The archive is written as binary output without PowerShell redirection. Validation lists archive contents only; it does not claim to have tested a full restore.

M1 provides tokens, goal plan references and eight read tools. Mark explicitly authorised the backup and M1 deployment; the backup gate was satisfied before merging to main triggered deployment. Backend approval was required by GitHub, and Mark merged that PR himself. M2 write tools and transaction changes still require separate explicit instruction.

M2 has not started. Local and production Claude Code acceptance are complete. Remaining interactive acceptance checks are the Microsoft/Google checklist above. The Claude-side planning skill, MCP OAuth, task-status history and time tracking remain follow-ups.
