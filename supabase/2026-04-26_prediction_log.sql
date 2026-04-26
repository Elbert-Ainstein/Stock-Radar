-- Create prediction_log table for tracking model predictions over time.
-- Used by calibration.py and feedback_loop.py to measure prediction accuracy.

CREATE TABLE IF NOT EXISTS prediction_log (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker      text NOT NULL,
    run_id      text,
    current_price       double precision,
    target_base         double precision,
    target_low          double precision,
    target_high         double precision,
    valuation_method    text,
    archetype           text,
    routing_score       double precision,
    projection_score    double precision,
    event_weight        double precision,
    final_target        double precision,
    sigmoid_params      jsonb DEFAULT '{}'::jsonb,
    context_inputs      jsonb DEFAULT '{}'::jsonb,
    scenario_probabilities jsonb DEFAULT '{}'::jsonb,
    created_at  timestamptz DEFAULT now(),
    UNIQUE (ticker, run_id)
);

-- Index for calibration lookups (ticker + time range)
CREATE INDEX IF NOT EXISTS idx_prediction_log_ticker_created
    ON prediction_log (ticker, created_at DESC);

-- Enable RLS but allow all operations (anon key)
ALTER TABLE prediction_log ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'prediction_log' AND policyname = 'prediction_log_all'
    ) THEN
        CREATE POLICY prediction_log_all ON prediction_log FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;

-- If table already exists without the unique constraint, add it:
-- (safe to run — will no-op if constraint already exists from CREATE TABLE above)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'prediction_log_ticker_run_id_key'
    ) THEN
        ALTER TABLE prediction_log
            ADD CONSTRAINT prediction_log_ticker_run_id_key UNIQUE (ticker, run_id);
    END IF;
END $$;
