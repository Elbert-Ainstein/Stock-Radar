-- ════════════════════════════════════════════════════════════════════════
-- Phase 1 Sandbox — scenario_scratch table
-- Run via Supabase SQL editor (no RLS for MVP — single-user app)
-- ════════════════════════════════════════════════════════════════════════
--
-- Stores user-saved what-if scenarios per ticker. Each row is one named
-- scenario with its driver perturbations (revenue growth, margins,
-- multiples, WACC, blend) and the computed price the user saw at save time.
--
-- Why Supabase instead of localStorage:
-- 1. Cross-device — Hume works across machines.
-- 2. Survives browser cache clears.
-- 3. CRITICAL: when Module 9 calibration loop eventually evaluates thesis
--    accuracy, having timestamped scenarios in Supabase lets us answer
--    "which scenario assumption was closest to actual outcome?" That's
--    falsifiability data we don't want to lose to localStorage volatility.
--
-- Schema deliberately minimal — drivers stored as a single JSONB so we can
-- add/remove driver fields without migrations. The cost is loose typing on
-- the inputs; mitigation is that the WhatIfTab UI is the only writer and
-- it has a TS interface for the driver shape.

CREATE TABLE IF NOT EXISTS scenario_scratch (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker          TEXT NOT NULL,
  scenario_name   TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Driver perturbations as JSON. Schema (TypeScript-side, app/model/.../WhatIfTab.tsx):
  -- {
  --   rev_growth_y1: number,        // 0..1 (e.g. 0.35 = +35% Y1 revenue)
  --   rev_growth_terminal: number,  // 0..1 terminal growth
  --   ebitda_margin: number,        // 0..1 EBITDA margin target
  --   fcf_sbc_margin: number,       // 0..1 FCF/SBC margin target
  --   ev_ebitda_multiple: number,   // multiple, e.g. 20
  --   ev_fcf_multiple: number,      // multiple, e.g. 28
  --   wacc: number,                 // 0..1 discount rate
  --   blend: number,                // 0..1 EBITDA-method weight (0..1)
  --   term_ps: number | null,       // for revenue-multiple mode
  -- }
  drivers         JSONB NOT NULL,

  -- Result snapshot at save time — denormalized so the comparison view
  -- doesn't have to recompute. Recomputation happens only when the user
  -- explicitly clicks "Refresh" on a scenario card (e.g. after a thesis
  -- re-run changed the base TTM revenue).
  computed_price  NUMERIC NOT NULL,
  upside_vs_current NUMERIC,         -- % vs the spot price at save time
  delta_vs_model    NUMERIC,         -- % vs the system base case at save time
  spot_at_save      NUMERIC,         -- captures spot price at save time

  -- Free-form notes (e.g. "what if AI capex grows 50%")
  notes           TEXT,

  -- Soft-delete via active flag. Avoids cascading deletes if we later add
  -- references from theses/calibration to specific scenarios.
  active          BOOLEAN NOT NULL DEFAULT TRUE,

  -- Each ticker should have at most one scenario per name (prevent
  -- accidental duplicates from a double-click on Save).
  CONSTRAINT scenario_scratch_unique_per_ticker UNIQUE (ticker, scenario_name, active)
);

CREATE INDEX IF NOT EXISTS scenario_scratch_ticker_idx
  ON scenario_scratch (ticker, active, created_at DESC);

-- Auto-update updated_at on UPDATE
CREATE OR REPLACE FUNCTION scenario_scratch_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS scenario_scratch_touch ON scenario_scratch;
CREATE TRIGGER scenario_scratch_touch
  BEFORE UPDATE ON scenario_scratch
  FOR EACH ROW
  EXECUTE FUNCTION scenario_scratch_touch_updated_at();
