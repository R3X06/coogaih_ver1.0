-- Migration 001 — Risk Contract support + contract/schema drift fixes
-- Corresponds to docs/RISK_CONTRACT.md v1.0.
-- Idempotent: guarded so re-running against an already-migrated db is a no-op.
-- Run inside one transaction so a partial failure rolls back cleanly.

begin;

-- 1. manual_logs.outcome: boolean -> four-value enum (correct|incorrect|partial|na)
--    to match DATA_CONTRACT.md and schema.json. The old boolean could not
--    represent `partial`, which the risk formula requires.
do $$
begin
    if (select data_type
        from information_schema.columns
        where table_name = 'manual_logs' and column_name = 'outcome') = 'boolean' then
        alter table manual_logs
            alter column outcome type text
            using case
                when outcome is true  then 'correct'
                when outcome is false then 'incorrect'
                else null
            end;
    end if;
end $$;

alter table manual_logs drop constraint if exists manual_logs_outcome_chk;
alter table manual_logs
    add constraint manual_logs_outcome_chk
    check (outcome is null or outcome in ('correct', 'incorrect', 'partial', 'na'));

-- 2. manual_logs.topic -> concept, to match the manual_log payload in
--    DATA_CONTRACT.md / schema.json (which name the field `concept`).
do $$
begin
    if exists (select 1 from information_schema.columns
               where table_name = 'manual_logs' and column_name = 'topic') then
        alter table manual_logs rename column topic to concept;
    end if;
end $$;

-- 3. sessions: freeze-at-compute provenance for risk_score (RISK_CONTRACT.md §6).
--    risk_score itself already exists (nullable, 0..1); we only add provenance.
alter table sessions
    add column if not exists risk_computed_at timestamptz,
    add column if not exists risk_detail      jsonb;

commit;
