"""Reference implementation of RISK_CONTRACT.md v1.0.

Importable by the cognitive engine as the canonical spec of the risk formula.
Running it directly (`python risk_ref.py`) executes the persona validation that
proves the math behaves. The demo is guarded under __main__ so importing these
functions has NO side effects.
"""
import numpy as np

# --- Tunable constants (RISK_CONTRACT.md §5) --------------------------------
# OCE_FLOOR / OCE_MAX are EMPIRICAL: set from reference distributions, not
# hardcoded. The values below are provisional bring-up defaults; recompute
# OCE_FLOOR as p90 of a well-calibrated corpus and OCE_MAX as p95 of an
# overconfident corpus once real/simulated logs exist.
HIGH_CONF = 0.7
N_BINS = 10
N_MIN = 8
DRIFT_BUMP = 0.25
OCE_FLOOR = 0.12   # provisional — noise band of a well-calibrated corpus
OCE_MAX = 0.75     # provisional — "clearly bad" ceiling of an overconfident corpus

CORRECTNESS = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}  # partial = half-wrong


def overconfidence_error(logs):
    """logs: iterable of (confidence, outcome_str). Returns raw OCE over the
    assessable logs, or None if fewer than N_MIN assessable logs (cold-start)."""
    assessable = [(c, CORRECTNESS[o]) for c, o in logs if o in CORRECTNESS]
    if len(assessable) < N_MIN:
        return None
    conf = np.array([c for c, _ in assessable])
    corr = np.array([v for _, v in assessable])
    edges = np.linspace(0, 1, N_BINS + 1)
    oce = 0.0
    n = len(assessable)
    for i in range(N_BINS):
        lo, hi = edges[i], edges[i + 1]
        m = (conf >= lo) & (conf < hi) if i < N_BINS - 1 else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        conf_b, acc_b = conf[m].mean(), corr[m].mean()
        oce += (m.sum() / n) * max(conf_b - acc_b, 0.0)  # overconfident direction only
    return float(oce)


def calibration_risk(logs):
    """Normalize OCE against the two reference bounds. None on cold-start."""
    oce = overconfidence_error(logs)
    if oce is None:
        return None, None
    cr = min(max((oce - OCE_FLOOR) / (OCE_MAX - OCE_FLOOR), 0.0), 1.0)
    return cr, oce


def risk_score(logs, drift_severity):
    """Full risk_score for one session's trailing window.
    Returns (score_or_None, detail_dict) matching risk_detail in RISK_CONTRACT.md §6."""
    cr, oce = calibration_risk(logs)
    if cr is None:
        n = len([o for _, o in logs if o in CORRECTNESS])
        return None, {"formula_version": "risk-1.0", "reason": "cold_start", "n_assessable": n}
    mult = 1 + DRIFT_BUMP * drift_severity
    rs = min(max(cr * mult, 0.0), 1.0)
    return rs, {
        "formula_version": "risk-1.0",
        "oce": round(oce, 3),
        "oce_floor": OCE_FLOOR,
        "oce_max": OCE_MAX,
        "calibration_risk": round(cr, 3),
        "drift_severity": drift_severity,
        "drift_multiplier": round(mult, 3),
    }


if __name__ == "__main__":
    rng = np.random.default_rng(0)

    def persona(conf_mu, acc_prob, n=20):
        out = []
        for _ in range(n):
            c = float(np.clip(rng.normal(conf_mu, 0.06), 0, 1))
            r = rng.random()
            o = "correct" if r < acc_prob else ("partial" if r < acc_prob + 0.1 else "incorrect")
            out.append((c, o))
        return out

    cases = {
        "confidently-wrong (.85/.20)": (persona(0.85, 0.20), 0.0),
        "mildly overconfident (.75/.55)": (persona(0.75, 0.55), 0.0),
        "well-calibrated (.70/.70)": (persona(0.70, 0.70), 0.0),
        "UNDERconfident (.35/.90)": (persona(0.35, 0.90), 0.0),
        "conf-wrong + drift .8": (persona(0.85, 0.20), 0.8),
        "cold-start (4 logs)": (persona(0.85, 0.20, n=4), 0.0),
    }
    print(f"{'persona':<34} {'risk':>6}   detail")
    print("-" * 92)
    for name, (logs, drift) in cases.items():
        rs, d = risk_score(logs, drift)
        val = "NULL" if rs is None else round(rs, 3)
        print(f"{name:<34} {str(val):>6}   {d}")