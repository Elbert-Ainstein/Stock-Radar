-- Thesis-driven analysis output, separate from the engine's DCF floor.
-- Populated by scripts/run_thesis.py — Claude-generated thesis with web search,
-- 5-filter setup quality, ranked risks/catalysts, position sizing.
--
-- This is the headline source for the v2 dashboard. The engine target lives
-- in `analysis` and is repositioned as the downside floor.

CREATE TABLE IF NOT EXISTS theses (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker          text NOT NULL,
    run_at          timestamptz NOT NULL DEFAULT now(),
    prompt_version  text NOT NULL,                      -- e.g. "v3" — from prompt YAML frontmatter
    -- Headline numbers (the dashboard's primary display)
    thesis_target   double precision,                   -- where the stock goes if thesis plays out
    breakout_price  double precision,                   -- thesis + sentiment amplification
    risk_adj_target double precision,                   -- risk-weighted EV
    -- Conviction / sizing
    conviction      text,                               -- "HIGH" | "MEDIUM" | "LOW" | "BROKEN"
    position_size_pct double precision,
    buy_below       double precision,
    trim_above      double precision,
    -- Structured analysis
    filters         jsonb DEFAULT '{}'::jsonb,          -- 5-filter pass/fail with evidence
    top_risks       jsonb DEFAULT '[]'::jsonb,
    top_catalysts   jsonb DEFAULT '[]'::jsonb,
    kill_triggers   jsonb DEFAULT '[]'::jsonb,
    -- Provenance / debugging
    spot_at_run     double precision,                   -- price when prompt ran
    trigger_reason  text,                               -- "manual" | "earnings" | "guidance_change" | etc
    markdown_path   text,                               -- path to full analysis markdown
    raw_response_blocks jsonb,                          -- full Claude content blocks (debugging)
    coverage_quality text,                              -- "HIGH" | "MEDIUM" | "LOW" — distinct domains cited
    cited_domains   jsonb DEFAULT '[]'::jsonb,
    -- Cost tracking
    input_tokens    integer,
    output_tokens   integer,
    web_search_count integer
);

CREATE INDEX IF NOT EXISTS idx_theses_ticker_run_at ON theses(ticker, run_at DESC);
CREATE INDEX IF NOT EXISTS idx_theses_prompt_version ON theses(prompt_version);
