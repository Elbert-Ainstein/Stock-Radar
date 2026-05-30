-- ════════════════════════════════════════════════════════════════════════
-- Phase 1b post-review fixes for scenario_scratch
-- Apply in Supabase SQL editor. Idempotent — safe to re-run.
-- ════════════════════════════════════════════════════════════════════════
--
-- Two changes flagged by the post-Phase-1b review squad:
--
-- 1. The original UNIQUE (ticker, scenario_name, active) constraint does
--    NOT enforce "one active scenario per (ticker, name)". A delete sets
--    active=false (orphaned row) then a new save inserts active=true, and
--    both rows persist. Module 9 calibration queries will see duplicate
--    names per ticker. Fix: replace with a partial unique index that only
--    enforces uniqueness across active rows.
--
-- 2. The original schema didn't persist `valuation_method`. A scenario
--    saved in EV/EBITDA mode would silently load into revenue-multiple
--    mode after a thesis re-run flipped the method, producing wrong
--    prices in the ScenarioCompare card with no warning. Add a column
--    so the client can detect the mismatch and warn the user.
--    Existing rows (pre-2026-05-09b) get NULL — treated as "unknown
--    mode" by the client.

-- ─── Fix #1: partial unique index on active rows only ───────────────────
ALTER TABLE scenario_scratch
  DROP CONSTRAINT IF EXISTS scenario_scratch_unique_per_ticker;

CREATE UNIQUE INDEX IF NOT EXISTS scenario_scratch_active_unique
  ON scenario_scratch (ticker, scenario_name)
  WHERE active = TRUE;

-- ─── Fix #2: persist valuation_method so cross-mode loads warn ──────────
ALTER TABLE scenario_scratch
  ADD COLUMN IF NOT EXISTS valuation_method TEXT;

COMMENT ON COLUMN scenario_scratch.valuation_method IS
  'Engine valuation_method at save time ("revenue_multiple" or NULL=EV/EBITDA). '
  'Client compares to current payload mode and warns on mismatch.';
