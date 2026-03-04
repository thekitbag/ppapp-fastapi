# Recommendations Logic

This document describes the behavior of the recommendation scoring engine implemented in:
- `app/api/v1/recommendations.py`
- `app/services/recommendations.py`

## Endpoints

### `GET /api/v1/recommendations/next`
Returns ranked task recommendations for immediate execution.

Query params:
- `limit` (optional, default `5`)
- `energy` (optional): `low | medium | high`
- `time_window` (optional): `15 | 30 | 60 | 120 | 240` (minutes)
- `window` (deprecated, optional): kept for backward compatibility, not used in ranking

Notes:
- Invalid `energy` or `time_window` values return HTTP `422`.
- Candidate tasks are user-scoped and limited to statuses:
  - `backlog`, `week`, `today`, `doing`

### `POST /api/v1/recommendations/suggest-week`
Returns a capped list of week-planning recommendations.

Body:
- `limit` (default `5`)

Notes:
- Candidate tasks are user-scoped and limited to `backlog` only.
- Uses the same ranking engine with a wider due-date horizon (7 days).

---

## Ranking Overview

The ranking engine is `prioritize_tasks(...)`.

Sort order:
1. Descending `score`
2. Ascending `task.sort_order`
3. Ascending `task.created_at`

Score formula:
- `raw = sum(weight_i * factor_i)`
- `score = (raw / max_raw) * 100`

`max_raw` is the sum of all active weights in the current run.

---

## Factors and Weights

### Base weights (always active)

| Factor | Weight | Description |
|---|---|---|
| `status_boost` | 10 | task.status == `today` |
| `due_proximity` | 5 | task due within horizon (24h for `/next`, 7d for `/suggest-week`) |
| `goal_align` | 2 | task has a tag named `"goal"` |
| `project_due_proximity` | 0.12 | sigmoid score from project milestone due date |
| `goal_linked` | 0.10 | task has at least one TaskGoal link |
| `goal_status_at_risk` | 10 | best linked goal status is `at_risk` (exclusive with off_target) |
| `goal_status_off_target` | 15 | any linked goal status is `off_target` (takes priority over at_risk) |
| `goal_urgency` | 10 | sigmoid from nearest linked goal `end_date` |

### Conditional weights (activated by query params)

| Factor | Weight | Activated when |
|---|---|---|
| `energy_match` | 20 | `energy` query param provided |
| `time_fit` | 15 | `time_window` query param provided |

---

## Factor Definitions

### `status_boost`
- `1` when `task.status == "today"`, else `0`.

### `due_proximity`
- `1` when `task.hard_due_at` or `task.soft_due_at` is within the horizon, else `0`.

### `goal_align`
- `1` when the task has a tag named `"goal"`, else `0`.

### `project_due_proximity`
- Sigmoid score `0–1` derived from the project's `milestone_due_at`.
- Formula: `1 / (1 + exp((days_until_milestone - 7) / 2.0))`
- ~0.88 at 1 day, ~0.5 at 7 days, ~0.12 at 14 days.
- `0.0` if project has no milestone or milestone is in the past.

### `goal_linked`
- `1` when the task has at least one `TaskGoal` link, else `0`.

### `energy_match` (SUGGEST-002)
Matches `task.energy` field against the user-provided `energy` param.

Mapping (user energy → accepted task.energy values):
- `low` → `{low, tired}`
- `medium` → `{medium, neutral}`
- `high` → `{high, energized}`

**Fallback policy**: `task.energy = None` → no boost (unknown energy requirement).

### `time_fit` (SUGGEST-002)
Uses `task.size` as Fibonacci effort points. Fit is determined by a fixed effort-band policy:

| time_window (minutes) | max task size that fits |
|---|---|
| 15 | 1 |
| 30 | 2 |
| 60 | 3 |
| 120 | 5 |
| 240 | 8 |

**Fallback policy**: `task.size = None` → no boost (unknown effort).

### `goal_status_at_risk` and `goal_status_off_target` (SUGGEST-002)
- For multi-goal tasks: use the **max** status boost across all linked goals.
- `off_target` takes priority (weight 15 > at_risk weight 10). A task cannot receive both boosts simultaneously.
- `on_target` goals contribute 0 to either factor.

### `goal_urgency` (SUGGEST-002)
- Sigmoid score based on the nearest-expiring linked goal's `end_date`.
- Formula: `1 / (1 + exp((days_until_end - 14) / 3.0))`
- ~0.97 at 1 day, ~0.5 at 14 days, ~0.03 at 28 days.
- `0.0` if no linked goals have a future `end_date`.
- For multi-goal tasks: uses the goal with the highest urgency score.

---

## Explanations (`why`)

`why` text is generated from active factors. Order of appearance:

1. Energy match: `"Matches your {energy} energy level"`
2. Time fit: `"Fits your {time_window}m window"`
3. Due proximity: `"Due soon"`
4. Goal tag alignment: `"Aligned with a goal"`
5. Project milestone: `"Project {name} milestone in N days"`
6. Goal health: `"Linked goal is off target"` or `"Linked goal is at risk"`
7. Goal urgency (>0.5): `"Goal due in N days"` or `"Goal due soon"`
8. Goal link (when no status signal): `"Linked to goal '{title}'"` or `"Linked to N goals"`
9. Trailing (secondary): `"Ready to start"` (for `today` status tasks)

Example: `"Matches your low energy level and fits your 30m window; linked goal is off target"`

---

## Data Access Pattern

To avoid N+1 reads, the service batches all lookups before the per-task loop:

1. **Project batch**: one query for all `project_id`s present in the candidate task list.
2. **TaskGoal batch**: one query for all `task_id`s. Returns task→goal links.
3. **Goal batch**: one query for all `goal_id`s from the links. Returns goal objects with `status` and `end_date`.

All lookups are user-scoped via `user_id` filtering.

---

## Engine Architecture (SUGGEST-003)

### Overview

Recommendation logic is encapsulated behind a `RecommendationEngine` abstract base
class (`app/services/recommendation_engine.py`). This decouples the API layer from
the ranking implementation and makes it straightforward to swap in an LLM-based
strategy in the future.

### Canonical Request Context

Both engines receive a single `RecommendationContext` dataclass:

```python
@dataclass
class RecommendationContext:
    tasks: List[Task]      # user-scoped candidate tasks (pre-filtered)
    db: Session            # live DB session for batch lookups
    energy: Optional[str]  # user energy param (low|medium|high)
    time_window: Optional[int]  # available minutes
    limit: int             # max results to return
```

### Engines

| Engine | Class | `NAME` | Behaviour |
|---|---|---|---|
| Algorithmic | `AlgorithmicRecommendationEngine` | `"algorithmic"` | Deterministic weighted-factor scorer (SUGGEST-002 model) |
| LLM | `LLMRecommendationEngine` | `"llm"` | Calls OpenAI-compatible API for top pick; falls back to algorithmic on any failure (SUGGEST-004). |

### Strategy Selection

```
USE_LLM_PRIORITIZATION=false  →  AlgorithmicRecommendationEngine  (default)
USE_LLM_PRIORITIZATION=true   →  LLMRecommendationEngine
```

The factory `get_recommendation_engine(use_llm: bool)` is called once per request
via a FastAPI `Depends(_get_engine)` dependency. No branching exists in endpoint code.

### Structured Logging

Each engine emits at `INFO` and `DEBUG` level:

```
INFO  engine=algorithmic candidates=12 returned=5 energy=low time_window=30
DEBUG task_id=<uuid> score=72.30 why="Matches your low energy level..."
```

Logs contain task IDs and scores only — no task titles, user emails, or other PII.

### LLM Narrative Why Text

`LLMRecommendationEngine` post-processes terse factor text via `_to_narrative()`:

- `"Due soon and linked goal is off target"` → `"Recommended because due soon and linked goal is off target."`
- `"No strong signals (baseline order)"` → `"This task has been waiting — it might be a good time to make progress on it."`

### Extending for Real LLM Integration

Completed in SUGGEST-004 — see section below.

---

## LLM Engine — Real Integration (SUGGEST-004)

### Environment Variables

| Var | Default | Purpose |
|---|---|---|
| `USE_LLM_PRIORITIZATION` | `false` | Enable LLM engine |
| `LLM_API_KEY` | — | Shared server API key (required; missing → algorithmic fallback) |
| `LLM_MODEL` | `gpt-4.1-mini` | Model identifier |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL |
| `LLM_TIMEOUT_SECONDS` | `8.0` | Per-request HTTP timeout |

### LLM Candidate Set

Statuses `today` and `week` only. If no such tasks exist, engine falls back to
algorithmic ranking on the full candidate pool.

### Context Schema

```json
{
  "user_state": {"energy": "medium|null", "time_window": 60},
  "tasks": [
    {
      "id": "...", "title": "...", "status": "today", "size": 2,
      "energy": "low", "hard_due_at": null, "soft_due_at": null,
      "project_id": null,
      "linked_goals": [{"id": "...", "title": "...", "status": "on_target", "end_date": null, "type": "annual"}]
    }
  ],
  "goals": [{"id": "...", "title": "...", "type": "annual", "status": "on_target", "end_date": null, "parent_goal_id": null}]
}
```

### Expected LLM Response

```json
{"task_id": "<id from task list>", "score": 91, "why": "..."}
```

### Fallback Matrix

| Condition | `fallback_reason` |
|---|---|
| `LLM_API_KEY` missing | `missing_api_key` |
| No `today`/`week` candidates | `empty_candidate_set` |
| Timeout / transport error / non-2xx | `llm_request_failed` |
| Malformed JSON / missing fields | `invalid_response` |
| Empty `why` after trim | `invalid_response` |
| `task_id` not in candidate list | `unknown_task_id` |

### Merge Strategy

LLM selects one top task. Remaining slots (`limit-1`) are filled from algorithmic
ranking of the full candidate pool, excluding the LLM-selected task.
The LLM item carries: LLM score, LLM `why`, algorithmic `factors` (unchanged).

---

## Known Constraints / Decisions

- `window` query parameter is deprecated and currently not used by ranking logic.
- `task.energy = None` is treated as no boost for both `energy_match` and `time_fit` to avoid elevating tasks with unknown requirements.
- `task.size = None` is treated as no boost for `time_fit` (unknown effort).
- The `_normalize` helper exists but is not used in the active scoring path.

---

## Test Coverage

Primary test files:
- `tests/test_recs.py` — endpoint validation and backward compatibility
- `tests/services/test_recommendations_service.py` — energy_match, time_fit, goal health, why text
- `tests/test_goals_recommendations.py` — goal-linked factor, goal health scoring, N+1 guard
- `tests/test_priority.py` — base formula, project milestone scoring
- `tests/test_week_suggest.py` — week suggestion behavior
