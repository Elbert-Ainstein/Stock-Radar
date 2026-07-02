-- Lesson L4 (2026-07-02): the engine must never have an invisible opinion.
-- Persist the parameter block each thesis verdict ran under (horizon, scaled
-- clamp table, archetype routing, which gates acted) so any verdict is
-- auditable against its own configuration.
--
-- Not auto-applied. Run in the Supabase SQL editor. Until applied, run_thesis
-- strips the column with a loud stderr warning.

ALTER TABLE theses ADD COLUMN IF NOT EXISTS run_parameters jsonb;

-- Verification: expect 1 row.
SELECT column_name FROM information_schema.columns
WHERE table_name = 'theses' AND column_name = 'run_parameters';
