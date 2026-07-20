"""Validate a simulator run.

Four gates, in increasing order of what they'd catch:

  1. SCHEMA     every event validates against docs/schema.json (the same
                Draft202012Validator the contract was locked with).
  2. INVARIANTS things the schema cannot express — producers never set
                `category`, manual_logs are instantaneous, every
                `refers_to_session` points at a session that exists.
  3. CONTRACT   every sessions.jsonl row would survive the Pydantic
                validation in backend/app/schemas.py (0-1 bounds, non-negative
                block length). If this fails, POSTing the fixture would 422.
  4. DETERMINISM regenerating from manifest.json's own seed reproduces the
                corpus byte-for-byte. This is the gate that would have caught
                the shared-RNG bug in RISK_CONTRACT.md §4.

Exit code is non-zero on any failure, so this drops straight into CI when
@maniarockiaraj stands up .github/workflows/.

Usage:
    python -m simulator.validate --out simulator/out --schema docs/schema.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from generate import generate_learner
from personas import PERSONAS


def _load_jsonl(p: Path) -> list[dict]:
    with p.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _hash(events: list[dict]) -> str:
    h = hashlib.sha256()
    for e in events:
        h.update(json.dumps(e, sort_keys=True).encode())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="simulator/out")
    ap.add_argument("--schema", default="docs/schema.json")
    args = ap.parse_args()

    out = Path(args.out)
    events = _load_jsonl(out / "events.jsonl")
    sessions = _load_jsonl(out / "sessions.jsonl")
    manifest = json.loads((out / "manifest.json").read_text())

    failures: list[str] = []

    # --- 1. schema ---------------------------------------------------------
    schema = json.loads(Path(args.schema).read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    bad = 0
    for idx, e in enumerate(events):
        errs = sorted(validator.iter_errors(e), key=lambda x: x.path)
        if errs:
            bad += 1
            if bad <= 3:
                failures.append(f"schema: event {idx}: {errs[0].message}")
    if bad:
        failures.append(f"schema: {bad}/{len(events)} events invalid")
    print(f"[1] schema        {len(events) - bad}/{len(events)} events valid")

    # --- 2. invariants -----------------------------------------------------
    session_ids = {s["session_id"] for s in sessions}
    inv = 0
    for e in events:
        if e["category"] is not None:
            inv += 1
        if e["kind"] == "manual_log":
            if e["duration_ms"] is not None:
                inv += 1
            ref = e["payload"].get("refers_to_session")
            if ref is not None and ref not in session_ids:
                inv += 1
        elif e["duration_ms"] is None or e["duration_ms"] < 0:
            inv += 1
    if inv:
        failures.append(f"invariants: {inv} violation(s)")
    n_logs = sum(1 for e in events if e["kind"] == "manual_log")
    print(f"[2] invariants    {inv} violation(s)   ({n_logs} manual_logs, "
          f"{len(session_ids)} sessions)")

    # --- 3. contract bounds (mirrors backend/app/schemas.py) ---------------
    cb = 0
    for s in sessions:
        for f in ("switching_rate", "fragmentation", "distraction_ratio"):
            if not (0.0 <= s[f] <= 1.0):
                cb += 1
                failures.append(f"bounds: {f}={s[f]} in session {s['session_id']}")
        if s["avg_focus_block_minutes"] < 0:
            cb += 1
        if s["ts_end"] < s["ts_start"]:
            cb += 1
    print(f"[3] contract      {len(sessions) - cb}/{len(sessions)} sessions would POST cleanly")

    # --- 4. determinism ----------------------------------------------------
    regenerated: list[dict] = []
    for lm in manifest["learners"]:
        ev, _, _ = generate_learner(
            PERSONAS[lm["persona"]],
            manifest["sessions_per_learner"],
            manifest["seed"],
            lm["persona_index"],
            lm["learner_index"],
        )
        regenerated.extend(ev)
    regenerated.sort(key=lambda e: e["ts"])
    same = _hash(regenerated) == _hash(events)
    if not same:
        failures.append("determinism: regenerated corpus differs from artifact on disk")
    print(f"[4] determinism   {'reproduced' if same else 'MISMATCH'}  "
          f"(sha256 {_hash(events)[:12]})")

    print()
    if failures:
        for f in failures[:12]:
            print("FAIL", f)
        return 1
    print("all gates passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
