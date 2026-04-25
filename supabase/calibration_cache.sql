-- Calibration cache: stores per-type calibration results
-- (event magnitude ratios, target convergence bias, etc.)
-- Keyed by calibration_type — upserted on each pipeline run.

CREATE TABLE IF NOT EXISTS calibration_cache (
    calibration_type TEXT PRIMARY KEY,
    data JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_calibration_cache_updated
ON calibration_cache (updated_at DESC);
