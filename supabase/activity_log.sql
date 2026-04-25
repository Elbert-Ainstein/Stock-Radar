-- Activity log table for structured pipeline event logging.
-- Supports the /logs dashboard page — transparent audit trail of
-- everything the bot does, organized by category and level.

CREATE TABLE IF NOT EXISTS activity_log (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category    TEXT NOT NULL,          -- pipeline, scout, analyst, engine, model, circuit_breaker, kill_condition, error
    level       TEXT NOT NULL DEFAULT 'info',  -- info, warn, error
    ticker      TEXT,                   -- NULL for system-level events
    source      TEXT NOT NULL,          -- script/module name (e.g. "run_pipeline.py", "scout_quant")
    title       TEXT NOT NULL,          -- short human-readable title
    message     TEXT,                   -- longer description
    run_id      TEXT,                   -- pipeline run ID for grouping
    metadata    JSONB DEFAULT '{}'::jsonb,  -- structured data (scores, durations, etc.)
    duration_ms INTEGER                 -- operation duration when applicable
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON activity_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_log_category ON activity_log (category);
CREATE INDEX IF NOT EXISTS idx_activity_log_level ON activity_log (level);
CREATE INDEX IF NOT EXISTS idx_activity_log_ticker ON activity_log (ticker);
CREATE INDEX IF NOT EXISTS idx_activity_log_run_id ON activity_log (run_id);

-- Auto-cleanup: keep only last 30 days of logs (optional, apply manually)
-- DELETE FROM activity_log WHERE created_at < NOW() - INTERVAL '30 days';
