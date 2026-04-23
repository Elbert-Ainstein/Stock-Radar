-- ═══════════════════════════════════════════════════════════════
-- FEEDBACK LOOP — Signal Outcomes & Scout Accuracy
-- Run this in Supabase SQL Editor after the base migration.sql
-- ═══════════════════════════════════════════════════════════════

-- 1. SIGNAL_OUTCOMES — tracks what happened after each signal
-- One row per signal per evaluation window (7d, 30d, 60d, 90d).
-- Populated by the feedback_loop.py module during pipeline runs.
CREATE TABLE IF NOT EXISTS signal_outcomes (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  signal_id       BIGINT NOT NULL,           -- FK to signals.id
  ticker          TEXT NOT NULL,
  scout           TEXT NOT NULL,
  signal          TEXT NOT NULL,              -- bullish / bearish / neutral (copied for fast queries)
  window_days     INT NOT NULL,              -- 7, 30, 60, 90
  signal_date     TIMESTAMPTZ NOT NULL,      -- when the signal was created
  price_at_signal NUMERIC,                   -- stock price when signal was issued
  price_at_eval   NUMERIC,                   -- stock price at signal_date + window_days
  return_pct      NUMERIC,                   -- ((price_at_eval - price_at_signal) / price_at_signal) * 100
  hit             BOOLEAN,                   -- did signal direction match actual price movement?
  evaluated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_so_signal_id ON signal_outcomes (signal_id);
CREATE INDEX IF NOT EXISTS idx_so_ticker ON signal_outcomes (ticker);
CREATE INDEX IF NOT EXISTS idx_so_scout ON signal_outcomes (scout);
CREATE INDEX IF NOT EXISTS idx_so_window ON signal_outcomes (window_days);
CREATE UNIQUE INDEX IF NOT EXISTS idx_so_signal_window ON signal_outcomes (signal_id, window_days);

-- RLS
ALTER TABLE signal_outcomes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on signal_outcomes" ON signal_outcomes FOR ALL USING (true) WITH CHECK (true);

-- 2. SCOUT_ACCURACY — materialized view of per-scout hit rates
-- Refreshed after each feedback evaluation run.
-- We use a regular table instead of a materialized view for Supabase compatibility.
CREATE TABLE IF NOT EXISTS scout_accuracy (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  scout           TEXT NOT NULL,
  window_days     INT NOT NULL,
  total_signals   INT DEFAULT 0,
  hits            INT DEFAULT 0,
  misses          INT DEFAULT 0,
  accuracy_pct    NUMERIC DEFAULT 0,         -- hits / total * 100
  avg_return_pct  NUMERIC DEFAULT 0,         -- average return when following signal
  avg_hit_return  NUMERIC DEFAULT 0,         -- avg return on correct calls
  avg_miss_return NUMERIC DEFAULT 0,         -- avg return on wrong calls
  bullish_accuracy NUMERIC DEFAULT 0,        -- accuracy on bullish calls specifically
  bearish_accuracy NUMERIC DEFAULT 0,        -- accuracy on bearish calls specifically
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(scout, window_days)
);

ALTER TABLE scout_accuracy ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on scout_accuracy" ON scout_accuracy FOR ALL USING (true) WITH CHECK (true);

-- 3. Add kill_condition_eval to analysis (from prior task, idempotent)
ALTER TABLE analysis
  ADD COLUMN IF NOT EXISTS kill_condition_eval JSONB DEFAULT NULL;
