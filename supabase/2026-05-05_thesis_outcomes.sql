-- ═══════════════════════════════════════════════════════════════
-- THESIS OUTCOMES — falsifiability mechanism for the thesis engine
-- 2026-05-05
--
-- For every thesis row in `theses`, we want to know what actually
-- happened to the stock price at T+30, T+90, T+180 days. This is
-- the only mechanism that lets the system tell whether thesis
-- targets are calibrated, optimistic, or systematically wrong.
--
-- Linked 1:1 to `theses` via thesis_id. Refreshed by
-- `scripts/outcomes_refresh.py` which pulls historical close
-- prices from yfinance and fills in the *_t30/*_t90/*_t180 cells.
--
-- Idempotent: refresh script can safely run repeatedly; it only
-- updates rows where the relevant time window has elapsed AND
-- the cell is currently NULL.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS thesis_outcomes (
  thesis_id        INT PRIMARY KEY REFERENCES theses(id) ON DELETE CASCADE,
  ticker           TEXT NOT NULL,
  thesis_date      TIMESTAMPTZ NOT NULL,         -- copied from theses.run_at
  thesis_target    REAL NOT NULL,                -- copied from theses.thesis_target
  spot_at_run      REAL NOT NULL,                -- copied from theses.spot_at_run
  conviction       TEXT,                          -- copied from theses.conviction
  position_size_pct REAL,                         -- copied from theses.position_size_pct

  -- Forward prices (filled by outcomes_refresh.py)
  price_t30        REAL,
  price_t30_date   DATE,                         -- actual close date used (handles weekends)
  price_t90        REAL,
  price_t90_date   DATE,
  price_t180       REAL,
  price_t180_date  DATE,

  -- Computed returns vs spot
  return_t30_pct   REAL,                         -- (price_t30 / spot_at_run - 1) * 100
  return_t90_pct   REAL,
  return_t180_pct  REAL,

  -- Calibration metric: how far did the stock actually go vs the thesis claim?
  -- (price_t180 / thesis_target) * 100 — 100 means thesis exactly hit, 50 means stock went halfway
  thesis_realized_pct_t180 REAL,

  -- Bookkeeping
  last_refreshed   TIMESTAMPTZ DEFAULT NOW(),
  notes            TEXT
);

CREATE INDEX IF NOT EXISTS idx_outcomes_ticker        ON thesis_outcomes (ticker);
CREATE INDEX IF NOT EXISTS idx_outcomes_thesis_date   ON thesis_outcomes (thesis_date);
CREATE INDEX IF NOT EXISTS idx_outcomes_last_refresh  ON thesis_outcomes (last_refreshed);

-- View: realized-vs-thesis calibration summary by ticker
CREATE OR REPLACE VIEW thesis_calibration AS
SELECT
  ticker,
  COUNT(*) AS n_theses,
  COUNT(price_t30)  AS n_t30,
  COUNT(price_t90)  AS n_t90,
  COUNT(price_t180) AS n_t180,
  AVG(return_t30_pct)   AS avg_return_t30,
  AVG(return_t90_pct)   AS avg_return_t90,
  AVG(return_t180_pct)  AS avg_return_t180,
  AVG(thesis_realized_pct_t180) AS avg_thesis_realized_pct,
  MIN(thesis_date) AS first_thesis,
  MAX(thesis_date) AS latest_thesis
FROM thesis_outcomes
GROUP BY ticker
ORDER BY ticker;
