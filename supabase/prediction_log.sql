-- Prediction logging for adaptive calibration
-- Apply via Supabase SQL Editor
CREATE TABLE IF NOT EXISTS prediction_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    run_id TEXT,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    current_price DOUBLE PRECISION,
    target_base DOUBLE PRECISION,
    target_low DOUBLE PRECISION,
    target_high DOUBLE PRECISION,
    valuation_method TEXT,
    archetype TEXT,
    routing_score DOUBLE PRECISION,
    projection_score DOUBLE PRECISION,
    event_weight DOUBLE PRECISION,
    final_target DOUBLE PRECISION,
    sigmoid_params JSONB DEFAULT '{}',
    context_inputs JSONB DEFAULT '{}',
    scenario_probabilities JSONB DEFAULT '{}'
);

-- For the price-tracker cron
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    prediction_id UUID REFERENCES prediction_log(id),
    ticker TEXT NOT NULL,
    days_elapsed INTEGER NOT NULL,
    actual_price DOUBLE PRECISION,
    recorded_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prediction_log_ticker ON prediction_log(ticker);
CREATE INDEX IF NOT EXISTS idx_prediction_log_run ON prediction_log(run_id);
CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_pred ON prediction_outcomes(prediction_id);
