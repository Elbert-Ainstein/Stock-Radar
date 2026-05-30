-- Run this in the Supabase SQL Editor to create the discovery_candidates table
CREATE TABLE IF NOT EXISTS discovery_candidates (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker text NOT NULL,
  name text,
  sector text,
  price float,
  change_pct float,
  market_cap_b float,
  revenue_growth_pct float,
  earnings_growth_pct float,
  gross_margin_pct float,
  operating_margin_pct float,
  forward_pe float,
  ps_ratio float,
  peg_ratio float,
  distance_from_high_pct float,
  beta float,
  short_pct float,
  quant_score float,
  scores jsonb DEFAULT '{}',
  signal text,
  summary text,
  stage text DEFAULT 'candidate',   -- 'candidate' | 'shortlist' | 'reviewed' | 'passed'
  rank int,
  run_id text,
  scanned_at timestamptz DEFAULT now()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_discovery_run_id ON discovery_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_discovery_stage ON discovery_candidates(stage);
CREATE INDEX IF NOT EXISTS idx_discovery_ticker ON discovery_candidates(ticker);
CREATE INDEX IF NOT EXISTS idx_discovery_score ON discovery_candidates(quant_score DESC);

-- Enable RLS (allow all for now — tighten later if needed)
ALTER TABLE discovery_candidates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all access" ON discovery_candidates FOR ALL USING (true) WITH CHECK (true);
