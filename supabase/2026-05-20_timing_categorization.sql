-- ═══════════════════════════════════════════════════════════════
-- TIMING CATEGORIZATION — 收获期 / 半步领先 / 一步领先 / 远见期
-- 2026-05-20  (BUILD_PLAN_v2 Phase 5.5 expansion from Session 2 addendum §C)
--
-- A 4-bucket capital-allocation discipline tag that applies to revolutions,
-- waves, and individual ticker assignments within a wave. Direct mapping
-- between timing category and conviction sizing per `user_position_sizing_discipline`:
--
--   收获期 (HARVEST)        : hold, don't enter — consensus/peak (e.g. AMD at $762B, 41/41 Buy)
--   半步领先 (HALF STEP)    : conviction capital 60-70%  — verified thesis, room to run
--   一步领先 (ONE STEP)     : moderate positions 15-25%  — thesis real, less consensus
--   远见期 (MOONSHOT)      : tiny positions 5-10%       — pre-commercial, optionality
--
-- All three columns are nullable — categorization is opt-in, not required
-- for every row. UI defaults to displaying the most specific available
-- (ticker > wave > revolution).
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE revolutions
    ADD COLUMN IF NOT EXISTS timing_category text;

ALTER TABLE revolutions
    DROP CONSTRAINT IF EXISTS revolutions_timing_category_check;
ALTER TABLE revolutions
    ADD CONSTRAINT revolutions_timing_category_check
    CHECK (timing_category IN ('收获期','半步领先','一步领先','远见期')
           OR timing_category IS NULL);

ALTER TABLE waves
    ADD COLUMN IF NOT EXISTS timing_category text;

ALTER TABLE waves
    DROP CONSTRAINT IF EXISTS waves_timing_category_check;
ALTER TABLE waves
    ADD CONSTRAINT waves_timing_category_check
    CHECK (timing_category IN ('收获期','半步领先','一步领先','远见期')
           OR timing_category IS NULL);

ALTER TABLE ticker_revolutions
    ADD COLUMN IF NOT EXISTS timing_category text;

ALTER TABLE ticker_revolutions
    DROP CONSTRAINT IF EXISTS ticker_revolutions_timing_category_check;
ALTER TABLE ticker_revolutions
    ADD CONSTRAINT ticker_revolutions_timing_category_check
    CHECK (timing_category IN ('收获期','半步领先','一步领先','远见期')
           OR timing_category IS NULL);

CREATE INDEX IF NOT EXISTS idx_revolutions_timing      ON revolutions (timing_category)      WHERE timing_category IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_waves_timing            ON waves (timing_category)            WHERE timing_category IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ticker_rev_timing       ON ticker_revolutions (timing_category) WHERE timing_category IS NOT NULL;

-- ────────────────────────────────────────────────────────────────
-- Initial seed values from socratic_results_summary-6121e194.md and
-- BUILD_PLAN-83703dd5.md addendum §C. Applied additively where the
-- target row exists; no errors if rows don't exist yet.
-- ────────────────────────────────────────────────────────────────

-- AI revolution overall: 半步领先 for most waves (per README)
UPDATE revolutions SET timing_category = '半步领先' WHERE name_cn = 'AI革命';

-- Space economy: 一步领先 to 半步领先
UPDATE revolutions SET timing_category = '一步领先' WHERE name_cn = '太空经济革命';

-- Digital finance: 一步领先
UPDATE revolutions SET timing_category = '一步领先' WHERE name_cn = '数字金融革命';

-- Quantum computing (will be created by 2026-05-20_quantum_revolution_seed.sql):
-- the seed file sets timing_category='远见期' directly at INSERT time.

-- Selected wave-level overrides (only where they meaningfully differ from revolution default).
-- AI Wave 1 (Compute/GPU) — past peak consensus
UPDATE waves SET timing_category = '收获期'
WHERE name_cn = '算力' AND revolution_id = (SELECT id FROM revolutions WHERE name_cn = 'AI革命');

-- AI Wave 2 (Optical) — 5-20x runs already happened on most; LITE/COHR specifically
UPDATE waves SET timing_category = '收获期'
WHERE name_cn = '光互联' AND revolution_id = (SELECT id FROM revolutions WHERE name_cn = 'AI革命');

-- AI Wave 0 (Equipment) — CAMT/CAMT-class still 半步领先 despite mid-cycle wave
UPDATE waves SET timing_category = '半步领先'
WHERE name_cn = '设备' AND revolution_id = (SELECT id FROM revolutions WHERE name_cn = 'AI革命');

-- AI Wave 4 (Power) — early-to-mid, still 半步领先
UPDATE waves SET timing_category = '半步领先'
WHERE name_cn = '电力' AND revolution_id = (SELECT id FROM revolutions WHERE name_cn = 'AI革命');

-- AI Wave 5 (Cooling) — VRT integrated chain, early/mid → 半步领先
UPDATE waves SET timing_category = '半步领先'
WHERE name_cn = '冷却' AND revolution_id = (SELECT id FROM revolutions WHERE name_cn = 'AI革命');
