-- ═══════════════════════════════════════════════════════════════
-- DISCOVERY V2 — Add AI validation columns to discovery_candidates
-- Run AFTER the initial create_discovery_table.sql
-- ═══════════════════════════════════════════════════════════════

-- AI validation fields
ALTER TABLE discovery_candidates
  ADD COLUMN IF NOT EXISTS ai_confidence FLOAT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS thesis TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS kill_condition TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS catalysts JSONB DEFAULT '[]'::JSONB,
  ADD COLUMN IF NOT EXISTS target_range JSONB DEFAULT '{}'::JSONB,
  ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::JSONB,
  ADD COLUMN IF NOT EXISTS research TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS industry TEXT DEFAULT NULL;

-- Index for AI-validated candidates
CREATE INDEX IF NOT EXISTS idx_discovery_ai_conf ON discovery_candidates(ai_confidence DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_discovery_stage_score ON discovery_candidates(stage, quant_score DESC);
