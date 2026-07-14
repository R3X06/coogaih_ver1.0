# Coogaih — Risk Score Contract (v1.0)

This document locks the definition of `sessions.risk_score`. It is the single
source of truth for what the number means, how it is computed, and how it is
validated. The cognitive engine implements against *this file*; the dashboard
and the LLM narration read the numbers it defines.

Companion to `DATA_CONTRACT.md` (where `manual_log` comes from) and
`API_CONTRACT.md` (which states the ingest endpoint never sets `risk_score`).

---

## 1. What `risk_score` is

> **`risk_score` is a 0–1 index of the learner's current propensity toward a
> *confidently-wrong* outcome, computed deterministically by the cognitive
> engine over a trailing window of sessions.**

It is a **whole-learner** state, not per-concept (see §9). Higher = the learner
is more likely to be confident about things they have wrong. It is *not* a
distraction score, *not* a burnout/clinical signal, and *not* causal.

### The target event (observable — this is what makes the score validatable)

A **confidently-wrong event** is a resolved `manual_log` with:

```sql
confidence >= HIGH_CONF  AND  outcome IN ('incorrect', 'partial')
```

This is checkable in SQL today. It is the failure a *learning*-intelligence
system should care about: not "were they distracted," but "do they believe they
know something they don't." One such event is already in `sample_events.jsonl`
(confidence 0.7, outcome `incorrect` on ECE).

---

## 2. The window `W`

`W` = the **trailing 10 sessions** up to and including the session being scored
(`W_SIZE = 10`, tunable). Chosen over a days-window because it behaves sanely
across personas (a crammer's two days vs a steady learner's two weeks) and
matches how the demo scores per-session.

**Attribution of logs to `W`:** a `manual_log` belongs to `W` if its
`refers_to_session` points at a session in `W`. If `refers_to_session` is absent,
attribute by `created_at` falling within `[first_session.ts_start, scored_session.ts_end]`.

**Immutability.** Per `DATA_CONTRACT.md`, a `manual_log` is an instantaneous,
immutable event — its `outcome` is fixed at emit time, not "resolved later."
So `W`'s membership is stable once its sessions and logs exist. The only way an
old session's inputs change is a **late-arriving log** that refers back to a
session inside its window; §6 (freeze) handles that case explicitly.

---

**Drift amplification.** A deteriorating trend raises present risk:

```
risk_score = clamp( calibration_risk · (1 + DRIFT_BUMP · drift_severity), 0, 1 )
```

`drift_severity ∈ [0,1]` is the engine's normalized drift statistic
(CUSUM / Page-Hinkley) on the trailing correctness stream; 0 = stable, 1 = max
detected drift. Its internals are the engine's business; only this interface is
contractual.

--- WITH THIS ---

**Drift amplification.** A deteriorating trend raises present risk:

```
risk_score = clamp( calibration_risk · (1 + DRIFT_BUMP · drift_severity), 0, 1 )
```

`drift_severity ∈ [0,1]` is the engine's normalized drift statistic on the
trailing correctness stream; 0 = stable, 1 = max detected drift. Its internals
are the engine's business; only this interface is contractual — an
implementation may be swapped without a contract version bump, provided the
interface holds.

*Implementation status (see decision log ADR-003):*

- **v1 (current, interim): one-sided Page-Hinkley** over the trailing
  wrongness stream (`1 − correctness`), normalized against empirically
  calibrated floor/ceiling constants (same discipline as `OCE_FLOOR`/
  `OCE_MAX` in §5) — see `drift_severity.py`.
- **Target: BOCPD** (Bayesian Online Change Point Detection). Chosen over
  CUSUM/Page-Hinkley because student data is sparse and bursty, and
  calibration against the v1 implementation surfaced two concrete failure
  modes: (a) a sharp break can be missed entirely when too few samples
  follow it within the trailing window, and (b) gradual decline is
  under-detected relative to abrupt breaks. Both are expected weaknesses of
  Page-Hinkley, not implementation bugs — they are the reason BOCPD remains
  the target rather than a stretch nicety.
- Migration from v1 to v2 changes only `drift_severity()`'s internals; no
  change to `risk_score`, `risk_ref.py`, or this contract's public interface
  is required.

---

## 4. Reference behavior (from the validated reference implementation)

Directional check the engine's implementation must reproduce (monotone, zeros
where they belong):

| learner pattern                    | risk_score |
|------------------------------------|-----------:|
| well-calibrated (conf ≈ accuracy)  |       0.00 |
| **under**confident (humble, right) |       0.00 |
| mildly overconfident               |       ~0.36 |
| confidently-wrong                  |       ~0.47 |
| confidently-wrong + drifting       |       ~0.98 |
| < N_MIN assessable logs            |       NULL |

The underconfident → 0.00 row is the whole reason OCE is used instead of plain
ECE. Any implementation where a humble-and-right learner scores > 0 is wrong.

---

## 5. Tunable constants

Starting values, same discipline as `SWITCH_MAX` / `FRAG_MAX`: sanity-check
against real captured/simulated logs; whoever changes one notifies the other
side, because the engine's exclusion thresholds, the dashboard, and the property
tests all assume them.

| Constant       | Start | Meaning / how to set |
|----------------|------:|----------------------|
| `HIGH_CONF`    | 0.7   | threshold for a "confident" statement (defines the target event) |
| `N_BINS`       | 10    | ECE bin count |
| `N_MIN`        | 8     | min assessable logs in `W` before a score is defined |
| `W_SIZE`       | 10    | sessions in the trailing window |
| `DRIFT_BUMP`   | 0.25  | how much max drift amplifies risk (×1.25 at drift 1.0) |
| `OCE_FLOOR`    | ~0.12 | **empirical** — p90 OCE of a well-calibrated corpus. Do NOT hardcode long-term. |
| `OCE_MAX`      | ~0.75 | **empirical** — p95 OCE of an overconfident corpus. Do NOT hardcode long-term. |

**Why `OCE_FLOOR`/`OCE_MAX` must be empirical, not guessed:** a single hardcoded
cap was tried and demonstrably fails. With ~20 logs, well-calibrated data still
produces ~0.12 OCE from pure binning noise; dividing by any small fixed number
inflates a perfectly-calibrated learner to a near-1.0 score (it cries wolf). The
floor absorbs the noise band; the ceiling anchors "clearly bad." Both come from
reference distributions, recomputed when the corpus grows.

---

## 6. Who computes it, when, and freeze semantics

- **Not on ingest.** `POST /ingest/session-metrics` never touches `risk_score`
  (already stated in `API_CONTRACT.md`). A dedicated **engine pass** computes it.
- **Trigger:** after a session's metrics and its assessable logs exist (or a
  batch pass). Computes the newest session.
- **Freeze-at-compute (default).** Once written, `risk_score`, `risk_detail`,
  and `risk_computed_at` are **immutable**. This guarantees a reproducible demo:
  the score reflects what was known at compute time. A late-arriving log about a
  past session does **not** silently rewrite history; a recompute is an explicit,
  logged operation, never an automatic side effect.
- **Provenance.** `risk_detail` (jsonb) stores the frozen inputs so the score is
  auditable and the LLM narration stays grounded ("narrates numbers the engine
  computed"):

```json
{
  "formula_version": "risk-1.0",
  "window_session_ids": ["…", "…"],
  "n_assessable": 12,
  "oce": 0.184,
  "oce_floor": 0.121,
  "oce_max": 0.754,
  "calibration_risk": 0.099,
  "drift_severity": 0.10,
  "drift_multiplier": 1.025
}
```

---

## 7. Validation protocol (how you *prove* the score predicts)

Because the target is observable, the score can be validated against itself —
reusing the calibration tooling recursively:

1. For each session `S` with a defined `risk_score`, look forward a fixed horizon
   `H` (default: next 3 sessions). Label `y_S = 1` if a confidently-wrong event
   occurs in `H`, else 0.
2. Bucket sessions by `risk_score` decile; plot observed `y=1` rate per decile.
   A monotone-increasing curve = the score has signal.
3. Report **decile lift** and **AUC** (risk_score as a continuous predictor of `y`).

This converts "I built a risk score" into "here is the evidence it predicts."

**Recommendation-impact link (correlational, not causal).** A recommendation
"worked" if, in the window after it was given, *both* `risk_score` and the
observed confidently-wrong rate dropped. Single-user, uncontrolled → report as
correlational only. Do not claim causation.

---

## 8. Schema changes this contract requires

Applied by `db/migrations/001_risk_contract.sql` (and reflected in `schema.sql`):

1. `manual_logs.outcome`: `boolean` → `text CHECK (… IN ('correct','incorrect','partial','na'))`.
   The old boolean could not represent `partial`, which §3 requires. Fixes a live
   `schema.sql` ↔ `DATA_CONTRACT.md`/`schema.json` drift.
2. `manual_logs.topic` → `manual_logs.concept`, to match the `manual_log` payload
   in `DATA_CONTRACT.md`/`schema.json`. (Second live drift, fixed in passing.)
3. `sessions`: add `risk_computed_at timestamptz`, `risk_detail jsonb` for §6.

---

## 9. What `risk_score` does NOT do

- **Not causal.** Recommendation impact (§7) is correlational, single-user.
- **Not clinical.** No burnout/mental-health inference — consistent with `plan.md`.
- **Not per-concept** in v1. It is a whole-learner state. `sessions` do not link
  to concepts, and per-concept scoring needs the embeddings explicitly deferred
  to "later." Claiming per-concept risk now would be uncomputable against the
  current schema.
- **Not on ingest**, and **does not use focus metrics** in v1. `switching_rate` /
  `fragmentation` / `distraction_ratio` are indirect, mutually collinear, and
  unvalidated against outcomes. A single `focus_quality_risk = mean(...)` sub-score
  is defined for the future but is folded in **only after** §7's decile/AUC curve
  shows it adds predictive lift — not before.
- **Does not mutate once frozen** (§6), except by explicit, logged recompute.

---

## 10. Versioning

`formula_version = "risk-1.0"`, stored in every `risk_detail`. Any change to the
formula bumps this and requires recompute of scores meant to be compared.
Constant changes are notified to both sides (see §5).