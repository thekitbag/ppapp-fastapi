# MCP milestone 1 handover

## Baseline and prerequisite commits

Baseline before changes: Python 3.11 backend **361 passed**; frontend **328 passed, 8 skipped**. Frontend build and TypeScript checks passed. No pre-existing test failures. The initial frontend setup/test overlap was discarded and rerun sequentially.

Dependency changes: Pydantic 2.12.5 / core 2.41.5, PyJWT 2.10.1, Uvicorn 0.38.0; uvloop is excluded on Windows. FastAPI 0.111.0, Starlette 0.37.2 and AnyIO 4.10.0 stay pinned.

### Manual login checks after upgrading PyJWT

- Microsoft: from a logged-out browser, sign in, verify the account and tasks, refresh, then log out.
- Google: repeat the same flow.
- Both: verify a pre-upgrade session works until expiry; verify another account's data is inaccessible; cancel/deny sign-in and confirm a safe return to the app.

These checks need the owner's interactive provider login; automated tests do not replace them.

## Delivery boundary

M1 provides tokens, goal plan references and eight read tools. M2 write tools and transaction changes must wait for explicit instruction. No push, PR or deployment is authorised. Before deployment, inspect the actual Fly database configuration, supply an exact custom-format pg_dump backup command and wait for approval. Verify the resulting archive before migrations.
