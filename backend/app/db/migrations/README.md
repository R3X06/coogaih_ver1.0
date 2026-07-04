# Database migrations

`schema.sql` (one directory up) is the source of truth for a **fresh** database —
docker-compose mounts it as the init script, so a brand-new DB comes up already in
the final shape. These migration files bring an **existing** database up to that
shape without wiping it.

Apply them **in numeric order**. Each is wrapped in a transaction and guarded to
be idempotent (safe to re-run).

## When you need these

- **Fresh DB / throwaway dev volume** → you don't. `docker compose down -v && docker compose up`
  reloads `schema.sql` at its current shape. Skip migrations entirely.
- **Existing DB with data you want to keep** → apply the migrations you haven't run yet.

## How to apply (local docker-compose db)

```bash
# from the repo root, with `docker compose up` running
docker compose exec -T db psql -U postgres -d coogaih < backend/app/db/migrations/001_risk_contract.sql
```

Or against a Supabase/remote instance:

```bash
psql "$DATABASE_URL_PSQL" -f backend/app/db/migrations/001_risk_contract.sql
```

(Use the plain `postgresql://` psql URL, not the `postgresql+asyncpg://` form the
app uses.)

## Migration log

| # | File | What it does |
|---|------|--------------|
| 001 | `001_risk_contract.sql` | `manual_logs.outcome` boolean→enum (`correct\|incorrect\|partial\|na`); `manual_logs.topic`→`concept`; adds `sessions.risk_computed_at` + `sessions.risk_detail`. Corresponds to `docs/RISK_CONTRACT.md`. |

## ⚠️ 001 is a breaking change for existing fixtures

If you have local test fixtures or seed data that insert into `manual_logs`, they
will break after 001:

- `outcome` is no longer a boolean — use `'correct'` / `'incorrect'` / `'partial'` / `'na'`
  (string), not `true` / `false`.
- the column `topic` is now `concept`.

Update fixtures before running the contract/property tests against a migrated DB.

## ⚠️ Not yet run against a live Postgres

001 has been parse-checked and reviewed, but not executed against a real database
in this repo yet. Before merging, run it once against a throwaway volume and
confirm it applies cleanly and re-running it is a no-op.