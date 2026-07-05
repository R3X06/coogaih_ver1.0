# Coogaih — Locked Plan (v2)

**One-liner:** An AI study-intelligence system that models a learner's cognitive
state over time and *estimates the association between its own recommendations and
subsequent learning outcomes* — using single-subject interrupted-time-series
analysis, with a randomized-delay design documented for causal identification.

**Scope (locked):** Browser-only MVP. No OS-level / cross-app watcher in v1.

> **What changed from v1:** v1 was well-plumbed but two differentiators (risk score,
> recommendation impact) fell apart under statistical scrutiny — cold-start false
> alarms, drift detection unfit for sparse data, and a causal claim that was really
> correlational. v2 fixes all three with established methods (hierarchical shrinkage,
> BOCPD, interrupted time series) and then **scopes deliberately** so two people can
> actually finish it. The cuts are documented as engineering decisions, not gaps.

---

## Locked principles

1. **LLM narrates, never invents.** Every number is computed deterministically by the engine; the LLM only explains numbers it is handed.
2. **Categories + timestamps only.** No URLs, page content, or keystrokes cross any boundary. Categorization runs **on-device, pre-egress**. Local-first, user-owned, honors a `telemetry_level` setting.
3. **Metrics route through the API, not the database.** The Focus-State Engine POSTs to the API; it never writes to Supabase directly.
4. **Every 0–1 metric has an exact formula.** No undefined "0–1."
5. **Build against simulators first.** Neither half waits on the other to start.
6. **Small-sample honesty (new in v2).** Every score reports uncertainty. A new learner is scored via shrinkage toward a population prior, never with a naked point estimate on 3 data points. NULL/uncertainty is preferred over a confident lie.

---

## The three statistical fixes (the heart of v2)

### Fix 1 — Cold-start: hierarchical Bayesian shrinkage
**Problem:** `risk_score`'s empirical `OCE_FLOOR`/`OCE_MAX` normalization needs a
learner's own history to compute percentiles; a new user has none, so the score was
undefined or noisily false-alarming during the exact window that forms first impressions.

**Fix:** Seed thresholds from a **population prior** (pooled across the simulated
cohort), then blend toward the learner's own estimate as evidence accumulates:

```
effective_threshold = w * personal_estimate + (1 - w) * population_prior
w = n_sessions / (n_sessions + k)      # k ≈ 5 (shrinkage strength, tunable)
```

At session 1, `w ≈ 0.17` → mostly population prior. By session 20, `w ≈ 0.8` → mostly
personal. No undefined window, no day-one false alarms. **Report an uncertainty band**
alongside the point score (`risk 0.3 ± 0.25, low confidence — 3 sessions`).

**Known residual:** the population prior currently comes from our own simulator, which
is mildly circular. Documented honestly: *priors seeded from a simulated cohort; would
be reseeded from real users at scale.*

### Fix 2 — Drift: BOCPD instead of CUSUM/Page-Hinkley
**Problem:** CUSUM/Page-Hinkley assume a steady sample stream. Student logging is
sparse and bursty (2–3 sessions some days, none others) — a known failure mode that
yields false triggers or dead-conservative thresholds.

**Fix:** **Bayesian Online Change Point Detection** (Adams & MacKay, 2007). Maintains a
posterior over *run length* (observations since the last changepoint), updated one
observation at a time. Outputs a **changepoint probability**, not a brittle binary, so
the dashboard shows "drift likelihood rising" rather than a threshold that fires or
doesn't. Run-length is measured in observations, not calendar time, so gaps don't break it.

**Known residual:** a hazard-rate hyperparameter still needs tuning. CUSUM is kept as a
**documented baseline we evaluated and rejected** — one sentence in the writeup, not a
second codebase.

### Fix 3 — Recommendation impact: interrupted time series (+ documented randomized-delay)
**Problem:** With one user, no control, no randomization, "the rec worked" is
confounded with regression to the mean and natural variation. The v1 one-liner implied
causation the design couldn't support.

**Fix (shipped):** **Interrupted Time Series (ITS).** Model the metric trend *before* a
recommendation, extrapolate it forward as the counterfactual, and measure the deviation
after. Comparing against an extrapolated trend — not a single low point — is what
defuses regression-to-the-mean. Reframe as: *an n-of-1 study is a sample from a
population of time-periods within one person.*

**Fix (designed, not shipped):** a **randomized-delay** design — sometimes withhold or
delay a recommendation at random to create within-person treated/untreated periods, a
real single-case randomized experiment. Documented in the README with its UX tradeoff;
demonstrated **in the simulator only**, where withholding costs nothing. ~90% of the
interview credit for ~20% of the build.

**Known residuals:** ITS assumes a roughly linear baseline (real learning curves are
lumpy — stated as a limitation); randomization degrades UX (the reason it's simulator-only in v1).

---

## The scoped cut list (why v2 is finishable)

| Component | v1 plan | v2 decision | Rationale |
|---|---|---|---|
| RAG over history | full vector store | **structured retrieval** (SQL filter + templated context) | Corpus is dozens–hundreds of records; a vector store is overkill. LLM-structured-output signal shown elsewhere. "Too small to justify RAG, explained the tradeoff" is a *better* interview answer. |
| Randomized-causal design | (implied) | **designed + simulator-only** | Full withholding experiment is heavy and degrades UX. Documented design earns most of the credit. |
| CUSUM baseline | keep as baseline | **mention only, don't build** | One sentence in writeup; no second implementation. |
| Drift detection | full engine | **build if time; else stub + document** | First thing sacrificed if behind — risk + impact already carry the "cognitive engine" signal. Additive, not load-bearing. |
| Dashboard | full suite | **one compelling screen** | Trajectory + risk band + past-rec impact score. No settings/multi-user/live-polish. The demo is one screenshot-worthy view. |

**Cut principle:** keep everything with a *unique* interview signal; cut anything
expensive that duplicates a signal shown elsewhere. The cuts read as engineering
maturity ("I scoped these deliberately, here's my reasoning"), not as holes.

---

## v1 spine (the finishable path)

```
simulator ─▶ risk score (shrinkage) ─▶ ITS impact scoring ─▶ structured retrieval + LLM debrief ─▶ ONE dashboard screen
                                                              ▲
extension + on-device categorizer ──(live capture)───────────┘

stretch / documented-only: BOCPD drift · randomized-delay causal design
```

---

## The split at a glance

```
   YOU (product + brain + platform)          FRIEND (Focus-State Engine + QUALITY)
   ─────────────────────────────────          ────────────────────────────────────
   Browser Extension ──raw events──────────▶  Focus-State Engine
   (capture, on-device categorize)             - batch metrics
                                               - live focus-state classifier
   Public API (FastAPI)  ◀──metrics POST────   - nudge back to extension
     /ingest/session-metrics                   + owns ALL system test/quality:
   Cognitive Engine                              - ground-truth oracle / synthetic data
   (risk+shrinkage · ITS impact ·                - property-based tests
    BOCPD drift [stretch])                       - contract tests on both seams
   LLM + structured retrieval                    - integration / E2E
   Manual Log (confidence → calibration)         - CI gating + coverage
   Dashboard (one screen) · DevOps               - API testing
```

---

## The two cross-team contracts (unchanged, locked)

### Seam 1 — Events: your Extension → his Engine
```jsonc
{ "type": "session_start", "ts": <unix_ms>, "session_id": "string" }
{ "type": "focus_start",   "ts": <unix_ms>, "tab_category": "study" | "non_study" }
{ "type": "focus_end",     "ts": <unix_ms>, "tab_category": "study" | "non_study" }
{ "type": "switch",        "ts": <unix_ms>, "from_category": "...", "to_category": "..." }
{ "type": "session_end",   "ts": <unix_ms>, "session_id": "string" }
```
Categorization (study vs non_study) happens **in the extension, on-device** via the
signal-tier cascade in `categorizer.ts`. Binary for v1.

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
Formulas + constants (`SWITCH_MAX`, `FRAG_MAX`) locked in `API_CONTRACT.md`. Plus the
live nudge: `{ "type": "focus_state", "state": "deep_focus"|"steady"|"scattered", "ts": <unix_ms> }`.

Third contract — `RISK_CONTRACT.md` — locks `risk_score` (window, OCE formula, shrinkage,
freeze-at-compute provenance).

---

## Efficiency scorecard (v1 → v2)

| Component | v1 | v2 | What moved it |
|---|---:|---:|---|
| On-device categorizer | 8 | 8 | untouched — already right |
| Risk score / calibration | 6 | 8 | shrinkage closes cold-start; uncertainty band adds honesty |
| Drift detection | 5 | 8 | BOCPD fits sparse data; probability output not binary |
| Recommendation impact | 4 | 8 | ITS + documented randomization → survives scrutiny |
| Retrieval / LLM layer | 5 | 5 | now the weakest-justified; RAG→structured is the fix |
| Contract-first split | 9 | 9 | untouched — cleanest part |
| **Overall** | **~6** | **~8** | risk shifts from "will it hold up" to "can two people finish it" |

**What caps v2 below 9:** population-prior circularity (only real users fix it); the
retrieval layer is deliberately simple; implementation burden rose (shrinkage + BOCPD +
ITS are more to build *and* more for the collaborator to test).

---

## Build order

**Week 0 — together:** lock all three contracts (done), including formulas + constants
and the category rules list. **Decide simulator ownership** (see open decisions).

**Then parallel:**

*You:* DB + API skeleton (done) → **simulator** (now critical path — build first) →
risk engine with shrinkage → ITS impact scoring → structured retrieval + LLM debrief →
extension + categorizer wiring → one dashboard screen → Docker. *(BOCPD drift =
stretch.)*

*Friend:* event simulator + ground-truth cases → Focus-State Engine to pass them → live
classifier → wire to `/ingest/session-metrics` → cross-system test suite + CI as each
piece lands.

**Integration moment:** his engine POSTs real metrics to your live API; you swap
simulator-fed metrics for real ones. Your cognitive engine doesn't care about the
source — that's the seam working.

---

## Demo (what you show)

1. **Live:** study tab → jump to YouTube → back. Extension emits events (categorized
   on-device) → engine computes metrics + live state → dashboard updates; a nudge fires
   on `scattered`.
2. **Longitudinal:** load weeks of simulated history → dashboard shows the cognitive
   trajectory, the **risk score with its uncertainty band**, the calibration gap, a
   grounded recommendation, and — the headline — the **ITS impact score of a past
   recommendation** (with the randomized-delay design shown in the simulator).
3. **Quality:** green CI badge + coverage + "contract & property-based tests across both
   service boundaries."

---

## Open decisions

- **Simulator ownership (new, urgent).** The simulator is now the critical path for the
  entire demo, *and* the collaborator needs an event simulator as his core test fixture.
  If they're the same artifact — good. If they drift, that's two simulators to maintain.
  Resolve in a 10-minute conversation before either side writes simulator code.
- **Timeline** — target for first end-to-end demo (his engine POSTing real metrics).
- **API auth** — before any public/demo exposure; who owns it.
- **CI ownership** — when the collaborator stands up `.github/workflows/`.

---

## MVP boundaries

**In v1:** browser-only capture · on-device categorization · manual log · batch metrics
+ live classifier · risk score with shrinkage + uncertainty · ITS recommendation impact
· grounded LLM debrief over structured retrieval · one dashboard screen · CI with
contract + property tests.

**Stretch (build if time):** BOCPD drift detection · live randomized-delay causal design.

**Documented-only (designed, not shipped):** full randomized-withholding experiment ·
CUSUM baseline comparison.

**Later:** OS-level native agent · full RAG with embeddings · multi-agent eval ·
subject-level embeddings · per-concept risk · mobile.

**Deliberately avoided:** clinical claims. "Burnout prediction" is reframed as
*engagement/fatigue signals* — no medical/mental-health inference. Causal language is
reserved for the randomized design only; ITS results are reported as association.