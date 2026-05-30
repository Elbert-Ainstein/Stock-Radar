-- Archetype stability tracking table
-- Stores one row per pipeline run per ticker with the archetype classification.
-- Used by check_archetype_stability() in generate_model.py to detect regime
-- changes vs. classification noise over a rolling 4-run lookback window.
--
-- Patterns detected:
--   stable:        all 4 runs agree → single archetype, high confidence
--   regime_change: consistent classification then a single switch → market narrative shift (real signal)
--   unstable:      flipping back and forth → genuinely ambiguous, auto-flag as hybrid

CREATE TABLE IF NOT EXISTS archetype_history (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker      TEXT NOT NULL,
    archetype   TEXT NOT NULL,           -- primary archetype: garp, cyclical, transformational, compounder, special_situation
    secondary   TEXT,                     -- secondary archetype (if hybrid characteristics)
    justification TEXT,                   -- Claude's 1-2 sentence reasoning for this classification
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for the stability lookup: latest N rows per ticker, ordered by time
CREATE INDEX IF NOT EXISTS idx_archetype_history_ticker_time
    ON archetype_history (ticker, created_at DESC);

-- Add archetype column to stocks table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stocks' AND column_name = 'archetype'
    ) THEN
        ALTER TABLE stocks ADD COLUMN archetype JSONB DEFAULT '{}';
    END IF;
END $$;
