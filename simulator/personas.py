"""Learner personas for the longitudinal simulator.

These are the SAME personas already cited by `RISK_CONTRACT.md` §4 and
exercised in `risk_ref.py` / `drift_severity.py`'s __main__ blocks. Defining
them once here is the point: those two files currently each carry their own
private persona code, which is how the §4 reference table drifted out of sync
with the implementation in the first place. Import from here instead.

The accuracy model is deliberately shaped for interrupted time series. A
learner's true accuracy at session `i` is:

    acc(i) = base
             + baseline_slope * i                     # pre-existing trend
             + drift_delta      if i >= drift_at      # a changepoint
             + rec_level
             + rec_slope * (i - rec_at)  if i >= rec_at   # planted effect

`rec_level` and `rec_slope` are exactly the two parameters ITS estimates
(level shift and slope change). Planting them means the ITS implementation
can be validated against a known truth rather than eyeballed off a chart.

`baseline_slope` matters more than it looks: a NON-FLAT baseline is what
makes ITS non-trivial. Extrapolating a flat line and extrapolating a
declining trend give very different counterfactuals, and the declining case
is precisely where naive before/after comparison gets fooled by regression
to the mean (`plan.md` Fix 3).

Confidence is modelled independently of accuracy — that separation IS the
calibration story. A persona is defined by the GAP between what it claims
and what it gets right.
"""
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Persona:
    name: str

    # --- stated confidence (the `manual_log.confidence` distribution) -------
    conf_mu: float
    conf_sigma: float

    # --- true accuracy trajectory ------------------------------------------
    base_accuracy: float
    baseline_slope: float = 0.0     # accuracy change per session, pre-intervention
    partial_band: float = 0.10      # P(partial) sits just above P(correct)

    # --- changepoint (for drift_severity validation) -----------------------
    drift_at: int | None = None
    drift_delta: float = 0.0

    # --- planted recommendation effect (for ITS validation) ----------------
    rec_at: int | None = None
    rec_level: float = 0.0          # immediate step change in accuracy
    rec_slope: float = 0.0          # per-session slope change after the rec

    # --- behavioural / focus profile ---------------------------------------
    focus_quality: float = 0.6      # 0 = scattered, 1 = deep focus
    focus_quality_sigma: float = 0.12
    logs_per_session: float = 1.8   # mean; Poisson-ish
    na_rate: float = 0.12           # share of logs that are check-ins with no outcome

    def accuracy_at(self, i: int) -> float:
        """True P(correct) at session index `i` (0-based)."""
        acc = self.base_accuracy + self.baseline_slope * i
        if self.drift_at is not None and i >= self.drift_at:
            acc += self.drift_delta
        if self.rec_at is not None and i >= self.rec_at:
            acc += self.rec_level + self.rec_slope * (i - self.rec_at)
        return float(min(max(acc, 0.02), 0.98))

    def as_manifest(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# The roster.
#
# The first four mirror RISK_CONTRACT.md §4's reference table rows one-for-one
# — they exist so the contract's claimed risk_scores stay reproducible from a
# named artifact instead of an inline lambda.
#
# `drifting` and `responsive` are the two that make the *validation* protocols
# runnable: one plants a changepoint for drift_severity to find, the other
# plants a level+slope effect for ITS to recover.
# ---------------------------------------------------------------------------
PERSONAS: dict[str, Persona] = {
    "well_calibrated": Persona(
        name="well_calibrated",
        conf_mu=0.70, conf_sigma=0.06,
        base_accuracy=0.70,
        focus_quality=0.78,
    ),
    "underconfident": Persona(
        name="underconfident",
        conf_mu=0.35, conf_sigma=0.06,
        base_accuracy=0.90,
        focus_quality=0.80,
    ),
    "mildly_overconfident": Persona(
        name="mildly_overconfident",
        conf_mu=0.75, conf_sigma=0.06,
        base_accuracy=0.55,
        focus_quality=0.62,
    ),
    "confidently_wrong": Persona(
        name="confidently_wrong",
        conf_mu=0.85, conf_sigma=0.06,
        base_accuracy=0.20,
        focus_quality=0.45,
    ),
    # Changepoint at session 12: a learner who was doing fine and falls off.
    # This is drift_severity.py's target case — and note that file's own
    # documented failure mode (late breaks with few post-break samples), which
    # is why `drift_at` sits comfortably inside the run, not at the tail.
    "drifting": Persona(
        name="drifting",
        conf_mu=0.72, conf_sigma=0.07,
        base_accuracy=0.75,
        drift_at=12, drift_delta=-0.50,
        focus_quality=0.55,
    ),
    # THE ITS CASE. Declining baseline, recommendation at session 15, planted
    # level shift of +0.18 and slope change of +0.012/session.
    #
    # The declining baseline is the trap: a naive before/after comparison sees
    # the post-rec average rise and calls it a win, when part of that rise is
    # just the counterfactual bottoming out. A correct ITS implementation
    # should recover ~+0.18 level and ~+0.012 slope, NOT the raw gap in means.
    "responsive": Persona(
        name="responsive",
        conf_mu=0.68, conf_sigma=0.07,
        base_accuracy=0.72, baseline_slope=-0.018,
        rec_at=15, rec_level=0.18, rec_slope=0.012,
        focus_quality=0.58,
    ),
    # Control arm for the ITS case: identical trajectory, NO recommendation.
    # If the ITS estimator reports a non-zero effect on this persona, the
    # estimator is picking up trend as treatment — a false positive you can
    # actually measure rather than hope about.
    "unresponsive_control": Persona(
        name="unresponsive_control",
        conf_mu=0.68, conf_sigma=0.07,
        base_accuracy=0.72, baseline_slope=-0.018,
        focus_quality=0.58,
    ),
}

# Which personas form which reference corpus. RISK_CONTRACT.md §5 defines
# OCE_FLOOR as p90 of OCE on a WELL-CALIBRATED corpus and OCE_MAX as p95 on an
# OVERCONFIDENT one. Those two corpora are these two lists — naming them here
# means the constants stop being "provisional" guesses and become a computed,
# re-runnable number.
WELL_CALIBRATED_CORPUS = ["well_calibrated", "underconfident"]
OVERCONFIDENT_CORPUS = ["mildly_overconfident", "confidently_wrong"]
