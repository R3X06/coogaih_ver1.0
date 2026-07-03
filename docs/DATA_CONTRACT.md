# Coogaih — Data Layer Contract (v1.0)

This document is the single source of truth for the boundary between **data producers**
(what runs on the laptop and captures activity) and the **cognitive engine**
(what turns activity into signals and recommendations).

Both halves of the team build against *this file only*. Producers can be mocked with
`sample_events.jsonl`; the engine never needs a real watcher to exist.

---

## 1. Pipeline

```
PRODUCERS                      INGEST          ENRICH            ENGINE
─────────                      ──────          ──────            ──────
window_watcher  ┐
browser_ext     │   normalized  ┌────────┐   categorizer   ┌──────────────┐
afk_watcher     ├──  events  ──▶ │ store  │ ──  (adds    ──▶│ derive       │
manual_client   │              └────────┘     category)     │ signals,     │
simulator       ┘                                            │ run LLM, etc │
                                                             └──────────────┘
```

**The one rule that keeps this clean:** producers are *dumb*. They report only what
happened (which app, which domain, idle or not, a manual entry). They **never** assign a
category, judge focus, or compute a signal. Everything semantic happens downstream.

Why this matters:
- Add a new producer later (mobile, a second OS, a different browser) with **zero engine changes** — it just emits the same envelope.
- Your teammate builds the entire engine against mock events before a single watcher exists.
- It is the architectural form of your "no hallucinated data" promise: the LLM only ever narrates numbers the engine computed from raw events.

---

## 2. The normalized event envelope

Every event from every producer has this exact shape:

```jsonc
{
  "schema_version": "1.0",     // string, always present
  "event_id":  "uuid-v4",      // unique per event
  "ts":        "2026-06-13T09:03:11.482Z",  // UTC, ISO-8601
  "local_offset_min": 480,     // int; minutes from UTC (e.g. SGT = +480). Enables time-of-day analysis.
  "source":    "window_watcher",  // who produced it (enum, see §3)
  "kind":      "focus",        // what kind of event (enum, see §3)
  "duration_ms": 124000,       // int >= 0 for span events; null for instantaneous events
  "category":  null,           // ALWAYS null from producers; filled in by the categorizer (§5)
  "payload":   { ... }         // kind-specific, see §3
}
```

- `ts` is the **start** of the span (for span events) or the moment (for instantaneous events).
- `duration_ms` + `ts` fully describe a span. A new `focus` event implies the previous one ended.
- `category` is part of the envelope but is **only** written by the enrich stage. Producers leave it `null`.

---

## 3. Event kinds & payloads

| source           | kind            | span?         | purpose                              |
|------------------|-----------------|---------------|--------------------------------------|
| `window_watcher` | `focus`         | yes           | which app held foreground            |
| `browser_ext`    | `browse`        | yes           | which site was active in the browser |
| `afk_watcher`    | `afk`           | yes           | user idle (no input)                 |
| `manual_client`  | `manual_log`    | no            | user check-in (confidence etc.)      |
| `simulator`      | any of the above| —             | synthetic data for tests & demo      |

### 3.1 `focus` — payload
```jsonc
{
  "app":          "Code",                 // app/process display name
  "window_title": "data_contract.md — coogaih",  // may be redacted, see §4
  "executable":   "com.microsoft.VSCode", // optional, OS-specific id
  "pid":          43122                    // optional
}
```
A continuous span on **one** app. When the user jumps to another app, the watcher closes
this span (emits the event with its `duration_ms`) and opens a new one. So:

> **The number of `focus` events in a time window = the number of app switches.**
> Context-switch rate is *derived*, not a separate event. (This is your fragmentation signal.)

### 3.2 `browse` — payload
```jsonc
{
  "domain":     "coursera.org",   // never store full URL by default
  "page_title": "Calibration — Week 3",  // may be redacted, see §4
  "url_hash":   "sha256:...",      // optional, opt-in; for dedup without storing the URL
  "tab_id":     17                 // optional
}
```
A `browse` span occurs **inside** a `focus` span on the browser app. The engine aligns them
by timestamp; you do not need to link them explicitly.

### 3.3 `afk` — payload
```jsonc
{ "reason": "idle" }   // idle = no keyboard/mouse input past threshold
```
Used downstream to split sessions. `ts`+`duration_ms` = the idle span.

### 3.4 `manual_log` — payload  *(instantaneous: `duration_ms` = null)*
```jsonc
{
  "concept":             "Bayesian calibration",  // free text or tag
  "confidence":          0.7,    // float 0.0–1.0 (self-rated, BEFORE knowing outcome)
  "perceived_difficulty":3,      // int 1–5
  "outcome":             "incorrect", // "correct" | "incorrect" | "partial" | "na"
  "refers_to_session":   "sess_2026-06-13_am", // optional session id
  "notes":               "mixed up ECE and Brier"  // optional
}
```
This is the **only** source of `confidence`, which you cannot sense passively. It is the
input to your calibration metric — guard it carefully.

---

## 4. Privacy rules (non-negotiable, and a selling point)

- **Local-first.** All raw events live on the user's machine. Nothing leaves it without explicit opt-in.
- `window_title` and `page_title` can leak document names and message previews. The watcher
  supports a **redaction mode**: when on, titles are replaced with `"[redacted]"` and only
  `app` / `domain` are kept.
- An **exclusion list** lets the user mark apps/domains as "never record" (e.g. banking, messaging).
- Full URLs are **never** stored by default — `domain` + optional `url_hash` only.
- `outcome` and `confidence` are user-owned learning data; treat them as sensitive.

---

## 5. Categorization ruleset format

The enrich stage turns raw events into categories using a **user-editable** ruleset.
Categories: `study` | `work` | `distraction` | `neutral`.

```jsonc
{
  "version": 1,
  "default_category": "neutral",
  "rules": [
    // First match wins → put SPECIFIC rules before GENERAL ones.
    { "match": { "domain": "youtube.com", "title_regex": "(?i)(lecture|tutorial|course)" }, "category": "study" },
    { "match": { "domain": "youtube.com" },                       "category": "distraction" },
    { "match": { "domain": "coursera.org" },                      "category": "study" },
    { "match": { "domain": "leetcode.com" },                      "category": "study" },
    { "match": { "app": "Code" },                                 "category": "study" },
    { "match": { "app": "Slack" },                                "category": "work" },
    { "match": { "app": "Mail" },                                 "category": "work" }
  ]
}
```

Match fields (all optional; a rule matches only if **all** present fields match):
- `app` — exact match on `payload.app`
- `domain` — exact match on `payload.domain`
- `app_regex` / `domain_regex` / `title_regex` — regex alternatives

**Evaluation:** rules are checked top-to-bottom, first match wins; if none match, use
`default_category`. (The YouTube pair above shows why order matters: a lecture is study,
everything else on the same domain is distraction.)

**Optional LLM fallback:** for events that hit `default_category`, you may ask the LLM to
suggest a category from `app` + redacted `title`. The suggestion is shown to the user as a
*proposed new rule* they confirm — it is never silently trusted. This keeps the "no
hallucinated data" guarantee intact.

---

## 6. Focus-watcher specification

A small background process. One OS first — build for **your own laptop's OS** before any port.

**Behavior:**
1. Poll the active window every `POLL_INTERVAL_MS` (default 3000) — or subscribe to OS
   focus-change notifications where available.
2. Maintain a *current span* `{app, title, start_ts}`. On focus change **or** afk
   transition, close the current span and emit a `focus` event with computed `duration_ms`.
3. Debounce: ignore spans shorter than `MIN_SPAN_MS` (default 1000) so a quick flick through
   windows doesn't create noise.
4. A separate idle check polls "time since last input" every `AFK_POLL_MS` (default 5000);
   if idle exceeds `AFK_THRESHOLD_MS` (default 120000), emit an `afk` event for the idle
   span and pause the active focus span; resume on next input.

**OS hooks (active window + title):**
- **macOS:** `NSWorkspace.frontmostApplication` + Accessibility API for the window title.
  Requires the user to grant **Accessibility** permission.
- **Windows:** `GetForegroundWindow` → `GetWindowText` (title) + `GetWindowThreadProcessId` → process name.
- **Linux/X11:** `_NET_ACTIVE_WINDOW` via `xprop`/`xdotool`. (Wayland is restricted — note as a limitation.)

**Idle/last-input hooks:**
- macOS: `CGEventSourceSecondsSinceLastEventType`
- Windows: `GetLastInputInfo`
- Linux/X11: `XScreenSaverQueryInfo`

**Tunable params (surface these in config):**
`POLL_INTERVAL_MS`, `MIN_SPAN_MS`, `AFK_POLL_MS`, `AFK_THRESHOLD_MS`, `redaction_mode`, `exclusion_list`.

---

## 7. Derived signals (downstream — informational, not part of this layer)

So both halves understand the contract's *purpose*. These are computed by the engine from
the event stream; they are **not** emitted by producers:

- **time_on_task** — summed `focus`/`browse` duration per `category`, per session.
- **context_switch_rate** — `focus` events per active minute. (Your fragmentation / stability signal.)
- **distraction_ratio** — distraction time ÷ total active time.
- **session structure** — count, length, and gaps (split on `afk` spans).
- **calibration gap** — from `manual_log.confidence` vs `outcome` (ECE / Brier). Needs `outcome` present.

---

## 8. Versioning

- Every event carries `schema_version`. This document is `1.0`.
- Additive changes (new optional payload field, new `kind`) bump the **minor** version.
- Breaking changes (renamed/removed field, changed type) bump the **major** version and the
  engine must branch on `schema_version`.
- Never silently reuse a field name with a new meaning.