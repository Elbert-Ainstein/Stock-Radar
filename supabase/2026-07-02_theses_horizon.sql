-- Lesson L1 (2026-07-02): the trade gate has a clock, and it must be visible.
-- Persist the thesis horizon each verdict was judged on, so a clamp is always
-- auditable against its ruler ("was the market expensive, or the clock wrong?").
--
-- Not auto-applied. Run in the Supabase SQL editor. Until applied, run_thesis
-- strips the column with a loud stderr warning (data lost for that row).

ALTER TABLE theses ADD COLUMN IF NOT EXISTS thesis_horizon_years numeric;

-- Verification: expect 1 row.
SELECT column_name FROM information_schema.columns
WHERE table_name = 'theses' AND column_name = 'thesis_horizon_years';
