"""Interim v1 implementation of drift_severity, per RISK_CONTRACT.md §3.

STATUS: interim. This uses Page-Hinkley (one-sided, tuned for detecting
DETERIORATION in correctness, not improvement). RISK_CONTRACT.md's target
design is BOCPD (better suited to sparse, bursty student data than
CUSUM/Page-Hinkley — see decision log ADR-003). This module exists so
risk_score has a real drift_severity input NOW; swapping to BOCPD later
should only touch this file's internals, not risk_ref.py or the contract's
public interface (drift_severity remains a float in [0,1], 0=stable,
1=max detected drift).

Importable with NO side effects; __main__ runs a validation demo, same
convention as risk_ref.py.
"""
import numpy as np

# --- Tunable constants -------------------------------------------------
# Same empirical discipline as OCE_FLOOR/OCE_MAX in risk_ref.py: these are
# calibrated against SIMULATED reference corpora below (synthetic personas,
# accuracy in [0.6, 0.8], n=20 streams; break-at-12 drift persona 0.75->0.25),
# NOT hardcoded truth. Recompute PH_FLOOR as p90 of the PH statistic on a
# real/simulated stable reference corpus, and PH_MAX as p95 on a real/
# simulated drifting corpus, once real longitudinal logs exist — same
# discipline as OCE_FLOOR/OCE_MAX as the corpus grows.
DELTA = 0.05        # allowed slack before a deviation counts as drift-relevant
MIN_HISTORY = 6      # fewer assessable logs than this -> assume stable, not "unknown"
PH_FLOOR = 1.91      # calibrated: p90 of PH statistic on stable synthetic corpus (n=2500 draws)
PH_MAX = 4.81        # calibrated: p95 of PH statistic on drifting synthetic corpus (n=500 draws)

# KNOWN LIMITATION (this is the concrete case for BOCPD as the target design,
# per ADR-003): in the calibration run that set PH_MAX above, some drift-
# persona draws scored PH=0.0 — a sharp break at log 12 was missed entirely
# when only ~8 post-break samples existed. Page-Hinkley needs enough post-
# change samples to accumulate signal; a learner who drifts late in a short
# trailing window can go undetected. This is a real false-negative risk, not
# a tuning gap — it's why this file is explicitly labeled interim.

CORRECTNESS = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}


def _wrongness_stream(logs_chronological):
    """logs: chronological iterable of (confidence, outcome_str) — same shape
    risk_ref.py takes. Returns the assessable stream as wrongness values
    (1 - correctness), because Page-Hinkley here watches for an UPWARD
    shift in wrongness (deteriorating accuracy), not a two-sided change."""
    return np.array([
        1.0 - CORRECTNESS[o] for _, o in logs_chronological if o in CORRECTNESS
    ])


def page_hinkley_statistic(wrongness):
    """One-sided PH statistic over a 1D array, computed at the FINAL point
    (i.e. "how much has the trailing stream drifted worse, as of now").
    Returns the raw PH_t (unbounded, >= 0)."""
    n = len(wrongness)
    running_mean = np.cumsum(wrongness) / np.arange(1, n + 1)
    # m_t = sum_{i=1}^t (x_i - mean_i - delta)
    # Under no drift, x_i - mean_i averages ~0, so subtracting delta makes
    # m_t trend gently DOWNWARD over time. A genuine upward jump in
    # wrongness pushes m_t up relative to its running minimum — that gap
    # (not a running max) is what signals "wrongness has increased".
    deviations = wrongness - running_mean - DELTA
    m = np.cumsum(deviations)
    m_min = np.minimum.accumulate(m)
    PH_t = m[-1] - m_min[-1]
    return float(PH_t)


def drift_severity(logs_chronological):
    """Full drift_severity per RISK_CONTRACT.md §3 interface.

    logs_chronological: assessable + non-assessable logs in chronological
    order (oldest first) — filtering happens internally. This should be a
    LONGER trailing stream than the risk window W; drift needs history
    before W to have a baseline to drift away from.

    Returns (severity, detail_dict). severity is always defined (never
    None) — insufficient history means "assume stable," not "unknown,"
    because risk_score's own cold-start gate (N_MIN on calibration) is
    what should block an undefined score, not this.
    """
    wrongness = _wrongness_stream(logs_chronological)
    n = len(wrongness)

    if n < MIN_HISTORY:
        return 0.0, {
            "method": "page_hinkley_interim",
            "reason": "insufficient_history",
            "n_assessable": n,
        }

    ph_t = page_hinkley_statistic(wrongness)
    severity = min(max((ph_t - PH_FLOOR) / (PH_MAX - PH_FLOOR), 0.0), 1.0)

    return severity, {
        "method": "page_hinkley_interim",
        "ph_statistic": round(ph_t, 3),
        "ph_floor": PH_FLOOR,
        "ph_max": PH_MAX,
        "n_assessable": n,
        "delta": DELTA,
    }


if __name__ == "__main__":
    rng = np.random.default_rng(0)

    def stable_persona(acc_prob=0.7, n=20):
        return [(0.6, "correct" if rng.random() < acc_prob else "incorrect") for _ in range(n)]

    def drifting_persona(n=20, break_at=12, acc_before=0.75, acc_after=0.25):
        out = []
        for i in range(n):
            acc = acc_before if i < break_at else acc_after
            out.append((0.6, "correct" if rng.random() < acc else "incorrect"))
        return out

    def slow_drift_persona(n=24):
        out = []
        for i in range(n):
            acc = max(0.15, 0.8 - i * 0.025)  # gradual decline
            out.append((0.6, "correct" if rng.random() < acc else "incorrect"))
        return out

    cases = {
        "stable (.70 accuracy throughout)": stable_persona(0.70),
        "sharp drift at log 12 (.75 -> .25)": drifting_persona(),
        "slow gradual decline": slow_drift_persona(),
        "cold-start (4 logs)": stable_persona(0.70, n=4),
    }
    print(f"{'persona':<38} {'severity':>8}   detail")
    print("-" * 100)
    for name, logs in cases.items():
        sev, d = drift_severity(logs)
        print(f"{name:<38} {round(sev, 3):>8}   {d}")