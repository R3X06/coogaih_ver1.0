# Coogaih — Process & Methodology (v1)

This document locks the development methodology for the project, the same way
`DATA_CONTRACT.md` locks the data layer and `RISK_CONTRACT.md` locks the risk
score. Both of you build against *this* for how work moves, not just what
gets built.

---

## 1. Locked decision: Agile — Kanban flavor

**Not Waterfall.** Waterfall assumes each phase (requirements → design → build
→ ship) is frozen before the next starts. This project has already broken
that assumption more than once:

- `manual_logs.outcome` went from boolean → 4-value enum (migration 001) —
  after the schema was already "locked"
- `RISK_CONTRACT.md` was added as a third contract after `DATA_CONTRACT.md`
  and `API_CONTRACT.md` were already frozen
- `SWITCH_MAX`, `FRAG_MAX`, `OCE_FLOOR`, `OCE_MAX` are explicitly flagged as
  provisional, pending real-data recalibration

Each of those is a revision to something Waterfall would have called "done."
Kanban expects that and absorbs it as a new card, not a broken commitment.

**Not Scrum.** Scrum needs fixed-length sprints and steady, predictable
capacity per person. Two people building this part-time don't have steady
velocity — forcing sprint boundaries onto that creates guilt over slippage
without buying anything back.

**Kanban fits** because work is pull-based and continuous: a contract change
becomes a new card on the board, not a broken sprint.

---

## 2. Board structure

- **Columns:** `Backlog` → `In Progress` → `In Review` → `Done`
- **Swimlanes:** one per owner (you / @maniarockiaraj), so folder ownership
  from `.github/CODEOWNERS` is visible on the board, not just enforced in git
- **WIP limit:** 2 cards `In Progress` per person at a time — this is the one
  piece of Kanban discipline worth keeping; it stops half-finished work from
  piling up invisibly
- **Where:** GitHub Projects, linked to this repo's issues/PRs — no new tool
  needed

---

## 3. Milestones (not sprints)

Checkpoints you both look at together — not calendar deadlines.

| Milestone | Status |
|---|---|
| M0 — Contracts locked (`DATA_CONTRACT.md`, `API_CONTRACT.md`) | Done |
| M1 — Backend scaffold (schema, FastAPI, Docker) | Done |
| M2 — Core engines (cognitive engine + Focus-State Engine) | In progress |
| M3 — LLM + RAG layer | Next |
| M4 — Dashboard + demo integration | Next |

---

## 4. Definition of Done

**Your components** (extension, API, cognitive engine, LLM/RAG, dashboard):
- Matches the locked contract in `docs/`
- Typed (Pydantic / TypeScript, as applicable)
- Runs against `sample_events.jsonl` or the longitudinal simulator
- Merged into `main` via reviewed PR

**His components** (Focus-State Engine, all of `tests/`):
- Property-based tests passing (Hypothesis)
- Consumer-driven contract test against `/ingest/session-metrics` passing
- CI green

A card doesn't move to `Done` until its Definition of Done is met — not when
it "feels finished."

---

## 5. Decision log (ADR-lite)

**Rule:** no constant or contract change merges without a decision log entry.
This turns the CODEOWNERS-enforced review from "someone approved it" into
"someone approved it *and we know why*."

**Template** (one entry per change, kept in the Notion Decisions Log — not
duplicated into `docs/`, which stays the enforced source of truth for the
contracts themselves):

```
Date:
Constant or contract changed:
Old value:
New value:
Data that justified the change:
Who agreed:
```

First entries to backfill: the `outcome` boolean→enum migration and the
addition of `RISK_CONTRACT.md` — both already happened without a record of
why, worth capturing retroactively while the reasoning is still fresh.

---

## 6. Cadence

- Async by default — PRs and the board carry most of the coordination
- One lightweight sync per week (15–30 min): check the board, flag any
  pending contract change, update the decision log if one landed

---

## 7. What this replaces

The ad hoc "we'll just talk about it when it comes up" coordination that
produced: the `outcome` rework, `RISK_CONTRACT.md` arriving after the fact
with no paper trail, and the duplicate `backend/API_CONTRACT.md` /
`docs/API_CONTRACT.md` drift risk. None of those were caused by a bad
methodology — they were caused by not having one written down. This document
is that write-down.