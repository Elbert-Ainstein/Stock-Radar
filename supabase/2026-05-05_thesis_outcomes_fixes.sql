-- ═══════════════════════════════════════════════════════════════
-- THESIS OUTCOMES — squad-review fixes
-- 2026-05-05 (same day, second pass)
--
-- Fixes from critic review:
--   1. thesis_realized_pct_t180 was mathematically incoherent — measured
--      (price_t180 / thesis_target) which is not normalized to spot. Now a
--      GENERATED column thesis_progress_pct_t180 computing
--      (realized_return / implied_target_return) * 100.
--   2. ON DELETE CASCADE destroyed calibration history when a thesis row
--      was deleted. Switched to ON DELETE SET NULL with separate UUID PK
--      so outcome rows survive thesis deletion.
--   3. thesis_calibration view: equally weighted stale and current theses.
--      Added thesis_calibration_latest view showing only the most recent
--      thesis per ticker.
-- ═══════════════════════════════════════════════════════════════

-- 0. Drop dependent views first so we can mutate the column they reference
DROP VIEW IF EXISTS thesis_calibration_latest;
DROP VIEW IF EXISTS thesis_calibration;

-- 1. Restructure PK: separate UUID id, thesis_id becomes nullable FK
ALTER TABLE thesis_outcomes DROP CONSTRAINT IF EXISTS thesis_outcomes_pkey;
ALTER TABLE thesis_outcomes ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
UPDATE thesis_outcomes SET id = gen_random_uuid() WHERE id IS NULL;
ALTER TABLE thesis_outcomes ALTER COLUMN id SET NOT NULL;
ALTER TABLE thesis_outcomes ADD PRIMARY KEY (id);
ALTER TABLE thesis_outcomes ALTER COLUMN thesis_id DROP NOT NULL;
ALTER TABLE thesis_outcomes ADD CONSTRAINT thesis_outcomes_thesis_id_unique UNIQUE (thesis_id);

-- 2. Replace FK with ON DELETE SET NULL
ALTER TABLE thesis_outcomes DROP CONSTRAINT IF EXISTS thesis_outcomes_thesis_id_fkey;
ALTER TABLE thesis_outcomes
  ADD CONSTRAINT thesis_outcomes_thesis_id_fkey
  FOREIGN KEY (thesis_id) REFERENCES theses(id) ON DELETE SET NULL;

-- 3. Drop the incoherent column (now safe — views are gone)
ALTER TABLE thesis_outcomes DROP COLUMN IF EXISTS thesis_realized_pct_t180;

-- 4. Add correctly-derived GENERATED columns for t30/t90/t180
ALTER TABLE thesis_outcomes ADD COLUMN thesis_progress_pct_t30 REAL GENERATED ALWAYS AS (
  CASE
    WHEN spot_at_run > 0 AND thesis_target > spot_at_run AND price_t30 IS NOT NULL
    THEN (((price_t30 / spot_at_run - 1.0) * 100.0) / ((thesis_target / spot_at_run - 1.0) * 100.0)) * 100.0
    ELSE NULL
  END
) STORED;

ALTER TABLE thesis_outcomes ADD COLUMN thesis_progress_pct_t90 REAL GENERATED ALWAYS AS (
  CASE
    WHEN spot_at_run > 0 AND thesis_target > spot_at_run AND price_t90 IS NOT NULL
    THEN (((price_t90 / spot_at_run - 1.0) * 100.0) / ((thesis_target / spot_at_run - 1.0) * 100.0)) * 100.0
    ELSE NULL
  END
) STORED;

ALTER TABLE thesis_outcomes ADD COLUMN thesis_progress_pct_t180 REAL GENERATED ALWAYS AS (
  CASE
    WHEN spot_at_run > 0 AND thesis_target > spot_at_run AND price_t180 IS NOT NULL
    THEN (((price_t180 / spot_at_run - 1.0) * 100.0) / ((thesis_target / spot_at_run - 1.0) * 100.0)) * 100.0
    ELSE NULL
  END
) STORED;

-- 5. Recreate views with corrected metric and add latest-only variant
-- Aggregate across ALL thesis runs per ticker. Equally weights stale and
-- current — for current-conviction analysis use thesis_calibration_latest.
CREATE VIEW thesis_calibration AS
SELECT
  ticker,
  COUNT(*) AS n_theses,
  COUNT(price_t30)  AS n_t30,
  COUNT(price_t90)  AS n_t90,
  COUNT(price_t180) AS n_t180,
  AVG(return_t30_pct)   AS avg_return_t30_pct,
  AVG(return_t90_pct)   AS avg_return_t90_pct,
  AVG(return_t180_pct)  AS avg_return_t180_pct,
  AVG(thesis_progress_pct_t30)  AS avg_progress_t30_pct,
  AVG(thesis_progress_pct_t90)  AS avg_progress_t90_pct,
  AVG(thesis_progress_pct_t180) AS avg_progress_t180_pct,
  MIN(thesis_date) AS first_thesis,
  MAX(thesis_date) AS latest_thesis
FROM thesis_outcomes
GROUP BY ticker
ORDER BY ticker;

-- Latest thesis per ticker only — the right view for "is the CURRENT
-- conviction calibrated?" Avoids stale-thesis dilution.
CREATE VIEW thesis_calibration_latest AS
SELECT DISTINCT ON (ticker)
  ticker, thesis_id, thesis_date, thesis_target, spot_at_run, conviction,
  return_t30_pct, return_t90_pct, return_t180_pct,
  thesis_progress_pct_t30, thesis_progress_pct_t90, thesis_progress_pct_t180
FROM thesis_outcomes
ORDER BY ticker, thesis_date DESC;
