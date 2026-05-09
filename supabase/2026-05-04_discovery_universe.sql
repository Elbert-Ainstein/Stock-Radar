-- ═══════════════════════════════════════════════════════════════
-- DISCOVERY UNIVERSE — self-evolving multi-market candidate registry
-- 2026-05-04
--
-- Persistent candidate registry for the self-evolving multi-market
-- discovery loop. One row per ticker, accumulates scan history across
-- runs. Distinct from the legacy `discovery_candidates` table (which
-- is per-run scout output): this is the upstream universe the scouts
-- read FROM; `discovery_candidates` holds per-run scan outputs.
--
-- Lifecycle: ingest → exploring → cheap-scan (Haiku) → promising/dropped
--            promising → full thesis (Opus) → promoted → watchlisted
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS discovery_universe (
  ticker         TEXT NOT NULL,           -- e.g. "AAPL", "0700.HK", "7203.T", "2330.TW", "005930.KS"
  market         TEXT NOT NULL,           -- "US" | "HK" | "TW" | "JP" | "KR"
  company_name   TEXT,
  sector         TEXT,
  first_seen     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_scanned   TIMESTAMPTZ,
  source         TEXT NOT NULL,           -- "yahoo_most_active" | "yahoo_gainers" | "watchlist_seed" | "news_extract" | "manual"
  cheap_score    REAL,                    -- 0-10 from Haiku cheap-scan, NULL until first scan
  cheap_verdict  TEXT,                    -- 1-sentence verdict from Haiku
  full_score     REAL,                    -- 0-10 from Opus full thesis if promoted
  status         TEXT NOT NULL DEFAULT 'exploring',  -- 'exploring' | 'promising' | 'promoted' | 'dropped' | 'watchlisted'
  scan_history   JSONB DEFAULT '[]'::jsonb,  -- array of {ts, score, verdict, model, version}
  market_cap_usd REAL,                    -- FX-normalized to USD (hard-fail on missing rate, never silent default)
  currency       TEXT,                    -- local currency (USD, HKD, TWD, JPY, KRW)
  PRIMARY KEY (ticker)
);

CREATE INDEX IF NOT EXISTS idx_universe_market         ON discovery_universe (market);
CREATE INDEX IF NOT EXISTS idx_universe_status         ON discovery_universe (status);
CREATE INDEX IF NOT EXISTS idx_universe_last_scanned   ON discovery_universe (last_scanned NULLS FIRST);
CREATE INDEX IF NOT EXISTS idx_universe_cheap_score    ON discovery_universe (cheap_score DESC NULLS LAST);
