-- ═══════════════════════════════════════════════════════════════
-- SOCRATIC ANALYSES — three-model verdict storage
-- 2026-05-15  (BUILD_PLAN_v2 Phase 1.2)
--
-- Two write paths land here:
--   AUTO MODE — run_thesis.py dual-writes the single-model verdict
--               into model_a (model_b/c null, mode='auto'). The same
--               row also lives in `theses` table; thesis_id links them.
--   SOCRATIC MODE — the 3-model orchestrator writes a new row with
--               mode='socratic', all three model columns populated,
--               and corpus-callosum output in agreements/disagreements.
--
-- Why dual-write to both `theses` and `socratic_analyses` for auto:
--   - `theses` keeps serving the existing dashboard unchanged
--   - `socratic_analyses` becomes the single read path for the new
--     5-tab frontend, so the UI doesn't need to know about modes
--   - After Phase 2 stabilizes, we may collapse theses into a view
--     over socratic_analyses, but not in this migration
--
-- model_a / model_b / model_c each store:
--   {
--     "verdict": "公允价值" | "低估" | "高估" | ...,
--     "target_low": number,
--     "target_high": number,
--     "reasoning_bullets": [string, ...],
--     "confidence": "HIGH" | "MEDIUM" | "LOW",
--     "role": "fundamentals" | "regime" | "adversarial" | "auto"
--   }
--
-- disagreements stores an array of:
--   {
--     "question": string,
--     "type": "research" | "judgment",
--     "resolved": boolean,
--     "finding": string | null,        -- web-search finding if type=research
--     "models_disagreeing": ["a","b"] | ...
--   }
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS socratic_analyses (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker              text NOT NULL,
    run_at              timestamptz NOT NULL DEFAULT now(),
    mode                text NOT NULL CHECK (mode IN ('auto','socratic')),

    -- For mode='auto', link back to the existing theses row
    thesis_id           bigint REFERENCES theses(id) ON DELETE SET NULL,

    -- Three model verdicts (model_b / model_c null in auto mode)
    model_a             jsonb,
    model_b             jsonb,
    model_c             jsonb,

    -- Corpus callosum output
    agreements          jsonb DEFAULT '[]'::jsonb,
    disagreements       jsonb DEFAULT '[]'::jsonb,
    research_findings   jsonb DEFAULT '[]'::jsonb,

    -- Rough target range (the user-facing magnitude estimate)
    rough_target_low    double precision,
    rough_target_high   double precision,
    downside_price      double precision,
    rough_target_paragraph text,                    -- the one-paragraph narrative

    -- Final routing for the human
    final_verdict       text CHECK (final_verdict IN ('proceed','watch','pass') OR final_verdict IS NULL),

    -- Provenance
    prompt_versions     jsonb DEFAULT '{}'::jsonb,  -- {"harness":"v1","model_a":"v1",...}
    spot_at_run         double precision,
    input_tokens        integer,
    output_tokens       integer,
    web_search_count    integer
);

CREATE INDEX IF NOT EXISTS idx_socratic_ticker_run_at  ON socratic_analyses (ticker, run_at DESC);
CREATE INDEX IF NOT EXISTS idx_socratic_mode           ON socratic_analyses (mode);
CREATE INDEX IF NOT EXISTS idx_socratic_thesis_id      ON socratic_analyses (thesis_id);

-- ────────────────────────────────────────────────────────────────
-- View: latest socratic per ticker (the frontend's primary read)
-- ────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW latest_socratic AS
SELECT DISTINCT ON (ticker)
    id, ticker, run_at, mode,
    model_a, model_b, model_c,
    agreements, disagreements,
    rough_target_low, rough_target_high, downside_price,
    rough_target_paragraph,
    final_verdict, spot_at_run, thesis_id
FROM socratic_analyses
ORDER BY ticker, run_at DESC;

-- ═══════════════════════════════════════════════════════════════
-- MODEL ACCURACY — per-bet, per-model error tracking
-- Populated at bet settlement (T+90).
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS model_accuracy (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bet_id              bigint NOT NULL,                 -- FK added in 2026-05-15_bets.sql
    socratic_id         bigint REFERENCES socratic_analyses(id) ON DELETE SET NULL,
    ticker              text NOT NULL,

    -- Error of each model's target_mid vs actual price at T+90
    -- error = (actual_price - model_target_mid) / model_target_mid * 100
    model_a_error_pct   double precision,
    model_b_error_pct   double precision,
    model_c_error_pct   double precision,
    closest_model       text CHECK (closest_model IN ('a','b','c') OR closest_model IS NULL),

    -- Did the human's custom judgment beat the default verdict?
    human_beat_default  boolean,

    actual_price_t90    double precision,
    settled_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_accuracy_ticker        ON model_accuracy (ticker);
CREATE INDEX IF NOT EXISTS idx_accuracy_closest       ON model_accuracy (closest_model);

-- Rolling accuracy summary (callable from frontend after N≥20 settlements)
CREATE OR REPLACE VIEW model_accuracy_summary AS
SELECT
    'a' AS model,
    COUNT(*) AS n,
    AVG(ABS(model_a_error_pct)) AS avg_abs_error,
    AVG(CASE WHEN closest_model = 'a' THEN 1.0 ELSE 0.0 END) AS won_share
FROM model_accuracy
WHERE model_a_error_pct IS NOT NULL
UNION ALL
SELECT 'b', COUNT(*), AVG(ABS(model_b_error_pct)),
    AVG(CASE WHEN closest_model = 'b' THEN 1.0 ELSE 0.0 END)
FROM model_accuracy
WHERE model_b_error_pct IS NOT NULL
UNION ALL
SELECT 'c', COUNT(*), AVG(ABS(model_c_error_pct)),
    AVG(CASE WHEN closest_model = 'c' THEN 1.0 ELSE 0.0 END)
FROM model_accuracy
WHERE model_c_error_pct IS NOT NULL;
