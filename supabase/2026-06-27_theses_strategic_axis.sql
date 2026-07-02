-- Dual-system Step 1 — surface the structural (Type A) axis.
-- `strategic_conviction` (HIGH/MEDIUM/LOW/BROKEN, price-INDEPENDENT structural thesis)
-- and `risk_adj_ev_ratio` (the trade-asymmetry ratio that drives the BROKEN clamp)
-- are computed in every thesis but were dropped before the DB write — so the
-- dashboard/grader only ever saw the price-dependent trade verdict (a bare BROKEN).
-- Persist both so a verdict reads "strategic HIGH / trade BROKEN / buy below $X".
-- Safe + idempotent (ADD COLUMN IF NOT EXISTS). Run in the Supabase SQL editor.

ALTER TABLE theses ADD COLUMN IF NOT EXISTS strategic_conviction text;
ALTER TABLE theses ADD COLUMN IF NOT EXISTS risk_adj_ev_ratio numeric;
