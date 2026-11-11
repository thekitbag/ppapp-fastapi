# MCP milestone 2 handover

M2 is implemented on **`feat/mcp-write-tools`** in both repositories and is being submitted for PR review. **It has not been merged or deployed. Production remains on M1**, and its token/configuration is unchanged.

## Implemented

- Five write tools: `create_task`, `update_task`, `create_goal`, `update_goal`, `bulk_create`. Together with the eight existing reads, the local server exposes 13 tools. No delete tools were added.
- All write tools, including a bulk dry run, require a `write`-scoped PAT. Existing `read` tokens keep their scope; no production token was minted or upgraded for M2.
- Goal references accept owned IDs or `plan_ref`; projects accept owned IDs or unique exact names. Ambiguous and foreign-user references fail. Creation preserves annual/quarterly/weekly hierarchy rules and the backlog default for tasks.
- Task patches add/remove tags and goal links atomically. Omitted fields remain unchanged. Explicit null clears descriptions and deadlines; goal patches also clear end dates or plan references. Null titles/statuses and conflicting additions/removals fail validation.
- Task completion/reopening uses the existing task service. Explicit-null task updates now clear nullable repository fields instead of silently ignoring them; the REST schema already described those fields as nullable. Incoming MCP dates are normalised to UTC.
- Settings copy now describes Read and Write permissions without the old M1-only wording. Read stays selected by default; Write stays opt-in.

## Bulk preview and commit

`bulk_create` defaults to `dry_run=true` and supports up to 1000 combined goal/task items. Temporary `key` values are unique across the batch and cannot shadow existing goal references. New goals can be referenced by their key or `plan_ref`, including forward references. Goal creation is topologically ordered.

The preview returns `valid`, `committed: false`, resolved goal parents, task goal/project references, `tags_to_create`, and item-specific reference/hierarchy errors. Previewing issues no INSERT, UPDATE or DELETE statements. Blank or duplicate keys, duplicate plan references, ambiguous aliases, cycles, invalid projects/dates and cross-user references are rejected. Repeated references to the same task goal are deduplicated.

The client must show the preview and obtain the user's approval before sending the same batch with an actual JSON boolean `dry_run=false`. Approval is a Claude-side interaction described in the tool, not a server-side approval token. The stateless server revalidates every committed batch. A bad reference or later service/database failure leaves no partial goals, tasks, tags or junction links.

`atomic(db)` owns the operation's one commit. Nested task/goal service commits flush rather than committing. A nested rollback marks the whole operation as failed, including when an intermediate error is caught. Standalone REST calls retain their existing commit behavior. Updates lock the owned task while composing tag/link changes. Bulk results correlate new records with the supplied item keys.

Writes are not automatically retried or deduplicated. If a connection fails around a commit, inspect current state before retrying a capture or batch.

## Single-copy responses

Success and application-error results now use **`structuredContent` only**, with `content: []`. Stable payload fields are preserved; the SDK's duplicate text serialisation is bypassed by returning an explicit `CallToolResult`. A client that parses `content[0].text` must read `structuredContent` instead. SDK argument-validation errors may still use a single text error block.

Verified with a real Claude Code probe, the SDK integration tests, Inspector, and the full local Claude write flow. Claude could read preview details, wait for approval, and use returned IDs for subsequent updates from structured-only results. Nullable text also preserves literal strings such as `"null"` or JSON text; only an actual JSON null clears a nullable field.

## Verification

- Full backend suite: **433 passed** on both Python **3.11.18** and **3.13.14**, with local PostgreSQL tests enabled.
- Full frontend suite: **399 passed, 8 skipped**; TypeScript and production build passed.
- New service/transport coverage includes all five write tools, write-scope enforcement, cross-user attempts, sparse/null patches, completion timestamps, duplicate and ambiguous references, date validation, batch cycles and previews with no DML.
- Disposable local PostgreSQL tests proved that other connections see no intermediate records, successful bulk creation commits once, late failures roll back every affected table, and changed database state invalidates an earlier preview.
- Claude Code first previewed a synthetic local batch: **zero goals, tasks, tags or links were written**. A separately authorised local test then previewed/committed the same batch, exercised all five write tools, verified completion/null clearing and queried the new task. All tool results succeeded.
- Inspector successfully ran a resolved bulk preview, confirmed `content: []`, and independently confirmed unchanged row counts.
- Regenerated `openapi.json` and frontend API types: **no diff**. These new contracts are MCP tool schemas; no REST endpoints or database migrations were added.

## Local commits

- Backend `020536f`: shared transaction boundaries and nullable task patches.
- Backend `9bb5bf3`: five scoped write tools, atomic bulk planner/commit, structured-only responses and regression/integration tests.
- Frontend `6255b89`: token settings permission copy and its test.

## Local review and deployment boundary

An isolated local M2 server runs at `http://localhost:8013/mcp`, using `.venv/mcp-m2.sqlite3` and a read/write test token. It contains synthetic acceptance records only. The ignored `.venv/mcp-m2-local.json` configuration can be used without changing your production Claude connection:

```powershell
claude --strict-mcp-config --mcp-config 'C:\Users\MarkGray\LocalProjects\Eigentask\ppapp-fastapi\.venv\mcp-m2-local.json'
```

The ignored acceptance transcripts are `.venv/claude-m2-preview.jsonl` and `.venv/claude-m2-commit.jsonl`. No real task/goal records were changed. M1 remains live at `https://api.eigentask.co.uk/mcp` until M2 deployment is explicitly authorised.

Before a future deployment, refresh from both remote main branches, run the required checks, take/verify a **fresh** production backup, and follow the existing PR/main-triggered deployment flow. Do not reuse the pre-M1 backup as the pre-M2 checkpoint.
