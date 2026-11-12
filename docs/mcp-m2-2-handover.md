# MCP M2.2: goal lifecycle and visible unparented goals

Implemented locally on `feat/mcp-goal-lifecycle` in both repositories. Nothing pushed or deployed. No migration or dependency change is needed. A fresh, verified production backup remains required before an approved deployment.

## MCP contract

`update_goal` now accepts optional `closed`, `archived` and `parent` alongside its existing fields. It still requires write scope and returns its data once in `structuredContent`.

- `closed: true` uses the existing close service: close the selected goal and its owned descendants, setting `closed_at`. Repeated closure preserves existing timestamps.
- `closed: false` reopens only the selected goal and clears its `closed_at`; descendants stay in their existing state.
- `archived: true/false` independently archives/unarchives only the selected goal. It does not close goals or archive descendants.
- `parent` resolves a case-sensitive owned goal ID or `plan_ref`. Quarterly goals require an annual parent; weekly goals require a quarterly parent; annual goals cannot have a parent. Explicit null follows those existing rules, so it is rejected for typed quarterly/weekly goals. Legacy parentless quarterly/weekly goals can be closed/archived without supplying parent, or repaired by supplying a valid one.
- Omitted fields remain unchanged. Lifecycle flags require actual booleans; null is rejected.
- Target and supplied parent rows are locked with PostgreSQL `FOR UPDATE`, matching the task-update approach. Re-parenting, ordinary fields, closure and archiving share one transaction; any failure rolls everything back.
- Cycles and foreign-user references are rejected. Shared cycle traversal is user-scoped, and descendant closure also guards against malformed cross-user links and repeated nodes.

Examples of MCP arguments (use the user's actual goal reference):

```json
{"goal":"WEEK-REF","closed":true}
{"goal":"QUARTER-REF","parent":"ANNUAL-REF"}
{"goal":"GOAL-REF","closed":false,"archived":false}
```

## Web UI

The active goals visualization previously rendered annual buckets only. Goals outside those buckets now appear under **Unparented goals**, including quarterly roots, weekly roots and descendants of orphan quarters. Cards retain status/date, edit, close, delete, task and focus callbacks. Valid annual hierarchies remain in their existing buckets with no duplicate cards. The empty annual message no longer hides orphan-only data.

## Verification

- Full backend suite: **459 passed** on Python **3.11.18** and **3.13.14**, with local disposable PostgreSQL tests enabled.
- Full frontend suite: **403 passed, 8 skipped**. Existing skipped tests remain skipped. TypeScript check and production build pass.
- Real SDK Streamable HTTP coverage verifies new schema fields, sparse omission/null/false handling, lifecycle operations, re-parenting, write-scope enforcement, foreign-user rejection and structured-only responses.
- PostgreSQL coverage verifies an independent session cannot acquire the locked target row, and that a late failure rolls back both goal fields and descendant closure.
- UI tests exercise orphan quarterly edit/close controls, weekly roots, orphan descendants, normal hierarchy rendering and mixed roots.
- Regenerated `openapi.json` and `src/types/api.d.ts` through the existing scripts: **no generated diffs**. The REST contract is unchanged.
- Suites retain existing deprecation warnings and frontend React test warnings; no failures remain.

No production data was changed, including the goal named in the brief. Closing that goal remains a post-deployment action. Refresh the Claude MCP connection after deployment so it discovers the expanded tool schema.
