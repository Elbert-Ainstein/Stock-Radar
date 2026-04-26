-- Create prediction_outcomes table for tracking actual price observations.
-- Used by calibration.py (compute_target_convergence) and prediction_logger.py (record_price_outcome).
-- Requires prediction_log table to exist first.

CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    prediction_id   UUID REFERENCES prediction_log(id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    days_elapsed    INTEGER NOT NULL,
    actual_price    DOUBLE PRECISION,
    recorded_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE (prediction_id, days_elapsed)
);

-- Index for fast joins from calibration.py
CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_pred
    ON prediction_outcomes (prediction_id);

-- Index for ticker-based lookups
CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_ticker
    ON prediction_outcomes (ticker, recorded_at DESC);

-- Enable RLS but allow all operations (anon key)
ALTER TABLE prediction_outcomes ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'prediction_outcomes' AND policyname = 'prediction_outcomes_all'
    ) THEN
        CREATE POLICY prediction_outcomes_all ON prediction_outcomes FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;
