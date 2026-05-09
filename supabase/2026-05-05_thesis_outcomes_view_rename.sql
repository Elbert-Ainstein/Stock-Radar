-- ═══════════════════════════════════════════════════════════════
-- THESIS OUTCOMES — view rename (third pass, squad re-review)
-- 2026-05-05
--
-- Critic re-review caught: keeping the all-thesis aggregate as the default
-- name `thesis_calibration` left the defect reachable (any caller using
-- the old name gets stale-thesis dilution). Fix: make the default correct.
--   - thesis_calibration         = latest thesis per ticker (was _latest)
--   - thesis_calibration_all_runs = explicit all-thesis aggregate
-- ═══════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS thesis_calibration_latest;
DROP VIEW IF EXISTS thesis_calibration;

-- The default view: latest thesis per ticker. This is what "is the system
-- calibrated?" should answer — current conviction vs realized.
CREATE VIEW thesis_calibration AS
SELECT DISTINCT ON (ticker)
  ticker, thesis_id, thesis_date, thesis_target, spot_at_run, conviction,
  return_t30_pct, return_t90_pct, return_t180_pct,
  thesis_progress_pct_t30, thesis_progress_pct_t90, thesis_progress_pct_t180
FROM thesis_outcomes
ORDER BY ticker, thesis_date DESC;

-- Explicit all-thesis aggregate. Use only when you specifically want to
-- see the system's calibration tendency across all historical runs,
-- accepting that stale theses dilute current signal.
CREATE VIEW thesis_calibration_all_runs AS
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
