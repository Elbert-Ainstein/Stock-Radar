-- 2026-07-08 — Lesson L4: no invisible opinions.
-- Every thesis run persists the parameter block it was judged under:
-- model/prompt/temperature, spot + source, horizon clock (config/used/
-- fallback), POST-SCALING clamp table, archetype + dcf_role, allowlist size,
-- memory size. Built by scripts/run_parameters.py, written by run_thesis.
-- Until applied, the writer strip-and-retries the column with a stderr
-- warning (that run's block survives only in the run log).
--
-- Apply manually in the Supabase SQL editor (postgres role), then run the
-- verification query and paste the output back.

ALTER TABLE theses ADD COLUMN IF NOT EXISTS run_parameters jsonb;

COMMENT ON COLUMN theses.run_parameters IS
  'L4 (2026-07-08): parameters the verdict was judged under — horizon clock, post-scaling clamp table, archetype/dcf_role, spot source, allowlist size. schema: thesis_run_parameters_v1';

-- Verification (expect 1 row):
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'theses' AND column_name = 'run_parameters';
