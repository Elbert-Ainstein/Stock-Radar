# Stock Radar — Change Log

All notable changes made to the project are documented here, with reasoning and impact.

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
