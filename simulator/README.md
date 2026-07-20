# Coogaih — Longitudinal Learner Simulator

Generates weeks of synthetic study history. It is the input to every remaining
stage of the v1 spine in `plan.md`, and it exists because `risk_score` is
defined over a trailing 10-session window (`RISK_CONTRACT.md` §2) and the repo
contains exactly one morning of sample data.

**One artifact, two consumers.** The same run produces @maniarockiaraj's test
fixture and your cognitive engine's fuel. That is the resolution to the
simulator-ownership question `plan.md` has flagged as urgent since July 4 —
you own the generator, he owns the assertions about what should be computed
from it.

---

## Run it

```powershell
python simulator\generate.py --seed 7 --sessions 30 --out simulator\out
python simulator\validate.py --out simulator\out --schema docs\schema.json
```

Cohort mode, for deriving the empirical constants:

```powershell
python simulator\generate.py --seed 7 --sessions 30 --cohort 40 --out simulator\out_cohort
python simulator\calibrate.py --out simulator\out_cohort
```

Requires `numpy` (already in `backend/requirements.txt`) and `jsonschema`.

---

## What comes out

| File | What it is | Who consumes it |
|---|---|---|
| `events.jsonl` | Normalized event envelopes per `DATA_CONTRACT.md` v1.0 | His Focus-State Engine; your extension pipeline |
| `sessions.jsonl` | Seam-2 payloads (`API_CONTRACT.md`), computed **from** the events using the locked formulas | POST straight to `/ingest/session-metrics`; also the oracle his engine must match |
| `manifest.json` | The answer key — true accuracy per session, changepoint index, planted recommendation level and slope | Validation code **only**. Never an input to the engine. |

`sessions.jsonl` being derived from `events.jsonl` rather than invented is the
important part. It means his engine and this generator can be pointed at the
same events and disagreement is a real bug in one of them, with
`API_CONTRACT.md` deciding which.

---

## The personas

Four mirror `RISK_CONTRACT.md` §4's reference table so those rows stay
reproducible from a named artifact. Three exist to make validation runnable:

- **`drifting`** — accuracy drops 0.75 → 0.25 at session 12. This is the
  changepoint `drift_severity.py` has to find, placed deliberately mid-run
  rather than at the tail, because that file documents its own false-negative
  mode on late breaks.
- **`responsive`** — the ITS case. Declining baseline (−0.018/session),
  recommendation at session 15, planted **level effect +0.18** and **slope
  effect +0.012/session**. A correct ITS implementation recovers those two
  numbers. A naive before/after comparison overstates the win, because part of
  the post-rec rise is just the counterfactual bottoming out.
- **`unresponsive_control`** — identical trajectory, no recommendation. If the
  ITS estimator reports an effect here, it is reading trend as treatment. A
  measurable false-positive rate rather than a hoped-for one.

---

## Verified on first run

Seed 7, 30 sessions, all seven personas — 2,885 events, 210 sessions:

```
[1] schema        2885/2885 events valid
[2] invariants    0 violation(s)   (379 manual_logs, 210 sessions)
[3] contract      210/210 sessions would POST cleanly
[4] determinism   reproduced  (sha256 647a40cd...)
```

OCE ordering over the generated logs reproduces §4's directional claims —
`underconfident` 0.000, `well_calibrated` 0.010, `confidently_wrong` 0.550.

### The constants are now empirical

280-learner cohort, windowed at `W_SIZE = 10` (the unit `risk_score` is
actually computed on, not whole-history):

| Corpus | n windows | percentile | value |
|---|---:|---|---:|
| well-calibrated (`well_calibrated` + `underconfident`) | 2006 | p90 | **`OCE_FLOOR = 0.104`** |
| overconfident (`mildly_overconfident` + `confidently_wrong`) | 2002 | p95 | **`OCE_MAX = 0.753`** |

`risk_ref.py` currently ships 0.12 / 0.75 marked "provisional bring-up
defaults." They were close — but they were guesses, and `RISK_CONTRACT.md` §5
says in bold that they must not be. They now have a re-runnable derivation.

Note `mildly_overconfident` lands at p90 = 0.340, comfortably above the floor.
That does **not** contradict the July finding that mild overconfidence scores
near zero: the floor absorbs the *median* window, and the spread is what makes
that row unstable as a reference point.

---

## Design decisions worth defending

**Determinism is a fix, not a nicety.** Every learner draws from a generator
seeded on `(seed, persona_index, learner_index)`. A shared RNG across personas
is precisely the bug that made `RISK_CONTRACT.md` §4's drift row describe a
different learner from its base row. Gate 4 in `validate.py` regenerates the
corpus from the manifest's own seed and compares hashes.

**Producers stay dumb.** Every event carries `category: null`, per
`DATA_CONTRACT.md` §2. The simulator is a producer and obeys the same rule —
which is what makes it a fair fixture for testing the categorizer rather than
a fixture that assumes the categorizer's answer.

**Surfaces resolve deterministically under `EXAMPLE_RULESET`.** The catalog
only uses containers that `categorizer.ts` classifies unambiguously, so a test
failure can't be blamed on a fixture judgement call. The `youtube.com` pair —
same container, opposite categories, split only by the title regex — is the
cheapest possible regression test that the tiered cascade actually cascades.

**Focus metrics share one latent.** `switching_rate`, `fragmentation` and
`distraction_ratio` are all driven by a single `focus_quality` value. That is
the collinearity `RISK_CONTRACT.md` §9 cites when it excludes focus metrics
from v1's risk score. Reproducing the weakness rather than hiding it is what
lets §7's decile/AUC test actually decide whether they add lift.

---

## One contract ambiguity this surfaced

`API_CONTRACT.md` states `distraction_ratio = non_study_time / total_session_time`.
Read literally, that folds `work`, `neutral` **and** idle time into the
numerator — a session spent answering email scores as distracted. The field's
*name* and its *formula* disagree, and both sides are currently free to assume
their own reading.

Implemented literally here so the oracle matches the locked document. Flagged
for the next shared-contract edit; it needs @maniarockiaraj's approval under
CODEOWNERS, so batch it with any other `docs/` changes rather than opening a
PR for it alone.

---

## Not built yet

- **A Postgres loader.** `sessions.jsonl` can be POSTed to
  `/ingest/session-metrics` today, but `manual_logs` have no write path — there
  is no endpoint for them. That gap is now on the critical path for the risk
  engine and is the natural next card.
- **Randomized-delay design.** `plan.md` scopes this as simulator-only. The
  `rec_at` hook is where it lands: randomize the index per learner and record
  the assignment in the manifest.
