-- ═══════════════════════════════════════════════════════════════
-- STOCK RADAR — Supabase Schema Migration
-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor)
-- ═══════════════════════════════════════════════════════════════

-- 1. STOCKS (watchlist — replaces watchlist.json)
CREATE TABLE IF NOT EXISTS stocks (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ticker        TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  sector        TEXT NOT NULL DEFAULT '',
  thesis        TEXT DEFAULT '',
  kill_condition TEXT DEFAULT '',
  tags          JSONB DEFAULT '[]'::JSONB,

  -- Target price model
  target_price       NUMERIC,          -- e.g. 1500
  timeline_years     INT DEFAULT 3,
  valuation_method   TEXT DEFAULT 'pe', -- 'pe' or 'ps'
  target_multiple    NUMERIC,          -- e.g. 42
  target_notes       TEXT DEFAULT '',

  -- Model defaults (slider starting values)
  model_defaults     JSONB DEFAULT '{}'::JSONB,
  -- e.g. {"revenue_b":8,"op_margin":0.4,"tax_rate":0.17,"shares_m":74,"pe_multiple":42}

  -- Scenarios
  scenarios          JSONB DEFAULT '{}'::JSONB,
  -- e.g. {"bull":{"probability":0.25,"price":1900,"trigger":"..."}, ...}

  -- Criteria (investment checklist)
  criteria           JSONB DEFAULT '[]'::JSONB,
  -- Array of criterion objects

  -- Metadata
  active             BOOLEAN DEFAULT TRUE,
  added_at           TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
);

-- 2. SIGNALS (per-scout, per-stock, per-run — replaces *_signals.json)
CREATE TABLE IF NOT EXISTS signals (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ticker        TEXT NOT NULL,
  scout         TEXT NOT NULL,        -- 'quant', 'news', 'insider', 'social', 'youtube', 'fundamentals'
  signal        TEXT NOT NULL,        -- 'bullish', 'bearish', 'neutral'
  ai            TEXT DEFAULT '',      -- 'Perplexity', 'Claude', 'Gemini', 'Script'
  summary       TEXT DEFAULT '',
  data          JSONB DEFAULT '{}'::JSONB,   -- Scout-specific structured data
  scores        JSONB DEFAULT '{}'::JSONB,   -- Scout-specific scores
  run_id        TEXT,                 -- Links to pipeline_runs.run_id
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals (ticker);
CREATE INDEX IF NOT EXISTS idx_signals_scout ON signals (scout);
CREATE INDEX IF NOT EXISTS idx_signals_run_id ON signals (run_id);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals (created_at DESC);

-- 3. ANALYSIS (composite scores — replaces analysis.json per-stock entries)
CREATE TABLE IF NOT EXISTS analysis (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ticker          TEXT NOT NULL,
  composite_score NUMERIC DEFAULT 0,
  overall_signal  TEXT DEFAULT 'neutral',
  convergence     JSONB DEFAULT '{}'::JSONB,
  scores          JSONB DEFAULT '{}'::JSONB,   -- {quant_score, convergence, fundamentals, ...}
  valuation       JSONB DEFAULT '{}'::JSONB,
  auto_tiers      JSONB DEFAULT '[]'::JSONB,
  alerts          JSONB DEFAULT '[]'::JSONB,
  criteria_eval   JSONB DEFAULT '{}'::JSONB,   -- criteria evaluation results
  event_impacts   JSONB DEFAULT '{}'::JSONB,   -- event-driven target adjustments (Phase 1 audit-only)
  fundamentals    JSONB DEFAULT '{}'::JSONB,   -- business fundamentals data
  price_data      JSONB DEFAULT '{}'::JSONB,   -- {price, change, change_pct, market_cap_b, ...}
  run_id          TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Additive migration for existing installs (idempotent)
ALTER TABLE analysis
  ADD COLUMN IF NOT EXISTS event_impacts JSONB DEFAULT '{}'::JSONB;

CREATE INDEX IF NOT EXISTS idx_analysis_ticker ON analysis (ticker);
CREATE INDEX IF NOT EXISTS idx_analysis_created ON analysis (created_at DESC);
-- Unique constraint: one analysis per stock per run
CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_ticker_run ON analysis (ticker, run_id);

-- 4. PIPELINE_RUNS (execution history — replaces pipeline_log.json)
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id        TEXT NOT NULL UNIQUE,  -- UUID or timestamp-based
  started_at    TIMESTAMPTZ DEFAULT NOW(),
  completed_at  TIMESTAMPTZ,
  success       BOOLEAN,
  free_only     BOOLEAN DEFAULT FALSE,
  scouts_active TEXT[] DEFAULT '{}',   -- Array of scout names that ran
  scout_details JSONB DEFAULT '{}'::JSONB,
  stock_count   INT DEFAULT 0,
  error         TEXT,
  log_tail      TEXT,                  -- Last 2000 chars of stdout
  duration_s    NUMERIC
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs (started_at DESC);

-- 5. Helper view: latest analysis per stock (most recent run)
CREATE OR REPLACE VIEW latest_analysis AS
SELECT DISTINCT ON (ticker) *
FROM analysis
ORDER BY ticker, created_at DESC;

-- 6. Helper view: latest signals per stock per scout
CREATE OR REPLACE VIEW latest_signals AS
SELECT DISTINCT ON (ticker, scout) *
FROM signals
ORDER BY ticker, scout, created_at DESC;

-- 7. RLS policies (enable row-level security for public access)
ALTER TABLE stocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;

-- Allow anon key full access (single-user app)
CREATE POLICY "Allow all on stocks" ON stocks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on signals" ON signals FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on analysis" ON analysis FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on pipeline_runs" ON pipeline_runs FOR ALL USING (true) WITH CHECK (true);

-- 8. Updated_at trigger for stocks
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER stocks_updated_at
  BEFORE UPDATE ON stocks
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();
