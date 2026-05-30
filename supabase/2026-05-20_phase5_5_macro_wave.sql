-- ═══════════════════════════════════════════════════════════════
-- PHASE 5.5 — Macro environment + Wave health
-- 2026-05-20  (BUILD_PLAN_v2 Phase 5.5; spec at docs/design/MACRO_AND_WAVE_HEALTH_v1.md)
--
-- Two new analytical layers sitting between economy-wide macro and per-stock
-- Socratic analysis. Macro is the portfolio-level frame; wave_health is the
-- per-wave dynamic translation. Both feed [MACRO_CONTEXT] / [WAVE_CONTEXT]
-- into Socratic A/B/C as upstream context.
--
-- Includes review squad amendments applied 2026-05-20:
--   Must-fix #3: ticker_revolutions.is_primary_wave for multi-wave resolution
--   Must-fix #4: bets.status enum extension for 'passed'
--   Should-fix #5: wave_health.beta_methodology for beta provenance
--   Should-fix #6: settlement fields on wave_health
--   Plus: watch_signals jsonb on wave_health for cycle-shift observables
--         (per feedback_watch_vs_break — LITE/COHR generational competition
--          and Wave 3 storage cycle are tracked as observable metrics, not
--          binary thesis-break triggers)
-- ═══════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────────────────
-- 1. macro_environment — portfolio-level regime assessment
-- ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS macro_environment (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_at                  timestamptz NOT NULL DEFAULT now(),
    source                  text NOT NULL,                  -- 'manual_hume' | 'run_macro_v1' | ...

    -- Headline state
    state_summary           text NOT NULL,                  -- one-paragraph regime summary
    regime_classification   text NOT NULL,                  -- free-text label, grows organically:
                                                            -- 'stagflation_risk' | 'goldilocks' | 'rate_shock' | etc.

    -- Bear / bull framework
    bear_case               jsonb NOT NULL,                 -- {probability, drivers[], implication}
    bull_case               jsonb NOT NULL,                 -- {probability, drivers[], implication}

    -- Triggers and dates (state_change_triggers become Phase 6 notification rows)
    state_change_triggers   jsonb NOT NULL DEFAULT '[]'::jsonb,
                                                            -- [{event, direction, watch_for}]
                                                            -- direction in {BULLISH, BEARISH, CLARITY, MIXED}
    watch_dates             jsonb NOT NULL DEFAULT '[]'::jsonb,
                                                            -- [{date, event, importance}]
    this_week_watch         jsonb NOT NULL DEFAULT '[]'::jsonb,
                                                            -- weekly granular triggers between regime
                                                            -- classification and next-FOMC-date watch

    -- Settlement
    falsification           text,                           -- required at write time; machine-parseable preferred
    settled_at              timestamptz,
    settled_outcome         text CHECK (settled_outcome IN ('bear_correct','bull_correct','mixed','unsettled')
                                        OR settled_outcome IS NULL),

    -- Lifecycle
    superseded_by           bigint REFERENCES macro_environment(id),
    notes                   text
);

CREATE INDEX IF NOT EXISTS idx_macro_env_run_at         ON macro_environment (run_at DESC);
CREATE INDEX IF NOT EXISTS idx_macro_env_current        ON macro_environment (id) WHERE superseded_by IS NULL;
CREATE INDEX IF NOT EXISTS idx_macro_env_regime         ON macro_environment (regime_classification);


-- ────────────────────────────────────────────────────────────────
-- 2. wave_health — dynamic per-wave health overlay on existing waves table
-- ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS wave_health (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    wave_id                 bigint NOT NULL REFERENCES waves(id) ON DELETE CASCADE,
    macro_env_id            bigint REFERENCES macro_environment(id),

    -- Health metrics (refreshed weekly + on macro change)
    momentum_score          double precision,               -- avg 12mo return of wave stocks
    momentum_label          text CHECK (momentum_label IN ('extreme','elevated','normal','depressed')
                                         OR momentum_label IS NULL),
    crowding_score          text CHECK (crowding_score IN ('high','medium','low') OR crowding_score IS NULL),
    avg_forward_pe          double precision,
    pe_vs_5yr_mean          text,                           -- e.g. '65% above' or '10% below'

    -- Macro sensitivity
    macro_beta              double precision,               -- e.g., 2.3
    beta_methodology        text,                           -- Should-fix #5: provenance of the beta number
                                                            -- e.g. "LLM analogy from 2022 semi correction, no quantitative lookback"
                                                            -- or "yfinance 36mo regression vs SPX, drawdowns >5% only"
    macro_translation       text,                           -- "SPX -15% → wave -30 to -35%"
    why_drivers             text,                           -- reasoning for the beta
    regime_playbook         text,                           -- advice specific to current macro regime

    -- Intra-wave (Must-fix #1: differentiation entries require trailing_12mo_return and
    -- trailing_18mo_return per ticker so Model C can derive per-stock beta deviations)
    -- Schema example: [{ticker, resilience, reason, trailing_12mo_return, trailing_18mo_return}]
    differentiation         jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- Watch signals (feedback_watch_vs_break — observable cycle-shift metrics,
    -- NOT binary fire/no-fire triggers; tracked as leading indicators)
    -- Examples:
    --   Wave 2 (Optical): {gen_mix: "1.6T vs 3.2T order ratio", eml_inventory_at_module_assemblers, ...}
    --   Wave 3 (Storage): {dram_inventory_weeks, nand_inventory_weeks, lead_times, price_qoq, cancel_to_book, distributor_stock}
    watch_signals           jsonb NOT NULL DEFAULT '{}'::jsonb,

    -- Settlement (Should-fix #6 — nullable until settled)
    settlement_window_days  int,
    benchmark_index         text,                           -- 'SPX' | 'NDX' | 'SOX' | etc.
    actual_wave_return      double precision,
    settled_at              timestamptz,

    -- Lifecycle
    run_at                  timestamptz NOT NULL DEFAULT now(),
    superseded_by           bigint REFERENCES wave_health(id)
);

CREATE INDEX IF NOT EXISTS idx_wave_health_wave         ON wave_health (wave_id);
CREATE INDEX IF NOT EXISTS idx_wave_health_macro        ON wave_health (macro_env_id);
CREATE INDEX IF NOT EXISTS idx_wave_health_current      ON wave_health (wave_id) WHERE superseded_by IS NULL;
CREATE INDEX IF NOT EXISTS idx_wave_health_run_at       ON wave_health (run_at DESC);


-- ────────────────────────────────────────────────────────────────
-- 3. Must-fix #3 — multi-wave ticker resolution
--    is_primary_wave column on ticker_revolutions; harness selects primary if set,
--    otherwise most recently refreshed wave_health row.
-- ────────────────────────────────────────────────────────────────

ALTER TABLE ticker_revolutions
    ADD COLUMN IF NOT EXISTS is_primary_wave boolean NOT NULL DEFAULT false;

-- Partial unique index: at most one primary wave per ticker
DROP INDEX IF EXISTS idx_ticker_rev_primary_unique;
CREATE UNIQUE INDEX idx_ticker_rev_primary_unique
    ON ticker_revolutions (ticker)
    WHERE is_primary_wave = true;


-- ────────────────────────────────────────────────────────────────
-- 4. Must-fix #4 — bets.status enum extension for pass decisions
--    Existing status check was: ('active','settled_win','settled_loss','cancelled')
--    Extended to include 'passed' for position_pct=0 bets.
--    Notification cron filters status='active'; 'passed' is excluded from
--    regime-flip notifications (no zombie pings).
-- ────────────────────────────────────────────────────────────────

ALTER TABLE bets DROP CONSTRAINT IF EXISTS bets_status_check;
ALTER TABLE bets ADD CONSTRAINT bets_status_check
    CHECK (status IN ('active','passed','settled_win','settled_loss','cancelled'));


-- ────────────────────────────────────────────────────────────────
-- 5. FK additions: link bets and socratic_analyses to macro and wave context
-- ────────────────────────────────────────────────────────────────

ALTER TABLE bets
    ADD COLUMN IF NOT EXISTS macro_environment_id bigint REFERENCES macro_environment(id);

ALTER TABLE socratic_analyses
    ADD COLUMN IF NOT EXISTS macro_environment_id bigint REFERENCES macro_environment(id);

ALTER TABLE socratic_analyses
    ADD COLUMN IF NOT EXISTS wave_health_id bigint REFERENCES wave_health(id);

CREATE INDEX IF NOT EXISTS idx_bets_macro_env           ON bets (macro_environment_id);
CREATE INDEX IF NOT EXISTS idx_socratic_macro_env       ON socratic_analyses (macro_environment_id);
CREATE INDEX IF NOT EXISTS idx_socratic_wave_health     ON socratic_analyses (wave_health_id);


-- ────────────────────────────────────────────────────────────────
-- 6. Views
-- ────────────────────────────────────────────────────────────────

-- Current (non-superseded) macro environment — the row Socratic injects from
CREATE OR REPLACE VIEW current_macro_environment AS
SELECT *
FROM macro_environment
WHERE superseded_by IS NULL
ORDER BY run_at DESC
LIMIT 1;

-- Current wave_health per wave (most recent non-superseded row per wave_id)
CREATE OR REPLACE VIEW current_wave_health AS
SELECT DISTINCT ON (wave_id) *
FROM wave_health
WHERE superseded_by IS NULL
ORDER BY wave_id, run_at DESC;

-- Bets needing macro-flip notification: open bets linked to a now-superseded regime
CREATE OR REPLACE VIEW bets_needing_macro_review AS
SELECT
    b.id,
    b.ticker,
    b.entry_price,
    b.position_pct,
    b.status,
    b.macro_environment_id AS bet_macro_env_id,
    me.regime_classification AS bet_regime,
    me.superseded_by AS regime_superseded_by,
    cm.regime_classification AS current_regime
FROM bets b
LEFT JOIN macro_environment me ON me.id = b.macro_environment_id
LEFT JOIN current_macro_environment cm ON true
WHERE b.status = 'active'                    -- exclude 'passed' (no zombie pings)
  AND me.superseded_by IS NOT NULL           -- bet's regime is no longer current
  AND me.id != cm.id;                        -- bet's regime != current regime
