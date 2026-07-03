# Coogaih — API Contract (Seam 2: Engine → API)

**Endpoint:** `POST /ingest/session-metrics`
**Called by:** Focus-State Engine (friend's service)
**Auth:** none in MVP (add a shared API key before any public demo)

## Request body

```json
{
  "session_id": "uuid",
  "user_id": "uuid",
  "ts_start": "2026-07-03T09:00:00Z",
  "ts_end": "2026-07-03T09:42:00Z",
  "switching_rate": 0.42,
  "avg_focus_block_minutes": 7.3,
  "fragmentation": 0.31,
  "distraction_ratio": 0.18
}
```

| Field | Type | Range | Notes |
|---|---|---|---|
| `session_id` | uuid | — | primary key; **idempotent** — resending the same id updates in place |
| `user_id` | uuid | — | must already exist in `users` |
| `ts_start` / `ts_end` | ISO-8601 datetime | — | `ts_end` optional if session still open |
| `switching_rate` | float | 0–1 | see formula below |
| `avg_focus_block_minutes` | float | ≥0 | mean duration of uninterrupted study-focus blocks, in minutes |
| `fragmentation` | float | 0–1 | see formula below |
| `distraction_ratio` | float | 0–1 | `non_study_time / total_session_time` |

## Response — `201 Created`

Same shape plus `risk_score` (nullable, populated later by the cognitive engine — the Engine never sets this).

## Locked formulas (finalize before either side starts)

```
switching_rate = clamp((switches / active_minutes) / SWITCH_MAX, 0, 1)
    SWITCH_MAX = 0.5   # switches per active minute → switching_rate hits 1.0 at 30 switches/hour

fragmentation = clamp((study_block_count / study_minutes) / FRAG_MAX, 0, 1)
    FRAG_MAX = 0.2     # blocks per study minute → hits 1.0 at one new block every 5 min

distraction_ratio = non_study_time / total_session_time
```

`SWITCH_MAX` / `FRAG_MAX` are starting values, not gospel — sanity-check them against a
real captured session once the extension is emitting events, and adjust together if
real numbers cluster oddly against these bounds. Whoever changes them notifies the other
side, since the dashboard and the property tests both assume these constants.

## Validation

- All 0–1 fields are rejected outside `[0, 1]` (FastAPI/Pydantic `Field(ge=0, le=1)`).
- `avg_focus_block_minutes` rejected if negative.
- Unknown extra fields are ignored, not rejected (forward-compatible).

## What the API does NOT do

- Does not compute metrics — it trusts the Engine's numbers and only validates shape/range.
- Does not write to Supabase directly from the Engine — this endpoint is the only write path.
- Does not touch `risk_score` on ingest — that's set later by the cognitive engine.
