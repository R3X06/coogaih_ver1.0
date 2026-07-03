# Coogaih — Final Locked Plan (v1)

**One-liner:** An AI study-intelligence system that models a learner's cognitive state over
time and *scores whether its own recommendations actually worked*.

**Scope (locked):** Browser-only MVP. No OS-level / cross-app watcher in v1.

---

## Locked principles

1. **LLM narrates, never invents.** Every number is computed deterministically by the engine; the LLM only explains numbers it is handed. No hallucinated data.
2. **Categories + timestamps only.** No URLs, page content, or keystrokes cross any boundary. Local-first, user-owned, honors a `telemetry_level` setting.
3. **Metrics route through the API, not the database.** The Focus-State Engine POSTs to the API; it never writes to Supabase directly. (You own the contract; he consumes it.)
4. **Every 0–1 metric has an exact formula.** Agreed in Week 0 — no undefined "0–1."
5. **Build against simulators first.** Neither half waits on the other to start.

---

## The split at a glance

```
   YOU (product + brain + platform)          FRIEND (Focus-State Engine + QUALITY)
   ─────────────────────────────────          ────────────────────────────────────
   Browser Extension ──raw events──────────▶  Focus-State Engine
   (capture, tag study/non_study)              - batch metrics
                                               - live focus-state classifier
   Public API (FastAPI)  ◀──metrics POST────   - nudge back to extension
     /ingest/session-metrics                   + owns ALL system test/quality:
   Cognitive Engine                              - ground-truth oracle / synthetic data
   (calibration · drift · risk)                  - property-based tests
   LLM + RAG Intelligence                        - contract tests on both seams
   Recommendation Impact Scoring                 - integration / E2E
   Manual Log (confidence → calibration)         - CI gating + coverage
   Dashboard (React/TS) · DevOps                 - API testing
```

---

## The two cross-team contracts

Both seams are between you and him. Lock both in Week 0.

### Seam 1 — Events: your Extension → his Engine
```jsonc
{ "type": "session_start", "ts": <unix_ms>, "session_id": "string" }
{ "type": "focus_start",   "ts": <unix_ms>, "tab_category": "study" | "non_study" }
{ "type": "focus_end",     "ts": <unix_ms>, "tab_category": "study" | "non_study" }
{ "type": "switch",        "ts": <unix_ms>, "from_category": "...", "to_category": "..." }
{ "type": "session_end",   "ts": <unix_ms>, "session_id": "string" }
```
Categorization (study vs non_study) happens **in the extension** via a user-editable rules
list. Binary for v1.

### Seam 2 — Metrics: his Engine → your API
```jsonc
POST /ingest/session-metrics
{
  "session_id": "string", "user_id": "string",
  "ts_start": "ISO-8601", "ts_end": "ISO-8601",
  "switching_rate":          0.42,   // 0–1
  "avg_focus_block_minutes": 7.3,
  "fragmentation":           0.31,   // 0–1
  "distraction_ratio":       0.18    // 0–1
}
```
**Starting formulas (finalize the constants in Week 0):**
- `switching_rate` = clamp((switches / active_minutes) / SWITCH_MAX, 0, 1)
- `avg_focus_block_minutes` = mean duration of uninterrupted study-focus blocks
- `fragmentation` = clamp((study_block_count / study_minutes) / FRAG_MAX, 0, 1)
- `distraction_ratio` = non_study_time / total_session_time

Plus a live message his engine → your extension for the nudge:
```jsonc
{ "type": "focus_state", "state": "deep_focus" | "steady" | "scattered", "ts": <unix_ms> }
```

---

## YOU own — and what it earns you

| Component | Skill (SWE + AI checklist) |
|---|---|
| Browser Extension (Manifest V3) | web platform / extension dev; you own the whole data path |
| Public API (FastAPI) | RESTful API design · "wrap a model in an API" |
| Cognitive Engine — calibration (ECE/Brier), drift (CUSUM/Page-Hinkley), stability, risk | Pandas/NumPy/scikit-learn · ML evaluation literacy |
| Manual Log client (confidence + outcome) | sole source of your calibration metric |
| LLM Intelligence (snapshot, delta, debrief, recs) — structured JSON, grounded | prompt engineering · structured output |
| RAG over the learner's own history | the #1 2026 GenAI trend, done authentically |
| Recommendation Impact Scoring | evaluation methodology — rare in a student portfolio |
| DB schema (Postgres/Supabase) | SQL · data modeling |
| Dashboard (React + TypeScript) | full-stack story |
| Docker + (your own) build pipeline | containerization |
| Longitudinal simulator | drives the cognitive demo before real data exists |

Covers nearly the entire Singapore SWE *and* AI/ML checklist (DSA aside — grind separately).

## FRIEND owns — optimized for a TEST ENGINEER

Headline identity: **test & quality engineer for the whole system.** The Focus-State Engine
is his build component; the testing is his skill story.

| Deliverable | Test-engineer skill |
|---|---|
| Focus-State Engine — batch metrics + **live sliding-window classifier** + nudge | a stateful, timing-dependent component (rich to test) |
| Ground-truth oracle + synthetic event simulator | test-oracle design · synthetic test data |
| Property-based tests (Hypothesis) on metric invariants | advanced test design (e.g. "fragmentation ∈ [0,1]", "switching_rate monotonic in switches") |
| Contract tests on **both** seams (Pact-style) | consumer-driven contract testing across services |
| Integration + E2E across the pipeline | system-level test automation |
| CI gating + coverage (GitHub Actions) | CI/CD; the schema validator becomes one of his contract tests |
| API testing (Postman/Newman) | API test automation |
| *(stretch)* load/perf testing engine + API (k6/Locust) | performance testing |

His résumé line: *"Owned test automation and quality for a multi-service system — contract
tests across service boundaries, property-based tests on the computation core, CI gating, E2E."*

---

## Build order

**Week 0 — together (~half a day):** lock both contracts above, including the exact metric
formulas + normalization constants (`SWITCH_MAX`, `FRAG_MAX`) and the category rules list.

**Then parallel:**

*You:* DB + API skeleton → cognitive engine against your longitudinal simulator → LLM + RAG
→ impact scoring → extension → dashboard → Docker.

*Friend:* event simulator + ground-truth cases → Focus-State Engine to pass them → live
classifier → wire to your `/ingest/session-metrics` → stand up the cross-system test suite +
CI as each piece lands.

**Integration moment:** his engine posts real metrics to your live API; you swap your
simulator-fed metrics for real ones. Your cognitive engine doesn't care about the source —
that's the seam working.

---

## Two simulators (on purpose)

- **His:** events → metrics ground truth. Doubles as his core test fixture.
- **Yours:** longitudinal learner trajectories (steady improver / crammer / confidently-wrong). Drives the demo.

---

## Demo (what you show)

1. **Live:** study tab → jump to YouTube → back. Extension emits events → engine computes metrics + live state → dashboard updates; a nudge fires on `scattered`.
2. **Longitudinal:** load weeks of simulated history → dashboard shows the cognitive trajectory, **drift detection firing**, the calibration gap, a grounded recommendation, and — the headline — the **impact score of a past recommendation**.
3. **Quality:** the green CI badge + coverage + "contract & property-based tests across both service boundaries."

---

## MVP boundaries

**In v1:** browser-only capture · manual log · batch metrics + live classifier · calibration/drift/risk · grounded LLM snapshot + debrief + recommendation · recommendation impact scoring · dashboard · CI with contract + property tests.

**Later:** OS-level native agent · multi-agent eval · subject-level embeddings · mobile.

**Deliberately avoided:** clinical claims. "Burnout prediction" is reframed as
*engagement/fatigue signals* — no medical/mental-health inference.