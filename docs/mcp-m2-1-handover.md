# MCP M2.1: task-size updates

`update_task` now accepts optional `size`: omission leaves it unchanged, and an explicit JSON null clears it. Values are validated through the existing REST `TaskUpdate` schema, using the app's actual story-point scale: **1, 2, 3, 5, 8, 13, 21**. Both REST and the web UI already allow 13 and 21, so those values remain supported.

Task creation and update descriptions document that scale. `BatchTask` already inherits `size` and its validation from `TaskDraft`; no batch contract change was needed.

Coverage includes every allowed value, changing/clearing/omitting size, rejecting invalid values, write-scope enforcement, cross-user rejection, and existing bulk size support. An SDK HTTP test resizes an unsized completed task and verifies that `get_insights` summary and breakdown totals increase, while its completion timestamp stays unchanged; clearing the size removes the points again.

Full backend suite: **442 passed** on both **Python 3.11.18** and **Python 3.13.14**, with the local PostgreSQL tests enabled.

No database migration, REST contract change or frontend change is required. This is one backend-only commit on `feat/mcp-task-size`. Nothing is pushed or deployed; take and verify a fresh production backup before any approved deployment.
