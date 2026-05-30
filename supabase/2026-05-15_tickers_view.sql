-- ═══════════════════════════════════════════════════════════════
-- TICKERS VIEW — frontend-compatible name over the live stocks table
-- 2026-05-15  (BUILD_PLAN_v2 Phase 1.5)
--
-- The new 5-tab frontend (BUILD_PLAN_v2 Phase 7) expects an entity
-- called `tickers` with conviction / thesis_target / setup_note
-- columns. Renaming the live `stocks` table would break the
-- existing dashboard (the entire `app/dashboard/*` directory
-- queries `stocks` directly).
--
-- Solution: create a view named `tickers` that exposes the columns
-- the new frontend wants, sourced from `stocks` + latest `theses`
-- row + latest `socratic_analyses` row. The view is read-only.
-- Writes continue to go to `stocks` via the existing code.
--
-- If the frontend ever needs to write to `tickers`, we'll add an
-- INSTEAD OF trigger then. Not before.
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW tickers AS
SELECT
    s.id,
    s.ticker,
    s.name,
    s.sector,

    -- Headline thesis numbers (from latest theses row, NULL if none)
    t.thesis_target,
    t.risk_adj_target              AS dcf_value,         -- repositioned: risk-adj target IS the downside floor
    t.conviction,
    t.position_size_pct,
    t.run_at                       AS last_run,

    -- Free-form setup
    s.thesis                       AS setup_note,
    s.kill_condition,

    -- Provenance
    s.tags,
    s.active,
    s.added_at                     AS created_at,
    s.updated_at,

    -- Latest socratic id if one exists (for the new frontend's compact view)
    sa.id                          AS latest_socratic_id,
    sa.mode                        AS latest_socratic_mode
FROM stocks s
LEFT JOIN LATERAL (
    SELECT thesis_target, risk_adj_target, conviction, position_size_pct, run_at
    FROM theses
    WHERE theses.ticker = s.ticker
    ORDER BY run_at DESC
    LIMIT 1
) t ON TRUE
LEFT JOIN LATERAL (
    SELECT id, mode
    FROM socratic_analyses
    WHERE socratic_analyses.ticker = s.ticker
    ORDER BY run_at DESC
    LIMIT 1
) sa ON TRUE;

-- Convenience: a view for stocks with NO recent thesis (the
-- watchlist's "needs analysis" bucket — useful for the new
-- compact Socratic-summary section that says "尚未运行").
CREATE OR REPLACE VIEW tickers_needing_analysis AS
SELECT
    s.ticker,
    s.name,
    s.sector,
    (SELECT MAX(run_at) FROM theses WHERE theses.ticker = s.ticker) AS last_thesis_run,
    (SELECT MAX(run_at) FROM socratic_analyses WHERE socratic_analyses.ticker = s.ticker) AS last_socratic_run
FROM stocks s
WHERE s.active = true
  AND (
      NOT EXISTS (SELECT 1 FROM theses WHERE theses.ticker = s.ticker)
      OR (SELECT MAX(run_at) FROM theses WHERE theses.ticker = s.ticker) < NOW() - INTERVAL '30 days'
  );
