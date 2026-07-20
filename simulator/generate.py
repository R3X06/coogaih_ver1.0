"""Coogaih — longitudinal learner simulator.

Generates weeks of synthetic study history for one or more learners. Three
artifacts come out of a single run, and the fact that it is a SINGLE run is
the whole design:

  events.jsonl    normalized event envelopes (DATA_CONTRACT.md v1.0 /
                  docs/schema.json). Stands in for the browser extension for
                  your half, and is @maniarockiaraj's core test fixture for
                  his. One corpus, two consumers, no second simulator.

  sessions.jsonl  the Seam-2 payloads (API_CONTRACT.md), computed FROM the
                  events above using the locked formulas. This is the
                  ground-truth oracle: his Focus-State Engine consumes
                  events.jsonl and must reproduce these numbers. Until his
                  engine exists, you POST these directly to
                  /ingest/session-metrics and stay unblocked.

  manifest.json   what was actually planted — true accuracy per session,
                  changepoint locations, and the recommendation's real level
                  and slope effect. Nothing downstream may read this except
                  validation code. It is the answer key, not an input.

Determinism: every learner gets its own seeded generator derived from
(seed, persona_index, learner_index). Same seed in, byte-identical corpus out.
This is not decoration — it is the fix for the exact bug that corrupted
RISK_CONTRACT.md §4's reference table, where a shared RNG meant the base row
and the drift row silently described two different learners.

Usage:
    python -m simulator.generate --seed 7 --sessions 30 --out simulator/out
    python -m simulator.generate --cohort 40 --out simulator/out_cohort
"""
from __future__ import annotations

import argparse
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from personas import PERSONAS, Persona

# --- Locked constants -------------------------------------------------------
# SWITCH_MAX / FRAG_MAX are NOT ours to choose — they are copied from
# API_CONTRACT.md. If they change there, they change here, and both the
# dashboard and the property tests move with them (that doc says so
# explicitly). Duplicating them silently is how contracts drift; this comment
# is the tripwire.
SWITCH_MAX = 0.5
FRAG_MAX = 0.2

SCHEMA_VERSION = "1.0"
LOCAL_OFFSET_MIN = 480          # SGT
SOURCE = "simulator"            # DATA_CONTRACT.md §3 permits `simulator` for any kind
START_DATE = datetime(2026, 3, 2, tzinfo=timezone.utc)  # fixed, so runs are reproducible

MS_MIN = 60_000


# ---------------------------------------------------------------------------
# Surface catalog.
#
# Every container here resolves DETERMINISTICALLY under EXAMPLE_RULESET in
# extension/src/categorize/categorizer.ts. That is deliberate: the fixture
# must not depend on a categorization judgement call, or a test failure can't
# distinguish "the engine is wrong" from "the fixture was ambiguous".
#
# The youtube.com pair is the interesting one — same container, opposite
# categories, split only by the title regex. It is the cheapest possible
# regression test that the tiered cascade actually cascades.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Surface:
    ctype: str          # 'app' | 'domain'
    container: str
    titles: tuple[str, ...]
    category: str       # ground-truth category under EXAMPLE_RULESET

STUDY_SURFACES = (
    Surface("app", "Code",
            ("problem_set_3.py — coogaih-hw", "calibration_utils.py — coogaih-hw",
             "risk_ref.py — coogaih"), "study"),
    Surface("domain", "leetcode.com",
            ("Two Sum - LeetCode", "Binary Search - LeetCode"), "study"),
    Surface("domain", "coursera.org",
            ("Calibration — Week 3", "Bayesian Methods — Week 5"), "study"),
    # polymorphic container rescued into `study` by the title regex
    Surface("domain", "youtube.com",
            ("Intro to Expected Calibration Error - Lecture 4",
             "Change Point Detection Tutorial"), "study"),
)
WORK_SURFACES = (
    Surface("app", "Slack", ("#coogaih-project",), "work"),
    Surface("app", "Mail", ("Inbox — university",), "work"),
)
DISTRACTION_SURFACES = (
    # same container as the study YouTube entry above, no regex match -> fallback
    Surface("domain", "youtube.com",
            ("Why I Quit My 9-5 to Study Full Time",
             "I Tried Studying 12 Hours a Day"), "distraction"),
)
NEUTRAL_SURFACES = (
    # unknown container -> default_fallthrough, tier='unknown', needsReview
    Surface("domain", "news.ycombinator.com", ("Hacker News",), "neutral"),
)

CONCEPTS = (
    "Expected Calibration Error", "Overconfidence Error", "Page-Hinkley test",
    "Bayesian changepoint detection", "Interrupted time series",
    "Regression to the mean", "Idempotent upsert", "Hierarchical shrinkage",
)


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------
def _rng(seed: int, persona_idx: int, learner_idx: int) -> np.random.Generator:
    return np.random.default_rng([seed, persona_idx, learner_idx])


def _uuid(rng: np.random.Generator) -> str:
    return str(uuid.UUID(bytes=bytes(rng.integers(0, 256, 16, dtype=np.uint8)), version=4))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _envelope(rng, ts, kind, duration_ms, payload) -> dict:
    """One normalized event. `category` is ALWAYS null — DATA_CONTRACT.md §2 is
    explicit that producers never categorize; the enrich stage does. The
    simulator is a producer and obeys the same rule, which is exactly what
    makes it a fair fixture for testing the categorizer."""
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": _uuid(rng),
        "ts": _iso(ts),
        "local_offset_min": LOCAL_OFFSET_MIN,
        "source": SOURCE,
        "kind": kind,
        "duration_ms": duration_ms,
        "category": None,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Session construction
# ---------------------------------------------------------------------------
@dataclass
class Span:
    surface: Surface | None     # None => afk
    duration_ms: int
    category: str               # 'afk' for idle spans


def _build_spans(rng: np.random.Generator, quality: float) -> list[Span]:
    """Lay out one session as a contiguous run of spans.

    `quality` (0..1) is the only knob: it lengthens study blocks and suppresses
    interruptions simultaneously. That coupling is intentional and is worth
    knowing about — it means switching_rate, fragmentation and
    distraction_ratio all inherit a single latent, which is precisely the
    collinearity RISK_CONTRACT.md §9 cites when it excludes focus metrics from
    v1's risk score. The simulator reproduces the weakness rather than hiding
    it, so the §7 validation can actually test whether those metrics add lift.
    """
    q = float(min(max(quality, 0.05), 0.95))
    target_ms = int(rng.integers(35, 96) * MS_MIN)

    p_distract = 0.42 * (1 - q)
    p_work = 0.12
    p_neutral = 0.10 * (1 - q)
    p_afk = 0.07

    study_mean_min = 4.0 + 16.0 * q

    spans: list[Span] = []
    elapsed = 0
    # always open on study — a session is a study session by definition
    first = STUDY_SURFACES[rng.integers(len(STUDY_SURFACES))]
    d = int(max(2.0, rng.gamma(3.0, study_mean_min / 3.0)) * MS_MIN)
    spans.append(Span(first, d, "study"))
    elapsed += d

    while elapsed < target_ms:
        r = rng.random()
        if r < p_afk:
            d = int(rng.integers(3, 10) * MS_MIN)
            spans.append(Span(None, d, "afk"))
        elif r < p_afk + p_distract:
            s = DISTRACTION_SURFACES[rng.integers(len(DISTRACTION_SURFACES))]
            d = int(rng.integers(2, 9) * MS_MIN)
            spans.append(Span(s, d, s.category))
        elif r < p_afk + p_distract + p_work:
            s = WORK_SURFACES[rng.integers(len(WORK_SURFACES))]
            d = int(rng.integers(2, 7) * MS_MIN)
            spans.append(Span(s, d, s.category))
        elif r < p_afk + p_distract + p_work + p_neutral:
            s = NEUTRAL_SURFACES[rng.integers(len(NEUTRAL_SURFACES))]
            d = int(rng.integers(1, 5) * MS_MIN)
            spans.append(Span(s, d, s.category))
        else:
            s = STUDY_SURFACES[rng.integers(len(STUDY_SURFACES))]
            d = int(max(2.0, rng.gamma(3.0, study_mean_min / 3.0)) * MS_MIN)
            spans.append(Span(s, d, "study"))
        elapsed += spans[-1].duration_ms

    return spans


def _spans_to_events(rng, ts_start: datetime, spans: list[Span]) -> list[dict]:
    """Render spans as envelopes.

    A domain surface emits TWO aligned events — a `focus` span on the browser
    app plus a `browse` span inside it — because that is what DATA_CONTRACT.md
    §3.2 describes and it forces the consumer to solve the alignment problem
    for real rather than against a simplified fixture.
    """
    events: list[dict] = []
    t = ts_start
    for sp in spans:
        if sp.surface is None:
            events.append(_envelope(rng, t, "afk", sp.duration_ms, {"reason": "idle"}))
        else:
            title = sp.surface.titles[rng.integers(len(sp.surface.titles))]
            if sp.surface.ctype == "app":
                events.append(_envelope(rng, t, "focus", sp.duration_ms, {
                    "app": sp.surface.container,
                    "window_title": title,
                }))
            else:
                events.append(_envelope(rng, t, "focus", sp.duration_ms, {
                    "app": "Chrome",
                    "window_title": title,
                }))
                events.append(_envelope(rng, t, "browse", sp.duration_ms, {
                    "domain": sp.surface.container,
                    "page_title": title,
                    "tab_id": int(rng.integers(10, 60)),
                }))
        t += timedelta(milliseconds=sp.duration_ms)
    return events


def _metrics(spans: list[Span], session_id: str, user_id: str,
             ts_start: datetime, ts_end: datetime) -> dict:
    """Compute the Seam-2 payload from spans using API_CONTRACT.md's locked
    formulas verbatim. This function is the oracle — if his engine and this
    disagree on the same events.jsonl, exactly one of them is wrong, and the
    contract says which.
    """
    total_ms = sum(s.duration_ms for s in spans)
    afk_ms = sum(s.duration_ms for s in spans if s.category == "afk")
    active_ms = total_ms - afk_ms
    study_ms = sum(s.duration_ms for s in spans if s.category == "study")

    # A `focus` event per non-afk span. DATA_CONTRACT.md §3.1: "the number of
    # focus events in a time window = the number of app switches".
    switches = sum(1 for s in spans if s.category != "afk")

    # Contiguous study runs. Anything non-study — including afk — closes a block.
    blocks: list[int] = []
    run = 0
    for s in spans:
        if s.category == "study":
            run += s.duration_ms
        elif run:
            blocks.append(run)
            run = 0
    if run:
        blocks.append(run)

    active_min = active_ms / MS_MIN
    study_min = study_ms / MS_MIN

    switching_rate = min(max((switches / active_min) / SWITCH_MAX, 0.0), 1.0) if active_min else 0.0
    fragmentation = (min(max((len(blocks) / study_min) / FRAG_MAX, 0.0), 1.0)
                     if study_min else 0.0)
    avg_block_min = (sum(blocks) / len(blocks)) / MS_MIN if blocks else 0.0

    # NOTE — a real ambiguity in API_CONTRACT.md, not a choice made lightly.
    # The contract states `distraction_ratio = non_study_time / total_session_time`.
    # Taken literally that folds `work`, `neutral` AND idle time into the
    # numerator, so a session spent answering email scores as "distracted".
    # Implemented literally here so the oracle matches the locked doc; flagged
    # for the next shared-contract edit, since the field NAME and the FORMULA
    # disagree and both sides currently assume their own reading.
    distraction_ratio = (total_ms - study_ms) / total_ms if total_ms else 0.0

    return {
        "session_id": session_id,
        "user_id": user_id,
        "ts_start": _iso(ts_start),
        "ts_end": _iso(ts_end),
        "switching_rate": round(switching_rate, 4),
        "avg_focus_block_minutes": round(avg_block_min, 3),
        "fragmentation": round(fragmentation, 4),
        "distraction_ratio": round(min(max(distraction_ratio, 0.0), 1.0), 4),
    }


def _category_ms(spans: list[Span]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in spans:
        out[s.category] = out.get(s.category, 0) + s.duration_ms
    return out


# ---------------------------------------------------------------------------
# Manual logs
# ---------------------------------------------------------------------------
def _manual_logs(rng, persona: Persona, i: int, session_id: str,
                 ts_start: datetime, session_ms: int) -> tuple[list[dict], list[tuple]]:
    """Emit this session's manual_log events plus the (confidence, outcome)
    pairs for the manifest.

    `outcome` is drawn against persona.accuracy_at(i) — the TRUE accuracy —
    while `confidence` is drawn against persona.conf_mu, independently. The
    calibration gap is therefore a planted quantity, not an emergent accident.
    """
    n = int(min(rng.poisson(persona.logs_per_session), 4))
    acc = persona.accuracy_at(i)
    events, pairs = [], []
    for k in range(n):
        conf = float(np.clip(rng.normal(persona.conf_mu, persona.conf_sigma), 0.02, 0.98))
        if rng.random() < persona.na_rate:
            outcome = "na"
        else:
            r = rng.random()
            outcome = ("correct" if r < acc
                       else "partial" if r < acc + persona.partial_band
                       else "incorrect")
        difficulty = int(np.clip(round(1 + 4 * (1 - conf) + rng.normal(0, 0.6)), 1, 5))
        offset = int((k + 1) / (n + 1) * session_ms)
        payload = {
            "concept": CONCEPTS[rng.integers(len(CONCEPTS))],
            "confidence": round(conf, 2),
            "perceived_difficulty": difficulty,
            "outcome": outcome,
            "refers_to_session": session_id,
        }
        events.append(_envelope(rng, ts_start + timedelta(milliseconds=offset),
                                "manual_log", None, payload))
        pairs.append((round(conf, 2), outcome))
    return events, pairs


# ---------------------------------------------------------------------------
# Learner
# ---------------------------------------------------------------------------
def generate_learner(persona: Persona, n_sessions: int, seed: int,
                     persona_idx: int, learner_idx: int) -> tuple[list[dict], list[dict], dict]:
    rng = _rng(seed, persona_idx, learner_idx)
    user_id = _uuid(rng)

    events: list[dict] = []
    sessions: list[dict] = []
    session_truth: list[dict] = []

    day = START_DATE
    i = 0
    while i < n_sessions:
        # Bursty cadence: some days nothing, some days three sittings. This is
        # the sparsity that plan.md Fix 2 says breaks CUSUM/Page-Hinkley — the
        # simulator has to reproduce it or the drift work is untested.
        r = rng.random()
        n_today = 0 if r < 0.34 else 1 if r < 0.74 else 2 if r < 0.93 else 3

        for slot in range(n_today):
            if i >= n_sessions:
                break
            hour = [9, 14, 20][slot]
            ts_start = day.replace(hour=hour, minute=int(rng.integers(0, 45)))

            quality = float(np.clip(
                rng.normal(persona.focus_quality, persona.focus_quality_sigma), 0.05, 0.95))
            spans = _build_spans(rng, quality)
            session_ms = sum(s.duration_ms for s in spans)
            ts_end = ts_start + timedelta(milliseconds=session_ms)
            session_id = _uuid(rng)

            events.extend(_spans_to_events(rng, ts_start, spans))
            log_events, pairs = _manual_logs(rng, persona, i, session_id, ts_start, session_ms)
            events.extend(log_events)

            sessions.append(_metrics(spans, session_id, user_id, ts_start, ts_end))

            assessable = [o for _, o in pairs if o in ("correct", "incorrect", "partial")]
            observed = (sum(1.0 if o == "correct" else 0.5 if o == "partial" else 0.0
                            for o in assessable) / len(assessable)) if assessable else None
            session_truth.append({
                "index": i,
                "session_id": session_id,
                "ts_start": _iso(ts_start),
                "true_accuracy": round(persona.accuracy_at(i), 4),
                "observed_correctness": None if observed is None else round(observed, 4),
                "n_assessable": len(assessable),
                "focus_quality": round(quality, 3),
                "post_recommendation": persona.rec_at is not None and i >= persona.rec_at,
                "post_changepoint": persona.drift_at is not None and i >= persona.drift_at,
                "category_ms": _category_ms(spans),
            })
            i += 1
        day += timedelta(days=1)

    rec_session = (session_truth[persona.rec_at]["session_id"]
                   if persona.rec_at is not None and persona.rec_at < len(session_truth) else None)
    drift_session = (session_truth[persona.drift_at]["session_id"]
                     if persona.drift_at is not None and persona.drift_at < len(session_truth) else None)

    manifest = {
        "user_id": user_id,
        "persona": persona.name,
        "params": persona.as_manifest(),
        "ground_truth": {
            "recommendation_at_index": persona.rec_at,
            "recommendation_session_id": rec_session,
            "true_level_effect": persona.rec_level,
            "true_slope_effect": persona.rec_slope,
            "baseline_slope": persona.baseline_slope,
            "changepoint_at_index": persona.drift_at,
            "changepoint_session_id": drift_session,
            "changepoint_delta": persona.drift_delta,
        },
        "sessions": session_truth,
    }
    return events, sessions, manifest


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Coogaih longitudinal learner simulator")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sessions", type=int, default=30, help="sessions per learner")
    ap.add_argument("--cohort", type=int, default=1,
                    help="learners PER persona (use ~40 to compute OCE_FLOOR/OCE_MAX)")
    ap.add_argument("--personas", type=str, default="",
                    help="comma-separated persona names; default = all")
    ap.add_argument("--out", type=str, default="simulator/out")
    args = ap.parse_args()

    names = ([n.strip() for n in args.personas.split(",") if n.strip()]
             or list(PERSONAS.keys()))
    unknown = [n for n in names if n not in PERSONAS]
    if unknown:
        raise SystemExit(f"unknown persona(s): {unknown}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    all_events, all_sessions, manifests = [], [], []
    for p_idx, name in enumerate(names):
        for l_idx in range(args.cohort):
            ev, se, mf = generate_learner(PERSONAS[name], args.sessions,
                                          args.seed, p_idx, l_idx)
            mf["persona_index"] = p_idx
            mf["learner_index"] = l_idx
            all_events.extend(ev)
            all_sessions.extend(se)
            manifests.append(mf)

    all_events.sort(key=lambda e: e["ts"])

    with (out / "events.jsonl").open("w") as f:
        for e in all_events:
            f.write(json.dumps(e) + "\n")
    with (out / "sessions.jsonl").open("w") as f:
        for s in all_sessions:
            f.write(json.dumps(s) + "\n")
    with (out / "manifest.json").open("w") as f:
        json.dump({
            "seed": args.seed,
            "sessions_per_learner": args.sessions,
            "cohort_per_persona": args.cohort,
            "start_date": _iso(START_DATE),
            "switch_max": SWITCH_MAX,
            "frag_max": FRAG_MAX,
            "learners": manifests,
        }, f, indent=2)

    print(f"learners      {len(manifests)}")
    print(f"events        {len(all_events)}  -> {out/'events.jsonl'}")
    print(f"sessions      {len(all_sessions)}  -> {out/'sessions.jsonl'}")
    print(f"manifest                -> {out/'manifest.json'}")


if __name__ == "__main__":
    main()
