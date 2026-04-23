# Stock Radar — Change Log

All notable changes made to the project are documented here, with reasoning and impact.

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
