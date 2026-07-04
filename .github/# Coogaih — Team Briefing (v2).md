# Coogaih — Team Briefing (v2)

*Sync point now that the repo is live and both of you are actually in it.*

---

## 1. What's done (as of now)

- Repo live on GitHub: `https://github.com/R3X06/coogaih_ver1.0`
- `main` protected: PR required, Code Owner review required, no force-push, no branch deletion
- Backend scaffold built and working: Postgres schema (`users`, `sessions`, `raw_events`, `manual_logs`), FastAPI app with `POST /ingest/session-metrics` — validated locally, not yet pointed at a real Supabase instance
- Both contracts locked and in `docs/`: `DATA_CONTRACT.md`, `API_CONTRACT.md`, plus `schema.json` and `sample_events.jsonl` (13 sample events, schema-validated) for building against mock data
- `docker-compose.yml` at repo root — spins up your API + Postgres, has a commented-out block for his `focus-engine` service to uncomment once it exists
- **[friend]** added as collaborator, confirmed the full Git loop works (branch → commit → push → PR)

## 2. What's NOT done yet — this is the actual state, not aspirational

- `focus-engine/` is still empty — his engine hasn't been started
- `tests/` is still empty — no property-based tests, contract tests, or CI workflow yet
- No CI pipeline exists at all — `.github/workflows/` is empty
- DB isn't live anywhere — schema exists but hasn't been run against a real Postgres/Supabase instance
- No auth on the API — fine for now, flagged for before any public demo

## 3. Ownership split (unchanged, just restating clearly)

| | Owns |
|---|---|
| **You** | Extension, FastAPI API, cognitive engine (calibration/drift/risk), LLM + RAG, impact scoring, dashboard, DB schema, Docker, simulator |
| **[friend]** | Focus-State Engine (switching rate, fragmentation, avg focus block, distraction ratio, live classifier) + **all quality engineering**: property-based tests, contract tests, integration/E2E, CI gating, Postman/Newman |

Folder boundary: he only ever touches `focus-engine/`, `tests/`, `.github/workflows/`. You touch everything else. `docs/DATA_CONTRACT.md` and `docs/API_CONTRACT.md` are the one shared zone — both of you must review changes there (GitHub enforces this automatically).

## 4. What he should actually start on

1. Read `docs/DATA_CONTRACT.md` and `docs/API_CONTRACT.md` fully if he hasn't.
2. Start his Focus-State Engine against `docs/sample_events.jsonl` as mock input — no need to wait for your real extension.
3. Compute the four metrics (`switching_rate`, `avg_focus_block_minutes`, `fragmentation`, `distraction_ratio`) per the locked formulas in `API_CONTRACT.md`.
4. POST them to your `/ingest/session-metrics` endpoint (works locally via `docker compose up`, or point at wherever you land Supabase).
5. Sanity-check `SWITCH_MAX` and `FRAG_MAX` once he has real numbers — they're flagged as starting values, not final. Bring back real numbers, decide together if they need adjusting.

## 5. Daily workflow, quick recap for both of you

```
git checkout main && git pull        # sync up before starting
git checkout -b name/task            # one branch per task
... work, commit ...
git push -u origin name/task
# → open PR on GitHub → merge (contract docs need both approvals)
git checkout main && git pull        # sync back up
```

Full reference: `GIT_MANUAL.md` (worth adding to the repo so it's there for both of you, not just local).

## 6. Open decisions for this sync

- **Timeline** — rough target for a first end-to-end demo (his engine actually POSTing real metrics into your live API)?
- **His engine's shape** — live watcher process, or a batch job over stored events, for the MVP demo? Affects whether the `docker-compose` service block is the right fit for him.
- **When to add API auth** — before any public/demo exposure, who owns it?
- **CI ownership** — when does he want to start the GitHub Actions workflow in `.github/workflows/`? Doesn't block either of you from building, but worth a rough date so contract-test gating exists before things get complex.