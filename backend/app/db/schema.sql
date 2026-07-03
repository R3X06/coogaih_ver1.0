-- Coogaih — Postgres/Supabase schema (v1)
-- Locked Week 0. Matches DATA_CONTRACT.md event envelope and the
-- /ingest/session-metrics payload in API_CONTRACT.md.

create extension if not exists "pgcrypto"; -- for gen_random_uuid()

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
create table if not exists users (
    id              uuid primary key default gen_random_uuid(),
    email           text unique not null,
    telemetry_level text not null default 'basic_domain_only'
                        check (telemetry_level in ('none', 'basic_domain_only', 'enhanced_titles_optional')),
    created_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- sessions
-- One row per study session. Populated by POST /ingest/session-metrics,
-- which is called by the Focus-State Engine (friend's service) — never
-- written to directly by his engine.
-- ---------------------------------------------------------------------------
create table if not exists sessions (
    id                          uuid primary key default gen_random_uuid(),
    user_id                     uuid not null references users(id) on delete cascade,
    ts_start                    timestamptz not null,
    ts_end                      timestamptz,

    -- metrics from the Focus-State Engine (all normalized 0-1 except avg block length)
    switching_rate              double precision check (switching_rate between 0 and 1),
    avg_focus_block_minutes     double precision check (avg_focus_block_minutes >= 0),
    fragmentation               double precision check (fragmentation between 0 and 1),
    distraction_ratio           double precision check (distraction_ratio between 0 and 1),

    -- populated later by the cognitive engine (calibration/drift/risk) — nullable at ingest time
    risk_score                  double precision check (risk_score between 0 and 1),

    created_at                  timestamptz not null default now()
);

create index if not exists idx_sessions_user on sessions(user_id);
create index if not exists idx_sessions_ts_start on sessions(ts_start);

-- ---------------------------------------------------------------------------
-- raw_events
-- Optional raw event trail (extension -> engine envelope), kept for
-- auditability / re-computation. Not required for the MVP demo path but
-- cheap to have and useful for your friend's contract/property tests.
-- ---------------------------------------------------------------------------
create table if not exists raw_events (
    id          bigserial primary key,
    session_id  uuid not null references sessions(id) on delete cascade,
    event_type  text not null check (event_type in
                    ('session_start', 'focus_start', 'focus_end', 'switch', 'afk', 'session_end')),
    ts          timestamptz not null,
    payload     jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists idx_raw_events_session on raw_events(session_id);

-- ---------------------------------------------------------------------------
-- manual_logs
-- User-entered confidence + outcome. This is the sole source of the
-- calibration metric (ECE/Brier) — keep it decoupled from sessions so a
-- log can exist without a session and vice versa.
-- ---------------------------------------------------------------------------
create table if not exists manual_logs (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references users(id) on delete cascade,
    session_id  uuid references sessions(id) on delete set null,
    topic       text,
    confidence  double precision not null check (confidence between 0 and 1),
    outcome     boolean, -- null until resolved
    created_at  timestamptz not null default now()
);

create index if not exists idx_manual_logs_user on manual_logs(user_id);
