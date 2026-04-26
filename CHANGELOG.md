# Stock Radar — Change Log

All notable changes made to the project are documented here, with reasoning and impact.

---

## [2026-04-26] Session: Pipeline Efficiency & Bug Fixes

### 16. Skip rebuild when scouts gather no new data (`scripts/run_pipeline.py`)
- **What:** Pipeline now detects when all scouts skipped (freshness window not expired) and short-circuits the analyst + model generation stages.
- **Why:** Pipeline was spending ~32 minutes and ~$3-4 in API costs regenerating identical models from stale signals.
- **Impact:** Saves 30+ minutes and all Claude/Perplexity costs on redundant runs. Use `--rebuild-only` to force a rebuild.

### 17. Filter analyst signals to active stocks only (`scripts/analyst.py`)
- **What:** Analyst now queries active tickers from the `stocks` table and filters `latest_signals` to only include signals for active stocks.
- **Why:** Was loading 51 signals (from old 50-stock watchlist) instead of 12, creating noise in logs.
- **Impact:** Cleaner logs, slightly faster analyst processing.

### 18. Limit revenue sanity checks to last 8 quarters (`scripts/finance_data.py`)
- **What:** Revenue sanity check now only scans the most recent 8 quarters (2 years) instead of all history.
- **Why:** ASML was flagging 2010 Q1 revenue jumps — 16-year-old data noise, not actionable.
- **Impact:** Eliminates false positive warnings on mature companies with long data histories.

### 19. Create `prediction_log` table (`supabase/2026-04-26_prediction_log.sql`)
- **What:** Added migration SQL for the `prediction_log` table with proper schema and RLS policy.
- **Why:** Calibration and prediction logging were failing with `Could not find the table 'public.prediction_log'` error.
- **Impact:** Run this migration in Supabase SQL Editor to enable prediction tracking and calibration feedback.

### 20. Eliminate redundant engine runs in prediction logging (`scripts/run_pipeline.py`)
- **What:** Prediction logging now reads targets from the analyst's already-computed results instead of re-running `fetch_financials` + `build_target` for each stock.
- **Why:** Engine was running 2-3x per stock per pipeline: once in analyst, once in model generator post-save, once in prediction logging.
- **Impact:** Eliminates 12+ redundant EODHD API calls and engine computations per run.

### 21. Fix model_export.py KeyError: 'discount_rate' (`scripts/model_export.py`)
- **What:** Removed `discount_rate` from the `scenario_keys` list in `_build_assumptions`.
- **Why:** `discount_rate` was intentionally removed from `SCENARIO_OFFSETS` (constant WACC across scenarios) but the export still referenced it.
- **Impact:** Fixes crash when exporting models to Excel.

---

## [2026-04-25] Session: Watchlist Trim & Pipeline Optimization

### 12. Trim watchlist to 6 core stocks (`config/watchlist.json`, `CLAUDE.md`)
- **What:** Removed all 44 expansion stocks (Wave 1 + Wave 2), keeping only: LITE, PLTR, RKLB, ACHR, CELH, SNDK.
- **Why:** 50 stocks made pipeline runs take ~2 hours. Core 6 stocks are the actual investment focus; extras were added to test system scaling but created unnecessary cost and runtime.
- **Files:** `config/watchlist.json`, `CLAUDE.md`

### 13. Parallelize Perplexity research queries (`scripts/generate_model.py`)
- **What:** Changed `research_financials()` from sequential 4-query loop (with 1.5s sleep between each) to concurrent 4-query execution via ThreadPoolExecutor. Eliminated the inter-query sleep entirely.
- **Why:** Each model generation spent ~10s on sequential Perplexity queries (4 × 2-3s response + 4 × 1.5s sleep). Concurrent execution reduces this to ~3s per stock. For 6 stocks, saves ~40s total.
- **Files:** `scripts/generate_model.py`
- **Before:** ~10s per stock for Perplexity research (sequential)
- **After:** ~3s per stock (concurrent)

### 14. Increase default model parallelism from 3 to 5 (`scripts/generate_model.py`)
- **What:** Changed default `max_workers` for `--all` from 3 to 5.
- **Why:** With only 6 stocks, 5 parallel workers means nearly all stocks generate models concurrently. Claude and Perplexity APIs can handle this concurrency.
- **Files:** `scripts/generate_model.py`

### 15. Fix PipelineMetrics.scout_metrics attribute error (`scripts/observability.py`)
- **What:** Added public `scout_metrics` property to PipelineMetrics class. The `_scouts` list was private but `run_pipeline.py` referenced it as `metrics.scout_metrics`, causing `AttributeError` crash.
- **Why:** This was the bug causing "PIPELINE FAILED after 3.9s" on GitHub Actions.
- **Files:** `scripts/observability.py`, `scripts/run_pipeline.py`

---

## [2026-04-25] Session: Bug Audit & Pipeline Reliability Fixes

### 1. Auto-seed stocks table after DB wipe (`scripts/run_pipeline.py`)
- **What:** Added `_ensure_stocks_seeded()` helper that checks if the `stocks` table is empty and, if so, populates it from `config/watchlist.json` via `seed_stocks_from_watchlist()`. Called at the start of both full pipeline and mini-pipeline runs.
- **Why:** After a database wipe, the pipeline would write signals and analysis but the dashboard couldn't find any stocks (it reads from the `stocks` table). This was the root cause of "models don't show up."
- **Files:** `scripts/run_pipeline.py`

### 2. Fix generate_model.py UPDATE → UPSERT (`scripts/generate_model.py`)
- **What:** Changed `update_stock_in_supabase()` from `.update()` to `.upsert(on_conflict="ticker")`. Now ensures `ticker`, `name`, and `active` fields are always present so a missing stock row is created rather than silently skipped.
- **Why:** After a DB wipe or for new tickers, the UPDATE matched zero rows and model data was silently lost. The dashboard would show the stock but with no model.
- **Files:** `scripts/generate_model.py`

### 3. Add ticker filtering to mini-pipeline (`scripts/utils.py`, `scripts/run_pipeline.py`)
- **What:** `run_single_ticker()` now sets `PIPELINE_TICKER_FILTER` env var. `get_watchlist()` respects this filter, returning only the matching stock. This prevents the quant scout and analyst from scanning all 50 stocks when only one was requested.
- **Why:** Previously, adding a single stock via the dashboard triggered a full watchlist scan in both quant and analyst stages, wasting ~5 minutes of API calls.
- **Files:** `scripts/utils.py`, `scripts/run_pipeline.py`

### 4. Run more scouts in mini-pipeline (`scripts/run_pipeline.py`)
- **What:** `run_single_ticker()` now runs 4 scouts in parallel (quant, insider, social, fundamentals) instead of just quant. Uses ThreadPoolExecutor with 4 workers.
- **Why:** A newly added stock only had quant data, producing a composite score from a single factor. Now it gets 4 signal sources for better initial coverage.
- **Files:** `scripts/run_pipeline.py`

### 5. Fix get_watchlist() missing archetype field (`scripts/utils.py`)
- **What:** Added `"archetype": row.get("archetype"),` to the Supabase row mapping in `get_watchlist()`.
- **Why:** Smart routing in the full pipeline reads `stock.get("archetype")` to route scouts per-stock. Without the field, every stock was treated as having no archetype, disabling smart routing.
- **Files:** `scripts/utils.py`

### 6. Dynamic fiscal year references in research queries (`scripts/generate_model.py`)
- **What:** Replaced hardcoded `FY2025 FY2026 FY2027` and `2026 2027` in Perplexity research queries with dynamically computed years based on `datetime.now().year`. Also fixed `query_labels` to have 4 entries matching 4 queries.
- **Why:** Hardcoded years go stale. By April 2027 the queries would be asking for historical data instead of forward guidance.
- **Files:** `scripts/generate_model.py`

### 7. Remove dashboard auto-run on empty data (`app/dashboard/Dashboard.tsx`)
- **What:** Removed the `useEffect` that auto-triggered `runPipeline(true)` when no signal data existed. Added a comment explaining the removal.
- **Why:** After a DB wipe with 50 stocks, the dashboard would silently start a 10-15 minute free pipeline run without user consent on every page load until signals existed.
- **Files:** `app/dashboard/Dashboard.tsx`

### 8. Split pipeline into scouts-only / rebuild-only modes (`scripts/run_pipeline.py`)
- **What:** Added `--scouts-only` and `--rebuild-only` CLI flags. `--scouts-only` runs all scouts in parallel but skips analyst, model generation, feedback loop, and prediction logging. `--rebuild-only` skips scouts entirely and runs analyst + models against existing signals in Supabase. The default (no flag) runs everything as before.
- **Why:** Separates cheap work (signal gathering, ~2-5 min, no Claude tokens) from expensive work (analyst + models, ~30-60 min, uses Claude + Perplexity). Enables scheduling scouts frequently and rebuilds less often to save API costs.
- **Files:** `scripts/run_pipeline.py`

### 9. GitHub Actions workflows for 24/7 automation
- **What:** Added three workflow files: `scout-refresh.yml` (twice daily at 6am/6pm UTC, `--scouts-only`), `analyst-rebuild.yml` (daily at 7am UTC, `--rebuild-only`), and `full-pipeline.yml` (manual trigger with mode selector). All workflows use `concurrency` groups to prevent overlapping runs and include artifact upload for logs.
- **Why:** Pipeline needs to run 24/7 regardless of whether any device is on. GitHub Actions provides free cron scheduling with secrets management, no VPS required.
- **Setup:** Push repo to GitHub → Settings → Secrets → add SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY, PERPLEXITY_API_KEY, EODHD_API_KEY, ALPHA_VANTAGE_API_KEY, GEMINI_API_KEY.
- **Files:** `.github/workflows/scout-refresh.yml`, `.github/workflows/analyst-rebuild.yml`, `.github/workflows/full-pipeline.yml`

### 10. Centralized scout cadence tiering (`scripts/registries.py`, all scouts)
- **What:** Added `SCOUT_CADENCE_HOURS` dict to `registries.py` — the single source of truth for how often each scout's signals go stale. Three tiers: daily (quant 12h, news 18h, social/insider 20h), periodic (catalyst/fundamentals/moat 48h), and weekly (youtube/filings 168h). Updated `get_fresh_tickers()` in `utils.py` to auto-resolve cadence from the registry when no explicit `max_age_hours` is passed. Removed all hardcoded hour values from 7 scout files.
- **Why:** Previously each scout had a hardcoded `max_age_hours` — changing a cadence meant editing a random scout file and hoping you found the right one. Now all cadences are in one place, tunable without touching scout code. The tiering reflects real signal decay: prices go stale in hours, competitive moats don't change for days.
- **Files:** `scripts/registries.py`, `scripts/utils.py`, `scripts/scout_quant.py`, `scripts/scout_news.py`, `scripts/scout_catalyst.py`, `scripts/scout_moat.py`, `scripts/scout_insider.py`, `scripts/scout_fundamentals.py`, `scripts/scout_social.py`

### 9. Signal freshness checks across all scouts
- **What:** Added `get_fresh_tickers()` calls to scout_quant (12h), scout_news (20h), scout_catalyst (20h), scout_moat (20h), scout_insider (20h), scout_fundamentals (20h), and scout_social (20h). Each scout now skips stocks that already have recent signals in Supabase.
- **Why:** With 50 stocks, re-scanning stocks that were just scanned hours ago wastes API calls and time. First run processes all 50; subsequent runs within the same day skip most and only process new/stale stocks.
- **Files:** `scripts/scout_quant.py`, `scripts/scout_news.py`, `scripts/scout_catalyst.py`, `scripts/scout_moat.py`, `scripts/scout_insider.py`, `scripts/scout_fundamentals.py`, `scripts/scout_social.py`

### 9. YouTube scout moved to --full only (`scripts/run_pipeline.py`)
- **What:** YouTube scout (`scout_youtube`) is no longer included in default or smart-mode pipeline runs. It only runs with `--full` flag.
- **Why:** YouTube scout is the slowest (~2 min/stock × 50 stocks = ~100 min) and returns 0 results for most stocks. Moving it to --full cuts default pipeline time significantly.
- **Files:** `scripts/run_pipeline.py`

### 10. Within-scout stock-level parallelism
- **What:** Added `ThreadPoolExecutor` to process stocks in parallel within each scout: quant (6 workers), insider (4 workers), news (3 workers). Social scout already had parallelism (4 workers).
- **Why:** Sequential processing of 50 stocks within each scout was the biggest bottleneck. With parallelism, each scout completes in the time of its slowest stock rather than the sum of all stocks.
- **Before:** Each scout processed ~50 stocks sequentially (e.g., quant: 50 × ~3s = ~150s)
- **After:** Each scout processes ~50 stocks in parallel (e.g., quant: ~50/6 batches × ~3s = ~25s)
- **Files:** `scripts/scout_quant.py`, `scripts/scout_insider.py`, `scripts/scout_news.py`

---

## [2026-04-24] Session: Confidence Propagation + Feedback Calibration (Resilience Phase 2-3)

### 1. Confidence propagation through target engine (`scripts/target_engine.py`)
- **What:** `TargetResult` dataclass now carries `confidence_score` (0.0-1.0), `confidence_label` ("high"/"medium"/"low"), and `data_quality` dict. `build_target()` accepts optional `analyst_confidence` parameter and auto-runs `check_target_quality()` at the end, degrading confidence by scenario spread width and circuit-breaker flags.
- **Why:** Confidence must flow end-to-end — scout → analyst → engine → frontend — so users know which targets are data-rich vs. data-poor.
- **Files:** `scripts/target_engine.py`, `scripts/target_api.py`, `scripts/run_pipeline.py`

### 2. Confidence indicators on dashboard and model page (`app/dashboard/StockRow.tsx`, `app/model/TargetPriceModel.tsx`)
- **What:** Dashboard scout completeness badge now shows 3-level confidence (high/medium/low) with numeric percentage in tooltip. Model page's ImpliedTargetBox shows engine confidence as a colored pill badge below the target price. Updated `DataQuality` interface to include `"medium"` level and numeric `confidence_score`.
- **Why:** Silent degradation → visible degradation. Users need to see "this target is based on 4/9 scouts with 55% confidence" right next to the price.
- **Files:** `lib/data.ts`, `app/dashboard/StockRow.tsx`, `app/model/TargetPriceModel.tsx`, `app/model/types.ts`

### 3. Event magnitude calibration + target convergence tracking (`scripts/calibration.py`)
- **What:** New `calibration.py` module with two feedback readers: (a) `calibrate_event_magnitudes()` — compares predicted event impacts to actual price changes, produces per-event-type calibration ratios; (b) `compute_target_convergence()` — tracks systematic bias by archetype and sector from prediction_log vs prediction_outcomes. Calibration ratios auto-applied in `event_reasoner.py` to scale future predictions. Results cached in new `calibration_cache` Supabase table.
- **Why:** The pipeline needs to learn from its mistakes. If earnings_beat events consistently over-predict by 30%, the ratio (0.70) automatically dampens future predictions.
- **Files:** `scripts/calibration.py` (new), `scripts/event_reasoner.py`, `scripts/run_pipeline.py`, `supabase/calibration_cache.sql` (new)

### 4. Pipeline wiring
- **What:** `run_pipeline.py` builds analyst_confidence_map after analyst stage and passes it through to `build_target()`. Calibration runs after the feedback loop. `target_api.py` loads analyst confidence from the latest analysis row in Supabase.
- **Files:** `scripts/run_pipeline.py`, `scripts/target_api.py`

---

## [2026-04-24] Session: Activity Logs Page

### 1. Activity log infrastructure (`scripts/activity_logger.py`, `supabase/activity_log.sql`)
- **What:** New `activity_log` Supabase table with structured columns (category, level, ticker, source, title, message, run_id, metadata jsonb, duration_ms). Python logger module with `log_info()`, `log_warn()`, `log_error()`, and `LogTimer` context manager. Fire-and-forget — never breaks the pipeline.
- **Why:** The system logs everything but it's all print() to stdout. No queryable, filterable, persistent record of what happened. The assessment called it "a system with a perfect diary and zero self-awareness."
- **Files:** `scripts/activity_logger.py` (new), `supabase/activity_log.sql` (new)

### 2. Pipeline + analyst logging wired up (`scripts/run_pipeline.py`, `scripts/analyst.py`)
- **What:** Pipeline start/end events logged with run_id, mode, duration, stock count. Analyst circuit breaker warnings logged as warn-level entries with full data_quality metadata. All logging is gracefully degraded (optional import, fire-and-forget writes).
- **Why:** Logs page needs data to display. These are the highest-value log points — pipeline lifecycle and data quality warnings.
- **Files:** `scripts/run_pipeline.py`, `scripts/analyst.py`

### 3. Logs API route (`app/api/logs/route.ts`)
- **What:** `GET /api/logs` with filters for category, level, ticker, run_id, time range. Supports pagination (limit/offset). Returns both flat log list and grouped-by-run-id view for timeline rendering.
- **Files:** `app/api/logs/route.ts` (new)

### 4. /logs dashboard page (`app/logs/page.tsx`, `app/logs/LogsDashboard.tsx`)
- **What:** Full-page activity log viewer at `/logs`. Features: category/level/ticker filtering, auto-refresh (15s), expandable entries showing full message + metadata, color-coded by level (info=neutral, warn=amber, error=red), category icons, duration badges, pagination. Empty state guides user to create the Supabase table.
- **Why:** Transparent audit trail — everything the bot does, organized and accessible. Not raw JSON dumps, but structured entries with human-readable titles, expandable details, and filterable categories.
- **Files:** `app/logs/page.tsx` (new), `app/logs/LogsDashboard.tsx` (new)

### 5. Navigation link (`app/dashboard/Dashboard.tsx`)
- **What:** Added "Logs" link to dashboard header navigation alongside Watchlist, Discovery, Models, Ask AI.

---

## [2026-04-24] Session: Contract Layer + Circuit Breakers (Resilience Phase 1)

### 1. Single-source registries (`scripts/registries.py`, `lib/registries.ts`)
- **What:** Created canonical registry files for Python and TypeScript. ALL scout names, valuation methods, archetypes, lifecycle stages, and circuit breaker thresholds defined once.
- **Why:** Registry fragmentation was the #1 structural failure category — scouts were defined in 5 places independently, archetypes in 4, valuation methods in 4. Adding a scout or archetype required editing every file, and missing one caused silent degradation (3 scouts invisible on dashboard).
- **Files:** `scripts/registries.py` (new), `lib/registries.ts` (new), `scripts/analyst.py`, `scripts/research_manager.py`, `scripts/feedback_loop.py`, `scripts/run_pipeline.py`, `scripts/target_engine.py`, `scripts/generate_model.py`, `lib/data.ts`, `app/model/types.ts`
- **Impact:** Future scout/archetype/method additions require editing ONE file per language. All consumers import from the canonical source.

### 2. Circuit breaker: Scout → Analyst boundary (`scripts/analyst.py`)
- **What:** After computing composite score, analyst now checks: (1) how many scouts actually contributed scored signals — flags LOW_CONFIDENCE if < 4; (2) inter-scout disagreement on overlapping metrics (revenue growth quant vs fundamentals). Produces `data_quality` field in output.
- **Why:** Silent degradation — when scouts fail, the composite score is computed from incomplete data with no visible warning. Assessment identified this as the most dangerous failure mode: "plausible-looking wrong numbers."
- **Impact:** `data_quality.confidence` propagates to frontend for display. Circuit breaker logs warnings but does not halt — downstream consumers decide what to do.

### 3. Circuit breaker: Analyst → Engine boundary (`scripts/target_engine.py`)
- **What:** New `check_target_quality()` function that validates: (1) extreme target-to-price ratio (>3x); (2) target swing > 30% between runs; (3) composite score regime change (>2 points); (4) kill condition / signal contradiction.
- **Why:** The cascade path from the assessment: stale data → slightly wrong growth → compounded 5-year forecast → wrong terminal value (60-80% of EV) → wrong target → user trusts it.
- **Impact:** Returns confidence level + warnings + machine-readable flags. Frontend/API can display warnings alongside targets.

### 4. Circuit breaker: Engine → Frontend boundary (`app/api/model/[ticker]/route.ts`)
- **What:** API route now checks target payload before sending to dashboard: (1) extreme prediction warning; (2) required fields present and non-null; (3) scenario ordering sanity (low < base < high). Attaches `_data_quality` metadata to response.
- **Why:** Last line of defense before a wrong number reaches the user. Assessment: "Circuit breakers do not fix bad data. They stop the cascade so bad data does not reach the user as a confident-looking number."
- **Impact:** Frontend can render confidence badges and warnings for flagged targets.

### 5. Scout completeness indicator on dashboard (`app/dashboard/StockRow.tsx`, `lib/data.ts`)
- **What:** Every stock card now shows "X/9 data" badge with color coding (green for high confidence, amber for low). Sourced from analyst `data_quality` field (if available) or computed from distinct scout count in signals.
- **Why:** Assessment's "simplest immediate fix" — eliminates the most dangerous form of silent degradation: the user not knowing that scouts failed. Data already existed in the system; it just wasn't surfaced.
- **Impact:** User immediately sees "3/9 data" in amber and knows half the picture is missing — vs. previously seeing a confident score with no indication of incomplete input.

---

## [2026-04-24] Session: Dashboard Bug Fixes — Event Impact Display + Scout Registry + Pipeline Cancellation

### 1. Fix event impact over-adjustment (-$608 LITE, -$203 AMD) (`app/model/TargetPriceModel.tsx`)
- **What:** Event delta was computed as `blend.final_target - liveSliderTarget`, but `blend.final_target` was anchored to the pipeline engine's base (a different number from the live slider target). This caused absurd deltas when the two bases diverged.
- **Fix:** Compute event delta from `blend.event_pct_weighted` applied to the live slider target, so the numbers are always internally consistent.
- **Before:** LITE showed -$608 events on $676 base = $68 target (-92%); AMD showed -$203 on $340 = $137 (-61%).
- **After:** Event delta is correctly percentage-based. If blend says -5.2% events, delta = $676 × -5.2% = -$35.

### 2. Add missing scouts to dashboard registry (`lib/data.ts`)
- **What:** `SCOUT_REGISTRY` only had 6 scouts (quant, insider, social, news, fundamentals, youtube). Catalyst, Moat, and Filings scouts were missing — their signals weren't counted in the "X/Y scouts active" display.
- **Fix:** Added catalyst, moat, and filings to the registry. Dashboard now shows 9 scouts.
- **Before:** Dashboard showed "4/6 scouts active" even when 8 scouts ran successfully.
- **After:** Dashboard correctly reports all scouts including catalyst, moat, and filings.

### 3. Add missing scouts to analyst name_map (`scripts/analyst.py`)
- **What:** The `_load_scouts_from_supabase` function's `name_map` only mapped 6 scout names. While the fallback `.capitalize()` handled unmapped scouts, adding catalyst/moat/filings to the map ensures explicit correctness.
- **Fix:** Added "catalyst": "Catalyst", "moat": "Moat", "filings": "Filings" to name_map.

### 4. Pipeline cancellation on stock deletion (`scripts/run_pipeline.py`, `app/api/stocks/delete/route.ts`)
- **What:** When a user added a stock (triggering a mini-pipeline) then immediately deleted it, the pipeline continued running all stages (quant → analyst → model generation), wasting API calls on a stock that no longer exists.
- **Fix:** Delete API now writes a `.pipeline-cancel-{TICKER}` file. The mini-pipeline checks for this cancellation signal between each stage and halts early if found, cleaning up the cancel file.
- **Before:** Pipeline ran to completion even for deleted stocks.
- **After:** Pipeline detects deletion within seconds and stops at the next stage boundary.

### 5. Add "Stop Pipeline" button + DELETE /api/pipeline endpoint (`app/api/pipeline/route.ts`, `app/dashboard/Dashboard.tsx`)
- **What:** No way to manually stop a running pipeline from the dashboard. If a wrong ticker was added or the pipeline was stuck, the only option was to wait 10-15 minutes or SSH in and `pkill`.
- **Fix:** Added a `DELETE /api/pipeline` endpoint that kills all pipeline-related Python processes (`run_pipeline.py`, all scouts, analyst, generate_model) and cleans up lock/progress files. The dashboard's "Run Pipeline" button transforms into a red "Stop Pipeline" button while the pipeline is running.
- **Before:** No stop mechanism; had to manually kill processes.
- **After:** One-click stop from the dashboard; processes are killed immediately.

---

## [2026-04-24] Session: Institutional DCF Overhaul + Infrastructure Build-out

### 1. Gordon Growth + ROIIC Fade Terminal Value (`scripts/target_engine.py`)
- **What:** Replaced dual 50/50 EV/EBITDA + EV/FCF-SBC exit-multiple blend with a single Gordon Growth model featuring a 7-year ROIIC fade period
- **How:** Growth fades linearly from g_terminal to g_perpetuity (≤2.5%) over ROIIC_FADE_YEARS=7, then applies steady-state Gordon Growth
- **Why:** Audit identified the old dual blend as a "Trojan Horse" mixing intrinsic (DCF) with relative (exit multiples). Pure Gordon Growth is theoretically clean
- **Fallback:** Exit-multiple method retained as fallback when Gordon returns None

### 2. Bottom-Up Beta WACC (`scripts/target_engine.py`)
- **What:** Replaced blanket 12% WACC with company-specific WACC derived from Damodaran sector unlevered betas
- **How:** Re-levers unlevered beta with company D/E ratio (Modigliani-Miller with taxes), then CAPM: Ke = Rf + βL × ERP. WACC = weighted average of Ke and Kd(1-t). 18 sector betas included
- **Clamped:** WACC bounded to [6%, 22%] to prevent absurd values

### 3. Archetype-Dependent Forecast Horizons (`scripts/target_engine.py`)
- **What:** GARP=5yr, transformational=7yr, cyclical=8yr, compounder=10yr explicit forecast periods instead of a fixed global constant
- **Added:** ARCHETYPE_FORECAST_YEARS, ARCHETYPE_VALUATION_YEAR, ARCHETYPE_MARGIN_RAMP dicts and _archetype_params() function

### 4. Alternative Valuation Methods (`scripts/target_engine.py`)
- **What:** Added reverse_dcf() — binary search for implied growth rate given current market price — and residual_income_model() — book value + PV of excess earnings above cost of equity

### 5. Volatility-Scaled Event Caps (`scripts/event_reasoner.py`)
- **What:** Replaced fixed ±10%/±15% event impact caps with k×σ_firm scaling. Single event cap = 0.4×annualized_vol, total cap = 0.6×annualized_vol
- **How:** _estimate_annualized_vol() uses 6-month yfinance history, daily vol × √252, clamped to [0.15, 1.50]

### 6. Inverse-Variance Sample Selection (`scripts/self_consistency.py`)
- **What:** Replaced "closest to mean base price" heuristic with inverse-variance weighting across all numeric fields (prices + defaults)
- **Why:** Old method only looked at one field and could pick outliers on other dimensions

### 7. Damodaran Lifecycle × Morningstar Moat 2D Grid (`scripts/generate_model.py`)
- **What:** Added lifecycle_stage (startup/high_growth/mature_growth/mature_stable/decline) and moat_width (none/narrow/wide) to archetype classification schema

### 8. SEC EDGAR XBRL Point-in-Time Data Layer (`scripts/edgar_xbrl.py`)
- **What:** New module for fetching financial data directly from SEC 10-K/10-Q filings with filing dates for backtesting-safe data retrieval
- **Features:** CIK lookup via company_tickers.json, rate limiting, company facts fetching, quarterly data extraction with automatic concept selection (picks most recent XBRL concept)
- **Why:** Eliminates look-ahead bias — filing date = knowledge date

### 9. Walk-Forward + CPCV Backtesting Harness (`scripts/backtest.py`)
- **What:** New module implementing anchored/rolling walk-forward and Combinatorial Purged Cross-Validation (de Prado ch.12) with embargo gaps
- **Metrics:** Hit rate, Information Coefficient, mean return, annualized Sharpe per fold
- **CPCV:** Deflated Sharpe p-value for multiple-testing correction (Bailey & de Prado 2014)

### 10. Alpaca Paper-Trading Bridge (`scripts/paper_trade.py`)
- **What:** Translates model outputs + composite scores into paper-trade orders on Alpaca's paper-trading API
- **Sizing:** Half-Kelly with 10% per-position cap, minimum score threshold, top-15 positions
- **Features:** Rebalancing, dry-run mode, portfolio state logging, daily P&L tracking

### 11. Factor Exposure Analysis (`scripts/factor_exposure.py`)
- **What:** OLS regression of stock/portfolio returns against factor proxy ETFs (market, size, value, growth, momentum, quality, low_vol)
- **Output:** Per-factor beta, t-stat, p-value, variance contribution. Alpha (annualized), R², systematic vs idiosyncratic risk decomposition
- **Warnings:** Flags high single-factor exposures and low diversification

### 12. Experiment Tracking (`scripts/experiment_tracker.py`)
- **What:** Lightweight experiment tracker with local JSON-lines storage + optional MLflow integration
- **Features:** Context manager API, parameter/metric/artifact logging, git commit tracking, run comparison, best-run search

### 13. Drift Monitoring (`scripts/drift_monitor.py`)
- **What:** Three-pronged drift detection: feature drift (KS test + Evidently reports), prediction drift (PSI + KS), concept drift (IC degradation)
- **Evidently:** HTML drift reports generated to data/drift_reports/ when evidently is installed

### 14. Market Regime Detection & Macro Overlay (`scripts/regime_detection.py`)
- **What:** Hidden Markov Model (Hamilton 1989) on SOX returns to identify risk-on/risk-off/transition regimes
- **Macro overlay:** VIX, yield curve, credit stress, USD trend. Outputs bear probability adjustment and position scaling
- **Fallback:** Heuristic vol-percentile regime detection when hmmlearn not installed

### 15. HRP Position Sizing (`scripts/position_sizing.py`)
- **What:** Hierarchical Risk Parity (López de Prado 2016) as alternative to Kelly sizing
- **How:** Correlation distance → hierarchical clustering → quasi-diagonalization → recursive bisection
- **Blended mode:** 60% Kelly + 40% HRP for conviction-weighted diversification

### 16. Property-Based Testing (`scripts/test_engine.py`)
- **What:** 5 Hypothesis fuzz tests: forecast length invariant, revenue non-negativity, FCF ≤ EBITDA margin, Gordon monotonicity, WACC bounds
- **Total tests:** 41 (up from 19 at start of audit response), all passing

### Files Modified
- `scripts/target_engine.py` — Gordon+ROIIC, bottom-up WACC, archetype horizons, reverse-DCF, RIM
- `scripts/event_reasoner.py` — vol-scaled event caps
- `scripts/self_consistency.py` — inverse-variance selection
- `scripts/generate_model.py` — lifecycle_stage + moat_width in schema
- `scripts/feedback_loop.py` — IC wired into run_feedback_loop()
- `scripts/test_engine.py` — 22 new tests

### Files Created
- `scripts/edgar_xbrl.py` — SEC EDGAR XBRL data layer
- `scripts/backtest.py` — Walk-forward + CPCV backtesting
- `scripts/paper_trade.py` — Alpaca paper-trading bridge
- `scripts/factor_exposure.py` — Factor exposure analysis
- `scripts/experiment_tracker.py` — Experiment tracking
- `scripts/drift_monitor.py` — Drift monitoring
- `scripts/regime_detection.py` — Regime detection + macro overlay
- `scripts/position_sizing.py` — HRP + blended position sizing

---

## [2026-04-24] Session: Structured Outputs + Watchlist Expansion + P1 Task Sprint

### 1. Watchlist Expanded to 50 Stocks (`config/watchlist.json`, `CLAUDE.md`)
- **What:** Added 36 new stocks across 16 sectors to reach the audit-recommended 50-stock universe
- **Sectors added:** Semiconductors (MRVL, WOLF, CEVA, MTSI), AI Software (PATH, SOUN, BBAI, AI), Cybersecurity (S, ZS), Cloud/Data (NET, MDB, CFLT), Biotech (RXRX, BEAM, CRSP), Clean Energy (ENPH, BE, FSLR), Fintech (SOFI, AFRM, HOOD), Space (ASTS, LUNR, RDW), Quantum Computing (IONQ, RGTI, QBTS), Consumer/EdTech (DUOL, GRAB), Robotics/Mobility (SERV, JOBY), EV (RIVN), Observability (DDOG), Industrial (AXON, TMC)
- **Verification:** All 50 tickers confirmed with live price data via yfinance
- **Why:** Audit flagged all-semi watchlist as statistically meaningless (effective independent bets ≈ 3.4). Sector-stratified universe enables meaningful IC measurement and factor exposure analysis

### 2. Schema-Drift Fix (`supabase/migration.sql`, `scripts/supabase_helper.py`, `scripts/run_pipeline.py`)
- **What:** Updated migration.sql to include ALL columns the code expects (archetype, research_cache on stocks table, plus new archetype_history table). Added `validate_schema()` function that probes Supabase at pipeline startup and warns about missing columns
- **Before:** Code silently stripped columns that didn't exist in DB — data loss went unnoticed
- **After:** Pipeline startup validates schema, logs specific missing columns with "run migration.sql to fix" guidance. Column-stripping retained as degraded-mode fallback but now tagged as a defect

### 3. SNDK Data Integrity & Delisted-Ticker Awareness (`scripts/finance_data.py`)
- **What:** Added `TICKER_DATA_CUTOFFS` dict mapping tickers to earliest valid data date, and `DELISTED_TICKERS` dict for immediate rejection. SNDK cutoff set to Feb 2025 (re-IPO date)
- **How:** `_apply_data_cutoff()` filters quarterly/annual periods by parsing period labels (1Q25, 2024, etc.) and dropping periods before the cutoff. Applied automatically in `fetch_financials()` after provider fetch + fallback
- **Before:** SNDK could ingest 2016-era SanDisk data from yfinance, contaminating models
- **After:** Pre-Feb-2025 SNDK data automatically dropped with warning

### 4. LLM Self-Consistency Sampling (`scripts/self_consistency.py`, `scripts/generate_model.py`)
- **What:** New module that samples LLM model generation N times and reports mean ± stderr for scenario prices, probabilities, model defaults, and archetype consensus
- **Config:** `SELF_CONSISTENCY_N` env var (default: 1 for backward compat). Set to 5+ for production sampling
- **Integration:** `process_stock()` in generate_model.py auto-uses self-consistency when N>1, picks the result closest to mean base price, and attaches consistency metadata for observability
- **High-variance detection:** Fields with coefficient of variation >15% are flagged in `high_variance` list

### 5. Research Memo Generator (`scripts/research_memo.py`)
- **What:** Auto-generates 2-minute Markdown research memos per stock covering thesis, key numbers, scenarios, top criteria, kill condition, and model notes
- **Usage:** `python research_memo.py --ticker LITE` (single), `--all` (all watchlist), `--digest` (combined overview table)
- **Output:** Individual memos in `data/memos/`, daily digest with upside-sorted watchlist table

---

## [2026-04-24] Session: Replace JSON Repair Pipeline with Structured Outputs

### 1. Anthropic Structured Outputs Integration (`scripts/generate_model.py`)
- **What:** Replaced the 4-layer JSON repair pipeline (brace extraction → trailing comma fix → truncation repair → retry with compact prompt) with Anthropic's Structured Outputs, which guarantees schema-conformant JSON at the API level
- **How:** Added `output_config.format.json_schema` to the Claude API request body with a comprehensive `MODEL_OUTPUT_SCHEMA` constant that mirrors the MODEL_GEN_PROMPT template exactly
- **Schema covers:** thesis, sector, kill_condition, archetype (with enum for 5 types), valuation_method (pe/ps), model_defaults (7 fields including nullable pe_multiple/ps_multiple), scenarios (bull/base/bear with probability/price/trigger), criteria (array with 9 fields including enum constraints), target_notes, divergence_note (nullable)
- **Legacy fallback retained:** The old repair code is kept as a safety net but tagged with "this is a defect — please investigate" logging. It should never fire with structured outputs
- **Before:** ~70 lines of repair code across 4 fallback layers; ~5-10% of generations needed repair; truncated responses required costly retries
- **After:** Zero-repair path; JSON is guaranteed valid by the API; repair_method reports "structured_output" for clean observability
- **Live tested:** AAPL test returned valid JSON on first parse with all 11 required fields, correct enum values, and proper nullable handling
- **Files:** `scripts/generate_model.py`

### 2. Schema Regression Tests (`scripts/test_engine.py`)
- **Added 6 new tests** in `TestModelOutputSchema` class (total: 25 tests, up from 19)
- Tests cover: required keys completeness, additionalProperties=false enforcement, valid model key matching, jsonschema validation (if installed), archetype enum values, criteria variable enum
- **Files:** `scripts/test_engine.py`

---

## [2026-04-24] Session: Institutional Audit Response + Watchlist Expansion

### 1. Watchlist Expanded from 6 to 14 Stocks (`config/watchlist.json`)
- **Added 8 new stocks:** ASML (semi equipment/monopoly), 6082.HK (Chinese GPU), COHR (AI photonics), NOK (telecom infra), ALAB (AI connectivity), U (gaming/3D platform), FSLY (edge cloud), CRCL (stablecoin/fintech)
- **Why:** Audit flagged the all-semi watchlist as statistically meaningless (effective independent bets ≈ 3.4). New additions diversify across semiconductor equipment, telecom, software, edge infra, and fintech
- **Data verification:** 13/14 tickers confirmed working with yfinance. 6082.HK has limited yfinance coverage (no quarterly income/cashflow) — needs EODHD or manual data
- **Files:** `config/watchlist.json`, `CLAUDE.md`

### 2. Comprehensive Roadmap Created from External Audit
- **Source:** 11-page institutional-quality audit covering 7 ranked weaknesses + 22 prioritized recommendations
- **Key findings accepted:** (1) Universe too narrow/correlated, (2) DCF terminal value is a "Trojan Horse" blending intrinsic + relative, (3) Feedback loop sample size ≈ 1% of what's needed, (4) Schema-drift and JSON repair are load-bearing hacks, (5) Event caps not empirically calibrated
- **25 tasks created:** 2 P0, 5 P1, 10 P2, 8 P3 with dependency chains
- **Files:** Task list updated, `CLAUDE.md` updated with new watchlist

---

## [2026-04-24] Session: EODHD Migration + Buffered Scout Output + System Report

### 1. EODHD Provider Fallback Logic (`scripts/finance_data.py`)
- **What:** Added automatic yfinance fallback in `fetch_financials()` when the primary EODHD provider fails
- **Why:** EODHD API can have transient failures; pipeline should not halt when a fallback data source exists
- **How:** `fetch_financials()` now catches `EarningsFetchError` from the primary provider and retries with `YFinanceProvider()`, appending a FALLBACK warning to the result
- **Impact:** Pipeline resilience — EODHD outages no longer block model generation; fallback is logged in `FinancialData.warnings`
- **Files:** `scripts/finance_data.py` (fetch_financials function)

### 2. Provider Auto-Selection Verified
- **What:** Confirmed `get_provider()` already auto-selects EODHD when `EODHD_API_KEY` is present, falls back to yfinance otherwise
- **Why:** The EODHD migration was already implemented in a prior session; this session verified it and added the fallback safety net
- **How:** Precedence: explicit name → `FINANCE_DATA_PROVIDER` env var → auto-detect (EODHD if key present, else yfinance)
- **Files:** `scripts/finance_data.py` (get_provider function — verified, not changed)

### 3. Buffered Scout Output (`scripts/run_pipeline.py`)
- **What:** Replaced interleaved parallel scout stdout with per-scout `StringIO` buffers, printed as grouped blocks after completion
- **Why:** When 8 scouts run in `ThreadPoolExecutor`, their print statements interleave into unreadable noise
- **Before:** `[OK] quant` mixed with news scout HTTP logs mixed with YouTube transcript lines
- **After:** Clean grouped blocks with box-drawing characters: `┌─── quant [OK] ───` / `│ output lines` / `└────────────`
- **How:** Each scout's `_run_scout()` uses `contextlib.redirect_stdout/stderr` into a `StringIO`. After all futures complete, output is printed scout-by-scout in definition order
- **Files:** `scripts/run_pipeline.py` (_run_scout function, scout execution block)

### 4. Regression Tests
- All 19 `test_engine.py` tests pass after changes

---

## [2026-04-23] Session: Adaptive Routing Implementation — Binary Gates to Continuous Scoring

### 1. Create adaptive_scoring.py — Core continuous scoring module

**Summary:** Built the central module that replaces 68+ binary/stepped thresholds with three continuous function types: parameterized sigmoids (smooth transitions), log-decay curves (size-dependent caps), and sector-relative z-scores (Damodaran-calibrated context). Also includes input-stability EMA tracking for volatile LLM-derived parameters (moat score, TAM, guided growth) with 2-sigma alert detection.

**Files created:**
- `scripts/adaptive_scoring.py` — sigmoid(), z_score(), log_decay_cap(), continuous_routing_score(), continuous_margin_target(), continuous_margin_expansion(), continuous_multiple_cap(), continuous_growth_cap(), projection_score_revenue_growth(), projection_score_forward_pe(), adaptive_scenario_offsets(), has_margin_expansion_story(), InputStabilityTracker class, build_adaptive_context()
- `config/sector_stats.json` — Damodaran-sourced sector statistics (median + stdev) for 7 sectors covering semiconductors, semi-equipment, software, industrials, and default fallback. Metrics: operating margin, EBITDA margin, EBITDA yield, revenue growth, EV/EBITDA, EV/FCF, forward PE, quarterly revenue variance.

**Reasoning:** The recommendations document identified that z-scores should come first (not full per-archetype parameterization) because 6 archetypes x 11 sectors x 3 size bands = 198 contexts with ~9 data points is massively underdetermined. Z-scores auto-calibrate to sector norms with zero tunable parameters per context.

---

### 2. Integrate continuous routing into target_engine.py (Phase 1)

**Summary:** Replaced the stepped EBITDA yield transition zone (0.5%-2.0% linear interpolation) with a continuous sigmoid fed by sector-relative z-scores. Replaced the binary margin expansion guard (guided_op > 15% AND ebitda_target > 20%) with continuous signal detection. Replaced banded margin ramp (>60%/>40%/>15%/>0%), stepped multiple caps (45x/55x/60x/70x), and banded growth caps (rev >500B/150B/30B) with continuous functions.

**Files modified:**
- `scripts/target_engine.py` — Added `_map_sector()` helper. Rewrote `_should_use_revenue_multiple()` Trigger 3 to use `continuous_routing_score()`. Replaced margin expansion detection with `has_margin_expansion_story()` (continuous signal 0.0-1.0, threshold 0.3 vs old binary). Replaced `compute_smart_defaults()` margin bands with `continuous_margin_target()`, growth bands with `continuous_growth_cap()`, multiple caps with `continuous_multiple_cap()`.

**Impact:** AMD target should increase from $332 → ~$500+ (no longer misrouted by missing guided_op_margin). LITE should increase from $629 → ~$1,200+ (margin expansion recognized via continuous signal). AEHR continues to route through cyclical engine correctly. NVDA and APP remain stable.

---

### 3. Integrate continuous sigmoids into target_blend.py (Phase 2)

**Summary:** Replaced stepped projection score contributions (≥40% → +0.30, ≥25% → +0.20, etc.) with continuous sigmoid functions that produce smooth, cliff-free scores.

**Files modified:**
- `scripts/target_blend.py` — Signal 1 (revenue growth): replaced 5-branch if/elif with `projection_score_revenue_growth()`. Signal 2 (forward PE): replaced 4-branch if/elif with `projection_score_forward_pe()`. Signals 3-5 (tags, valuation method, data quality) unchanged.

**Impact:** A 1pp change in revenue growth no longer produces a score jump > 0.05. Old system: 39% → +0.20 but 40% → +0.30 (50% jump). New system: 39% → +0.271 and 40% → +0.278 (2.6% change).

---

### 4. Add archetype-adapted scenario offsets (Phase 4, minimal)

**Summary:** Added `adaptive_scenario_offsets()` that adjusts scenario widths by archetype without requiring earnings surprise data. Cyclicals get wider down-scenarios (0.82x rev vs 0.88x). Compounders get tighter scenarios (0.92x rev vs 0.88x). Transformationals get the widest asymmetry (0.80x down, 1.18x up).

**Files created/modified:**
- `scripts/adaptive_scoring.py` — `adaptive_scenario_offsets()` function with per-archetype override tables.

---

### 5. Wire prediction logging into run_pipeline.py

**Summary:** Added prediction snapshot logging after model generation in the pipeline. Each run now records target prices, valuation method, archetype, and context inputs for all watchlist stocks.

**Files modified:**
- `scripts/run_pipeline.py` — Added prediction logging block after model generation using `log_predictions_batch()`.

---

### 6. Verification Results

- 19/19 regression tests pass (test_engine.py)
- Cliff elimination test: old system had 0→100% P/S weight jump at yield=2.0%, new system transitions smoothly (0.694→0.654)
- All continuous functions produce sensible outputs at edges and boundaries
- Margin expansion detection now catches AMD/LITE cases that the binary guard missed (signal ≥ 0.3 with either guided margin OR high EBITDA target)

---

## [2026-04-23] Session: Prediction Logger — Phase 5 Feedback Calibration Foundation

### Add prediction_logger.py and prediction_log.sql

**Summary:** Created the prediction logging infrastructure required by Phase 5 of the adaptive routing plan. Every pipeline run can now record a full snapshot of its target prices, valuation method, archetype, routing/projection scores, sigmoid parameters, and context inputs to Supabase. A companion `prediction_outcomes` table receives actual price observations from the price-tracker cron, enabling regression-based calibration of sigmoid parameters over time.

**Files created:**
- `scripts/prediction_logger.py` — Three public functions: `log_prediction(ticker, snapshot_data)` for single-stock upserts, `log_predictions_batch(predictions)` for whole-watchlist batch inserts, and `record_price_outcome(ticker, prediction_id, days_elapsed, actual_price)` for the cron tracker. Follows the analyst.py column-stripping retry pattern (up to 5 attempts) for schema-drift resilience. Imports `get_client` from `supabase_helper` and `get_run_id` from `utils`.
- `supabase/prediction_log.sql` — DDL for `prediction_log` and `prediction_outcomes` tables with three performance indexes. Apply via Supabase SQL Editor before first pipeline run.

**Reasoning:** Prediction data is irreplaceable — you cannot retroactively reconstruct what the engine believed on a given run. Logging must start before calibration work begins (Phase 5). The schema captures every variable the feedback loop will need: current price, all three scenario targets, method, archetype, both routing scores, event weight, final blended target, raw sigmoid parameters, and context inputs.

**Impact:** No existing behaviour changed. `log_predictions_batch` should be wired into `run_pipeline.py` after model generation completes.

---

## [2026-04-23] Session: Adaptive Routing Architecture Report

### Adaptive Routing Architecture Report (.docx)

**Summary:** Created a comprehensive internal technical report classifying all 78+ hardcoded thresholds across the engine into hard criteria (10 thresholds that must stay binary) vs. flexible criteria (68+ that should become continuous scoring functions). The report proposes a 3-layer adaptive architecture: continuous sigmoid/log-decay scoring functions, context injection (archetype, sector, scale, moat), and feedback-calibrated parameter tuning.

**Files created:**
- `docs/Adaptive_Routing_Architecture.docx` — Full report with executive summary, cliff-effect case studies (AMD $332, LITE $629, AEHR $9), hard/flexible classification tables, proposed sigmoid/log-decay/z-score replacements for each threshold, context injection design, implementation plan (5 phases), and expected impact matrix.

**Reasoning:** The engine had accumulated 78+ hardcoded cutoffs that produced valuation cliffs — 1pp changes in input metrics could swing targets 30%+. Three confirmed mis-pricings (AMD, LITE, AEHR) were caused by binary gates that didn't account for company-specific context. The report provides a roadmap to replace stepped gates with smooth, context-aware functions.

**Impact:** No code changes — this is a design document. Implementation follows the phased plan in the report (Phase 1: projection score sigmoids, Phase 2: routing, Phase 3: margins/multiples, Phase 4: scenario widths, Phase 5: feedback calibration).

---

## [2026-04-23] Session: Target Price Reliability — Engine Bugs, Analyst Fallback, DB Schema Fix

### 1. Fix Model Generation Not Saving Thesis/Sector/Target Price to DB

**Summary:** `generate_model.py` was generating thesis, sector, kill_condition, and scenario prices via Claude but never writing them to Supabase. Dashboard showed "No analysis data" for stocks that had been analyzed.

**Files modified:**
- `scripts/generate_model.py` — Added `thesis`, `sector`, `kill_condition` to the Claude JSON output schema. Updated `update_stock_in_supabase()` to extract and save these fields plus `target_price` (derived from `scenarios.base.price`).

**Reasoning:** The entire pipeline produced analysis that was discarded at the DB write step. This was the root cause of blank model cards on the dashboard.

---

### 2. Fix Systematically Low Target Prices (3-Bug Cascade)

**Summary:** All watchlist stocks showed unrealistically low target prices (e.g. LITE $629 vs expected $1100+, AEHR $0). Root cause was a cascade of three bugs in the engine pipeline.

**Bug 2A — Missing `_advance_quarter_label` function:**
- `scripts/target_engine.py` — Added the function definition. It was called at line ~2276 but never defined, causing a `NameError` crash for every ticker.

**Bug 2B — Cyclical auto-promotion ignoring archetype:**
- `scripts/target_engine.py` — The engine auto-promoted stocks to cyclical mode when TTM EBITDA ≤ 0, even for non-cyclical archetypes (e.g. AEHR "transformational"). Fixed by gating auto-promotion: only triggers when archetype is `None` or explicitly `"cyclical"`.

**Bug 2C — No analyst fallback when engine produces garbage:**
- `scripts/target_api.py` — Renamed `_load_stock_archetype` → `_load_stock_from_db` to load archetype, model_defaults, valuation_method, and scenarios from Supabase. Added `_analyst_to_driver_overrides()` which converts analyst model_defaults (target margin, target multiple) into engine-compatible driver overrides. Merged these as low-priority defaults that user slider overrides can supersede.
- `app/model/hooks/useEnginePayload.ts` — Added garbage detection: if engine base price < 10% of current price AND analyst base > 3× engine base, falls back to analyst model_defaults for slider values. Returns `usedAnalystFallback` boolean.
- `app/model/TargetPriceModel.tsx` — Destructures `usedAnalystFallback` from hook; shows amber warning badge "Using analyst targets — engine produced unreliable values" when active.

**Reasoning:** Forward drivers from Supabase were silently failing (Python `supabase` package not installed), causing the engine to use raw TTM data. Combined with the missing function crash, every stock fell back to worst-case defaults. The analyst fallback ensures the dashboard always shows a reasonable starting point even when the engine misfires.

---

### 3. Fix Ask AI Route — DB Schema Drift

**Summary:** The `/api/ask/route.ts` referenced a `model_config` column that doesn't exist in Supabase. The DB has separate `scenarios` and `model_defaults` columns.

**Files modified:**
- `app/api/ask/route.ts` — Changed `select("model_config, ...")` → `select("scenarios, ...")`. Fixed scenario key: `scenarios.downside` → `scenarios.bear`. Updated `buildPortfolioSummaryText` and `buildSystemPrompt` to use the correct column names.

**Reasoning:** Schema drift between code and DB caused the ask route to silently return `null` for model data, making the AI agent unable to reference any stock's analysis.

---

---

## [2026-04-23] Session: Ask AI Page, SBC Audit, Pre-Commit Hook, Tests & Health Dashboard

### 0. Ask AI — Portfolio Q&A Agent (Read-only → Full Agent Mode)

**Summary:** Built a dedicated `/ask` page where the user can ask natural-language questions about their portfolio. Initially read-only, then upgraded to full agent mode with 6 tool-use capabilities and an agentic loop (up to 5 tool iterations per question).

**Files created / rewritten:**
- `app/ask/page.tsx` — Chat UI with conversation history, 8 suggested questions, markdown rendering, and **action indicator badges** that show which tools the AI used (expandable with input/result preview). Capability badges in empty state show the agent's abilities.
- `app/api/ask/route.ts` — Agentic API route with Claude tool-use. 6 tools: `run_scout` (any of 9 scouts), `regenerate_model`, `what_if_scenario` (temporary engine run with driver overrides), `search_stocks` (discovery universe + watchlist), `add_to_watchlist` (inserts + triggers mini-pipeline), `get_portfolio_summary`. Agentic loop feeds tool results back to Claude for multi-step reasoning.

**Files modified:**
- `app/dashboard/Dashboard.tsx` — Added "Ask AI" nav link in the header.
- `package.json` — Added `@anthropic-ai/sdk` dependency.

**Agent capabilities:**
1. **Run scouts** — Trigger any of 9 scouts for fresh signals on demand
2. **Regenerate models** — Re-run full model generation pipeline for updated targets
3. **What-if scenarios** — Modify engine drivers (WACC, growth, margins) and compute exact price impact without saving to DB
4. **Search & discover** — Query discovery_candidates and stocks tables by ticker/name/sector/theme
5. **Add to watchlist** — Insert stock + trigger background mini-pipeline (quant → analyst → model)
6. **Portfolio summary** — Refresh full portfolio context mid-conversation

**Frontend action indicators:**
- Color-coded badges per tool (blue=scout, purple=model, amber=what-if, green=search, cyan=add, gray=portfolio)
- Expandable details showing tool input + result preview
- Action count in the token footer
- Loading text updated to "Analyzing — may run scouts or models..."

**Reasoning:** The system generates rich signal data across 10 scouts and builds institutional-grade valuation models, but all of that data was only accessible through individual stock cards. Users need a way to ask cross-cutting questions ("Am I too concentrated?", "What should I buy?") that synthesize the full portfolio view. Agent mode goes further — the AI can now act on answers (run fresh data, test scenarios, add stocks) instead of just reading stale context.

---



### 1. Fix Missing `_annual_label_from_q` Function

**Summary:** Added the missing `_annual_label_from_q()` helper to `target_engine.py`. The function converts quarterly labels (e.g. `"1Q25"`) to 4-digit fiscal year strings (`"2025"`) for the forecast engine.

**Files modified:**
- `scripts/target_engine.py` — Added function definition after `_discount_years_for_horizon()`. Handles `QqYY` format, 4-digit year fallback, and empty input.

**Reasoning:** The function was referenced at line 1959 (`build_target`) and imported by `debug_scenario_inversion.py`, but was never defined — likely lost between sessions. This caused a `NameError` crash when running `verify_model.py` or the full pipeline.

---

### 2. SBC-Proportional Share Dilution (P1)

**Summary:** Fixed the share dilution driver (`share_change_pct`) to scale with actual SBC intensity instead of using a flat 1% for all companies.

**Files modified:**
- `scripts/target_engine.py` — Added SBC-proportional dilution derivation in `compute_smart_defaults()`: `share_change_pct = sbc_pct_rev * 0.4`, clamped to [0.5%, 8%]. Added diagnostic warning when SBC data is unavailable (falls back to defaults).

**Reasoning:** A company with 30% SBC/revenue was getting the same 1% annual dilution as one with 2% SBC/revenue. The FCF-SBC leg of terminal value already deducted SBC from free cash flow, but the share count wasn't reflecting the corresponding dilution. This created a subtle double-counting asymmetry: high-SBC companies had their FCF penalized but their share count left artificially low.

**Before → After:**
- Before: All companies used flat 1% dilution regardless of SBC level
- After: Dilution scales proportionally (e.g., 10% SBC → 4% dilution, 2% SBC → 0.8% dilution). Companies without TTM SBC data get a logged warning.

---

### 2. Pre-Commit Hook (P2)

**Summary:** Wired `verify_model.py` and `test_engine.py` as a git pre-commit hook. Also fixed hardcoded paths in `verify_model.py`.

**Files modified/created:**
- `scripts/verify_model.py` — Replaced hardcoded `/sessions/fervent-charming-johnson/...` paths with `Path(__file__).resolve().parent.parent`. Updated `DEFAULT_TICKERS` to match current watchlist (9 stocks). Removed stale `_SKILL_RECALC` fallback.
- `.git/hooks/pre-commit` — **New file.** Runs regression tests on every commit; runs `verify_model.py` only when engine-related files are staged.

**Reasoning:** Without automated checks, engine changes could silently break parity between Python calculations, Excel exports, and JSON API responses. The pre-commit hook catches these before they reach the repo.

---

### 3. Regression Test Suite (P3)

**Summary:** Built a comprehensive pytest test suite for the target engine with 19 tests covering invariants, ranges, and security.

**Files created:**
- `scripts/test_engine.py` — 9 test classes covering: scenario weight sums, terminal growth cap, negative scenario inversion, WACC constancy across scenarios, driver range validation, share change defaults, SBC defaults, margin invariants in forecasts (using FinancialData stubs), and a security scan for `exec()`/`eval()` in API routes.

**Reasoning:** The engine has accumulated 11+ bug fixes over recent sessions. Without regression tests, any future change risks reintroducing fixed issues (negative scenario inversion, uncapped terminal growth, margin invariant violations, etc.).

---

### 4. System Health Dashboard Panel

**Summary:** Added a "Health" button to the dashboard header that opens a panel showing data provider status, regression test results (live), and last pipeline run health.

**Files created:**
- `app/api/health/route.ts` — API endpoint returning provider key status, live pytest results, and latest pipeline run metrics from Supabase.
- `app/dashboard/HealthPanel.tsx` — Three-column panel: data providers (key status), regression tests (pass/fail with progress bar), pipeline health (last run success, scout success rate, run ID).

**Files modified:**
- `app/dashboard/Dashboard.tsx` ��� Added HealthPanel import, state toggle, header button, and conditional render.

**Reasoning:** The system uses 7 external services (EODHD, yfinance, Alpha Vantage, Perplexity, Claude, Gemini, Supabase) and has a multi-stage pipeline. Without visibility into which providers are configured, whether tests pass, and whether the last pipeline succeeded, debugging failures requires reading raw logs.

---

## [2026-04-23] Session: Pipeline Robustness & Cyclical Dashboard Wiring

### 1. Cyclical Mode Fully Wired into Dashboard

**Summary:** Extended the interactive model UI so that when a stock's archetype is "cyclical," all sliders, deduction chain, sensitivity table, and target price computation switch to the normalized-earnings framework.

**Files modified:**
- `app/model/types.ts` — Extended `ValuationMethod` from `"pe" | "ps"` to `"pe" | "ps" | "cyclical"`; added `net_debt`, `upside_base_pct`, `capitalization`, `ebitda` to EnginePayload
- `app/model/helpers.ts` — Added `computeTargetPriceCyclical()`, `cyclicalMethodInfo()`, cyclical branch in `buildSensitivityMatrix()`
- `app/model/TargetPriceModel.tsx` — Split valuation detection into `baseValMethodInfo` (pre-hook) and `valMethodInfo` (post-hook) to fix forward-reference bug; added cyclical sliders (Normalized EBIT margin, Through-cycle EV/EBIT 4-40×), cycle position indicator, net debt display
- `app/model/components/DeductionChain.tsx` — Added cyclical chain: Revenue → ×EBIT margin → Normalized EBIT → ×EV/EBIT → EV → −Net debt → Equity → Price/share
- `app/model/components/SensitivityTable.tsx` — Cyclical mode shows EBIT margins as rows instead of revenues; subtitle updated
- `app/model/hooks/useEnginePayload.ts` — Added cyclical branch reading `ebit_margin_normalized` and `ev_ebit_multiple` from engine drivers

**Reasoning:** The archetype system classified stocks into cyclical mode but the dashboard had no way to display it. All valuation UI was locked to P/E or P/S. Cyclical companies need normalized-earnings inputs (EBIT margin × EV/EBIT) to avoid extrapolating peak-cycle margins.

---

### 2. Model Generation Pipeline Robustness Overhaul

**Summary:** Fixed 5 execution-level bugs in `generate_model.py` that caused truncation, JSON parse failures, and Supabase save errors during pipeline runs.

**Files modified:**
- `scripts/generate_model.py` — All changes below

**Changes:**
1. **Prompt redundancy removed** — `analyst_prompt.md` (123 lines) was being injected into the prompt which already contained the same rules. Removed the `{guideline}` injection, saving ~2,000+ input tokens.
2. **Output size discipline added** — New `OUTPUT SIZE RULES` section: max 3 sentences for target_notes, 2 for criteria detail, no extra fields (sensitivity_table, time_path, etc.). Prevents Claude from generating bloated responses.
3. **max_tokens bumped 16K → 32K** — Safety net for complex stocks.
4. **4-layer JSON repair chain** — (a) Clean parse → (b) Brace extraction → (c) Regex repair (trailing commas, unescaped newlines) → (d) Truncation repair (`repair_truncated_json`: counts open/close braces, strips last incomplete value, closes structure) → (e) Auto-retry with compact prompt (halved research, Sonnet instead of Opus, "MAXIMALLY CONCISE" override).
5. **Variable initialization bug fixed** — `content` and `stop_reason` were referenced in error handlers before assignment if the API call failed. Now initialized to `""` and `"unknown"` before the try block.
6. **Supabase column-stripping loop** — Previously only handled one missing column, then crashed. Now loops up to 5 times, stripping each missing column and retrying.
7. **Research text trimmed** — Input research capped at 6,000 chars (was 8,000) since guideline removal freed headroom. Retry uses 3,000.

**Before → After:**
- Before: LITE and SNDK failed every run due to truncation at 16K tokens; one missing Supabase column crashed the save
- After: LITE generates cleanly on first attempt; truncation triggers repair → retry → compact retry; Supabase saves degrade gracefully

---

### 3. YouTube Scout Performance Optimization

**Summary:** Reduced YouTube scout processing time by ~60% through shorter transcripts, faster retries, and reduced inter-stock delays.

**Files modified:**
- `scripts/scout_youtube.py` — 4 parameter changes

**Changes:**
1. Transcript per video: 5,000 → 2,000 chars (Gemini only needs first ~2 min for sentiment/thesis)
2. Gemini call timeout: 45s → 30s
3. Retry sleep: 15s → 5s
4. Inter-stock sleep: 5s → 2s

**Before → After:**
- Before: Worst case ~4.5 min/stock, happy path ~50s/stock, 9 stocks = 12+ min
- After: Worst case ~2 min/stock, happy path ~32s/stock, 9 stocks = ~5 min

---

### 4. CLAUDE.md Handoff Document

**Summary:** Created comprehensive AI handoff document at project root so new sessions can immediately understand the full system.

**Files created:**
- `CLAUDE.md` — Covers architecture, directory structure, how to run everything, valuation methods (including cyclical), all known gotchas (Supabase drift, MU data bug, truncation handling), key design decisions, and session startup checklist.

---

## [2026-04-23] Session: Architecture Upgrade & Micro-Cap Fixes

### 1. Archetype Classification in Model Generation Prompt (P1)

**Summary:** Added STEP 0: ARCHETYPE CLASSIFICATION to the LLM prompt so every stock gets classified into one of six investment archetypes before valuation.

**Files modified:**
- `scripts/generate_model.py` — Added archetype classification block (lines 296–336) to `MODEL_GEN_PROMPT`

**Reasoning:** The valuation framework needs to know *what kind* of company it's dealing with before choosing a method. A cyclical semiconductor (MU) requires normalized-earnings valuation, while a pre-profit SaaS (SNOW) needs revenue multiples. Without archetype classification, every stock was forced through the same EV/EBITDA pipeline regardless of business type.

**Before → After:**
- Before: All stocks valued with generic EV/EBITDA; cyclicals at trough and pre-profit companies produced nonsensical targets
- After: Each stock is classified as GARP, Cyclical, Compounder, Transformational, Special Situation, or Deep Value, and the correct valuation engine is selected automatically

---

### 2. Frontend Time-Path Convexity Fix (P2)

**Summary:** Replaced linear multiple compression in the time-path chart with Gordon Growth Model-based convex decay.

**Files modified:**
- `app/model/helpers.ts` — Added `gordonPE()` function; rewrote `buildTimePath()` to use convex compression at each quarterly step

**Reasoning:** Linear interpolation of P/E compression from current to terminal produces straight-line price paths that misrepresent how multiples actually decay. In reality, as terminal growth approaches the required return, the P/E ratio compresses non-linearly (convexly) per the Gordon Growth Model: P/E = 1/(r − g). The visual difference matters for investor decision-making — a linear path suggests constant decay, while convex compression shows most of the de-rating happens early.

**Before → After:**
- Before: Time-path chart showed a straight line from current price to target
- After: Chart shows a convex curve reflecting realistic multiple compression dynamics

---

### 3. Observability Layer (P3)

**Summary:** Built a thread-safe pipeline metrics collector that tracks scout runs, model generation, and data source calls.

**Files modified:**
- `scripts/observability.py` — **New file.** Contains `ScoutMetrics`, `ModelGenMetrics`, `DataSourceMetrics` dataclasses and the `PipelineMetrics` collector class
- `scripts/run_pipeline.py` — Wired observability into the pipeline loop; each scout run records timing, success/failure, signal count
- `scripts/generate_model.py` — Added `_gen_meta` tracking for tokens_used, repair_attempts, repair_method

**Reasoning:** The pipeline runs 9 scouts in parallel across 9 stocks (81 concurrent operations) with no visibility into what's slow, what's failing, or how much API spend each run costs. The observability layer collects structured metrics in-memory during the run and outputs both a formatted terminal summary and a dict suitable for the `pipeline_runs.scout_details` JSONB column in Supabase.

**Before → After:**
- Before: Pipeline failures were silent; debugging required reading raw logs
- After: Every run produces a structured summary table showing per-scout duration, success rate, signal counts, and per-model token usage / repair attempts. Data is stored in Supabase for historical analysis.

---

### 4. Research Manager — Archetype-Aware Scout Routing (P4)

**Summary:** Built a rule-based research orchestration layer that selects which scouts to run based on stock archetype and urgency mode.

**Files modified:**
- `scripts/research_manager.py` — **New file.** Contains `SCOUT_PRIORITY` matrix, `select_scouts()`, `detect_conflicts()`, `check_sufficiency()`, and `plan_research()` functions
- `scripts/run_pipeline.py` — Integrated research manager; changed default from "full" (all scouts) to "smart" (archetype-aware); added `--smart`, `--fast`, `--full` CLI flags

**Reasoning:** Running all 9 scouts for every stock wastes API calls and time. A GARP stock doesn't need the YouTube scout; a compounder doesn't need the catalyst scout. The research manager uses a priority matrix (always/recommended/optional per archetype) to intelligently select scouts. Three modes: `full` (all scouts), `smart` (always + recommended, default), `fast` (always-tier only, minimum viable signal set).

**Before → After:**
- Before: Every stock ran all 9 scouts regardless of type (81 scout calls per run)
- After: Smart mode runs ~6–7 scouts per stock based on archetype. A 9-stock run with mixed archetypes saves ~20–30% of API calls. Conflict detection flags when scout signals may contradict (e.g., strong moat + heavy insider selling). Sufficiency checking warns when critical scouts for an archetype failed.

---

### 5. Default Pipeline Mode Changed to Smart

**Summary:** Changed the default pipeline behavior from running all scouts to archetype-aware smart routing.

**Files modified:**
- `scripts/run_pipeline.py` — Default is now `smart` mode; use `--full` to force all scouts

**Reasoning:** The user pointed out: "Shouldn't the default pipeline be as smart as possible?" Correct — the smart default saves API costs and time while maintaining signal quality for each archetype.

**Before → After:**
- Before: `python scripts/run_pipeline.py` ran all 9 scouts for every stock
- After: `python scripts/run_pipeline.py` uses smart routing (default); `--full` overrides to all scouts; `--fast` uses minimum scout set

---

### 6. Micro-Cap Sanity Check Size Gate

**Summary:** Made revenue-spike detection thresholds size-aware to prevent false positives on micro-cap stocks like AEHR.

**Files modified:**
- `scripts/finance_data.py` — Rewrote `_validate_quarterly_revenue()` with tiered thresholds based on quarterly revenue scale

**Reasoning:** The sanity check was built to catch data-provider errors on large-caps (the MU bug: yfinance returning $23.86B instead of $8.7B). It used flat 2.0x trailing and 2.5x YoY thresholds. On a micro-cap like AEHR doing $5M–$15M quarters, normal order lumpiness in semi-equipment business routinely produces 3–5x quarter-over-quarter swings. The flat thresholds flagged legitimate revenue as "SUSPECT DATA."

**Before → After:**
- Before: All stocks used 2.0x trailing / 2.5x YoY thresholds → AEHR produced multiple false positive warnings
- After: Large-cap (≥$500M/Q): 2.0x / 2.5x (unchanged). Mid-cap ($100M–$500M): 3.0x / 4.0x. Micro-cap (<$100M): 5.0x / 6.0x. AEHR's legitimate revenue swings no longer trigger false alarms.

---

### 7. Cyclical-at-Trough Routing Fix ($9 Target Bug)

**Summary:** Prevented cyclical companies at the bottom of their revenue cycle from being misrouted to the P/S (revenue-multiple) valuation framework, which produced absurdly low targets.

**Files modified:**
- `scripts/target_engine.py` — Added `_has_cyclical_history()` function; added `archetype` parameter to `_should_use_revenue_multiple()`; added cyclical-at-trough auto-promotion logic in `build_target()`

**Reasoning:** AEHR is a cyclical semi-equipment company in a revenue trough ($45M TTM rev, negative TTM EBITDA). The routing logic saw TTM EBITDA ≤ 0 and classified it as "structurally pre-profit" (like early SNOW or PLTR), sending it to the P/S framework. P/S mode then applied conservative terminal P/S multiples to trough-level revenue, producing a $9 target on a stock trading at $91. The market wasn't wrong — it was pricing cyclical recovery. The correct framework is the cyclical normalized-earnings engine, which uses historical mid-cycle EBIT margins.

The fix has two layers:
1. `_has_cyclical_history()` checks if ≥3 of the last 10 annual periods had operating margins above 5%. If so, current losses are cyclical, not structural.
2. When the routing guard rejects P/S for a cyclical-at-trough company, `build_target()` auto-promotes to the cyclical engine — even without an explicit "cyclical" archetype tag.

**Before → After:**
- Before: AEHR → TTM EBITDA ≤ 0 → P/S mode → conservative terminal P/S × trough revenue → $9 target (vs $91 market price)
- After: AEHR → TTM EBITDA ≤ 0 → cyclical history detected → auto-promote to cyclical normalized-earnings engine → target based on mid-cycle EBIT margins and through-cycle EV/EBIT multiple → target aligned with recovery thesis

---

*This changelog is maintained manually. Each session appends new entries at the top.*
