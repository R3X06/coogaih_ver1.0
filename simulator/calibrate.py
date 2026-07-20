"""Compute OCE_FLOOR and OCE_MAX from a simulated cohort.

RISK_CONTRACT.md §5 defines these two constants as percentiles of reference
distributions, and says in bold that they must be empirical rather than
guessed. Until now they could not be: `risk_ref.py` carries 0.12 and 0.75
labelled "provisional bring-up defaults" because there was no corpus to take a
percentile of. This script is that corpus.

    OCE_FLOOR = p90 of OCE over a WELL-CALIBRATED reference corpus
    OCE_MAX   = p95 of OCE over an OVERCONFIDENT reference corpus

Granularity matters and is easy to get wrong: OCE is sampled over a TRAILING
W_SIZE-session WINDOW, not over a learner's whole history, because that is the
unit `risk_score` is actually computed on. A floor calibrated on 30 sessions
of data would sit far below the noise level of a real 10-session window and
the score would cry wolf — the exact failure §5 describes.

Circularity, stated plainly: the prior comes from our own simulator, so this
proves the pipeline recovers the distribution we planted, not that the
distribution matches real learners. `plan.md` already flags this as a known
residual. It would be reseeded from real users at scale.

Usage:
    python -m simulator.generate --cohort 40 --sessions 30 --out simulator/out_cohort
    python -m simulator.calibrate --out simulator/out_cohort
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from personas import WELL_CALIBRATED_CORPUS, OVERCONFIDENT_CORPUS

W_SIZE = 10     # RISK_CONTRACT.md §2
N_MIN = 8       # RISK_CONTRACT.md §5
N_BINS = 10
CORRECTNESS = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}


def oce(logs) -> float | None:
    """Inlined so this script has no import dependency on backend/ — it must be
    runnable before the engine package is importable. Kept identical to
    risk_ref.overconfidence_error(); any divergence is a bug."""
    a = [(c, CORRECTNESS[o]) for c, o in logs if o in CORRECTNESS]
    if len(a) < N_MIN:
        return None
    conf = np.array([c for c, _ in a])
    corr = np.array([v for _, v in a])
    edges = np.linspace(0, 1, N_BINS + 1)
    total, n = 0.0, len(a)
    for i in range(N_BINS):
        lo, hi = edges[i], edges[i + 1]
        m = (conf >= lo) & (conf < hi) if i < N_BINS - 1 else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        total += (m.sum() / n) * max(conf[m].mean() - corr[m].mean(), 0.0)
    return float(total)


def windowed_oce(out: Path) -> dict[str, list[float]]:
    events = [json.loads(l) for l in (out / "events.jsonl").open() if l.strip()]
    manifest = json.loads((out / "manifest.json").read_text())

    by_session: dict[str, list[tuple]] = {}
    for e in events:
        if e["kind"] != "manual_log":
            continue
        ref = e["payload"].get("refers_to_session")
        by_session.setdefault(ref, []).append(
            (e["payload"]["confidence"], e["payload"]["outcome"]))

    per_persona: dict[str, list[float]] = {}
    for lm in manifest["learners"]:
        ids = [s["session_id"] for s in lm["sessions"]]
        vals = []
        for i in range(len(ids)):
            window = ids[max(0, i - W_SIZE + 1): i + 1]
            logs = [p for sid in window for p in by_session.get(sid, [])]
            v = oce(logs)
            if v is not None:
                vals.append(v)
        per_persona.setdefault(lm["persona"], []).extend(vals)
    return per_persona


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="simulator/out_cohort")
    args = ap.parse_args()

    per = windowed_oce(Path(args.out))

    print(f"{'persona':<24}{'windows':>9}{'p50':>8}{'p90':>8}{'p95':>8}")
    print("-" * 57)
    for name, vals in per.items():
        if not vals:
            print(f"{name:<24}{0:>9}{'—':>8}{'—':>8}{'—':>8}")
            continue
        a = np.array(vals)
        print(f"{name:<24}{len(a):>9}{np.percentile(a,50):>8.3f}"
              f"{np.percentile(a,90):>8.3f}{np.percentile(a,95):>8.3f}")

    wc = np.array([v for n in WELL_CALIBRATED_CORPUS for v in per.get(n, [])])
    oc = np.array([v for n in OVERCONFIDENT_CORPUS for v in per.get(n, [])])
    if wc.size == 0 or oc.size == 0:
        raise SystemExit("\nreference corpora empty — generate with all personas")

    floor = float(np.percentile(wc, 90))
    ceil = float(np.percentile(oc, 95))

    print(f"\nwell-calibrated corpus   n={wc.size:<6} p90 -> OCE_FLOOR = {floor:.3f}")
    print(f"overconfident corpus     n={oc.size:<6} p95 -> OCE_MAX   = {ceil:.3f}")
    print(f"\nrisk_ref.py currently ships OCE_FLOOR = 0.12, OCE_MAX = 0.75 (provisional)")
    if ceil <= floor:
        print("\nWARNING: ceiling <= floor. The two corpora do not separate; "
              "the normalization would be degenerate.")


if __name__ == "__main__":
    main()
