# Stock Radar — System Status & Roadmap Report

**Prepared:** 2026-06-01
**Owner:** Hume (asyanurpekel@gmail.com)
**Scope:** Full-system snapshot — current state, health, and the to-be-built backlog
**Basis:** Live code, `CHANGELOG.md` (3,162 lines), `data/todo_master_2026_05_26.md`, design docs, and a green engine regression run (37/37) performed for this report.

---

## 1. Executive Summary

Stock Radar is a production investment-research platform that runs an AI agent system to find and track 10x stock opportunities. Ten independent "scout" modules gather signals, an analyst layer aggregates them, an institutional-grade DCF engine produces probability-weighted price targets, and a Next.js dashboard surfaces conviction-ranked stocks. Over the most recent development arc (late April → late May 2026) the system grew a second brain on top of the original pipeline: a **Socratic reasoning layer** (Models A/B/C plus a "corpus callosum" reconciler) and a **macro + wave-health layer**, both now live end-to-end.

The system is operational and the daily pipeline runs. The single largest piece of architectural debt — DCF structurally undershooting regime-shift names — was closed on 2026-05-26 (the "C1 + D-v1" change). What remains is a well-documented, trigger-tagged backlog: kill-rule routing, an EDGAR-based data guardrail rewrite, a macro cron orchestrator, the frontend migration to the v2 production wireframe, and several reasoning-layer refinements that are intentionally parked until real outcome data arrives (the first, AXON's T+30, lands ~2026-06-08).

A recurring theme in the codebase is discipline: changes ship behind baselines, follow a canonical 7-step workflow, and are deferred unless a falsifiable trigger fires. That philosophy is the main reason the backlog reads as "deliberately waiting" rather than "unfinished."

---

## 2. Current State

### 2.1 Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind, Three.js (discovery globe) |
| Backend | Python 3, ~70 scripts |
| Database | Supabase (PostgreSQL) |
| Research / reasoning | Claude (analysis, models, Socratic), Perplexity Sonar (forward research) |
| Data | EODHD (primary financials), Alpha Vantage (fallback), yfinance, SEC EDGAR XBRL |
| Media | Gemini (YouTube transcript analysis) |

### 2.2 Watchlist (6 stocks)

The active list in `config/watchlist.json` is **LITE, PLTR, RKLB, ACHR, CELH, SNDK**. Each carries a thesis, a kill condition, MECE criteria, and scenario probabilities. (Note: `CLAUDE.md` still says "9-stock watchlist" in places — see §5, stale docs.)

### 2.3 Frontend surface

The `app/` directory exposes these routes: `dashboard/` (scores, signals, scout panels), `model/` (interactive target-price builder), `discovery/` (3-stage universe-expansion funnel), `ask/` (conversational Q&A), `stock/[ticker]/` (per-ticker detail), and `logs/` (pipeline activity viewer). There are 17 API route groups under `app/api/` (stocks, pipeline, model, scout, health, convergence, discovery, feedback, fx, locations, logs, rebuild, scenarios, search, thesis, ask). The model builder is component-rich: DeductionChain, SensitivityTable, GordonModel, ScenarioSection, EventImpactsPanel, ConfidenceMeter, TimePathChart, and slider/criteria components, backed by `useEnginePayload` / `usePipeline` / `useCurrency` hooks.

### 2.4 Backend modules (grouped)

- **Pipeline orchestration:** `run_pipeline.py`, `research_manager.py`, `rebuild_analysis.py`, `ingest_scout_jsons.py`
- **10 scouts:** `scout_quant`, `scout_news`, `scout_catalyst`, `scout_moat`, `scout_social`, `scout_insider`, `scout_filings`, `scout_fundamentals`, `scout_youtube`, `scout_discovery`
- **Valuation / target engine:** `target_engine.py` (DCF), `target_blend.py`, `target_api.py`, `generate_model.py`, `model_export.py`, `forward_drivers.py`, `verify_model.py`
- **Analyst / scoring:** `analyst.py`, `adaptive_scoring.py`, `confidence.py`, `research_memo.py`
- **Reasoning / judgment:** `run_socratic.py` (Models A/B/C + corpus callosum), `run_thesis.py`, `run_judgment.py`, `event_reasoner.py`, `event_templates.py`, `kill_condition_eval.py`, `self_consistency.py`, `convergence_detector.py`
- **Discovery / universe:** `discovery_scan`, `discovery_ingest`, `discovery_13f`, `discovery_bootstrap`, `discovery_calibrate`, plus `feed_*_to_universe`
- **Calibration / feedback / backtest:** `calibration.py`, `feedback_loop.py`, `backtest.py`, `backtest_targets.py`, `drift_monitor.py`, `prediction_logger.py`, `experiment_tracker.py`
- **Data / finance:** `finance_data.py`, `edgar_xbrl.py`, `refresh_prices.py`, `regime_detection.py`, `factor_exposure.py`, `position_sizing.py`, `paper_trade.py`
- **Infra / utils:** `utils.py`, `supabase_helper.py`, `registries.py`, `observability.py`, `activity_logger.py`

### 2.5 Valuation system

Three valuation methods (`pe`, `ps`, `cyclical`/EV-EBIT) and a five-archetype classification system (GARP, Cyclical, Transformational, Compounder, Special Situation) determine the analytical framework per stock. The target engine is an institutional-grade forward DCF with a constant WACC across scenarios, a 2.5% terminal-growth cap, and event-adjusted blend targets treated as authoritative. As of 2026-05-26, DCF is routed by archetype: for regime-shift names it acts as a **downside floor** while exit multiples drive the primary target.

### 2.6 Health check

- **Engine regression tests:** `test_engine.py` → **37 passed, 0 failed** (run 2026-06-01, no network needed). Covers forecasting, terminal value, bottom-up WACC, sector betas, and margin ramp.
- **Parity / fixtures:** `verify_model.py` (engine ↔ Excel ↔ JSON parity) plus `test_engine_fixtures.py`; a pre-commit hook runs the engine tests on every commit and parity checks when engine files are staged.
- **Pipeline:** daily run operational; full run with the watchlist takes ~10–15 min (YouTube scout slowest).
- **Git:** baseline tag `v3.5-foundation` captured; recent commits cover the DCF reposition, Socratic milestone, and frontend overhaul. Working tree clean at time of report.

---

## 3. Architecture (data flow)

```
                          EXTERNAL APIS
   Claude · Perplexity · Gemini · EODHD · AlphaVantage · EDGAR · Supabase
                                │
 ┌──────────── SCOUT LAYER (10 independent signal gatherers) ───────────┐
 │ quant · news · catalyst · moat · social · insider · filings ·        │
 │ fundamentals · youtube · discovery                                   │
 └──────────────────────────────┬───────────────────────────────────────┘
                                 ▼  (signals → Supabase)
                        ANALYST / SCORING LAYER
                 analyst.py · adaptive_scoring · confidence
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                         ▼
  TARGET ENGINE          REASONING / JUDGMENT        MACRO + WAVE HEALTH
  (DCF + blend +         Socratic A/B/C + corpus      regime + wave overlay
  event reasoner +       callosum · thesis ·          → [MACRO]/[WAVE]
  forward drivers)       kill conditions ·            context blocks
        │                self-consistency ·                 │
        │                convergence                        │
        └────────────────────────┼────────────────────────┘
                                 ▼
                         DASHBOARD (Next.js)
        dashboard · model builder · discovery · ask · logs · stock/[t]
                                 │
                CALIBRATION / FEEDBACK / BACKTEST (closes the loop)
        feedback_loop · calibration · drift_monitor · backtest · prediction_logger
```

---

## 4. Recent Milestone Timeline (Apr → May 2026)

| Date | Milestone |
|---|---|
| 2026-04-24 | Institutional DCF overhaul, EODHD migration, structured outputs, resilience layer |
| 2026-04-25/26 | Pipeline reliability/efficiency fixes; confidence propagation + feedback calibration |
| 2026-05-03 | CI cost-runaway fix (`--no-thesis`); thesis-as-headline / DCF-as-floor framing |
| 2026-05-05→08 | Outcome tracker (T+30/90/180); hard-fail on suspect quarters; adversarial filter v3; convergence detector |
| 2026-05-09 | Shared NavBar, discovery panels, per-ticker data-provider override; AXON first end-to-end tracked signal (5% position) |
| 2026-05-10/11 | V3.4.3 kill rule; archetype override (LITE + AMD tagged transformational) |
| 2026-05-15 | Socratic orchestrator (Models A/B/C + corpus callosum); judgment card + bets table |
| 2026-05-17→23 | Macro + wave-health layer: design locked → data layer shipped → **live end-to-end** |
| 2026-05-24/25 | Operator notes as Socratic context; Model B anti-sycophancy + future-pricing analysis |
| 2026-05-26 | **C1 + D-v1: DCF role contextual routing + archetype override loader** — closed 25-day DCF debt |

---

## 5. Known Issues & Gotchas

**Supabase schema drift.** `supabase/migration.sql` does not always match the live DB. The pipeline strips unknown columns and retries (up to 5). Missing columns are added manually via the SQL editor; this remains a manual, error-prone seam.

**Financial data source reliability.** `finance_data.py` has a multi-source `DataProvider` abstraction (EODHD primary, Alpha Vantage fallback, yfinance) with cross-validation, but EODHD is not yet the default for every ticker. Note: the earlier "MU $23.86B revenue bug" was reclassified by a corrigendum (`docs/reports/2026-05-09_mu_thesis_contamination/CORRIGENDUM.md`) as *real* Q2 FY26 revenue, not a contamination — the memory-anchoring lesson stands, the data-bug premise did not.

**"System learns" is currently aspirational.** `feedback_loop.py` requires `MIN_SIGNALS_FOR_ADJUSTMENT = 10` settled outcomes before adjusting scout weights. With AXON as the first tracked signal (T+30 ~2026-06-08), fewer than ~5 outcomes likely exist, so the feedback loop is effectively prior-only today. This is a status fact, not a bug (tracked as E2).

**Macro layer has no orchestrator.** The macro + wave-health layer is live in the reasoning path, but `macro_environment` still has a single, manually-seeded row — `scripts/run_macro.py` (the daily macro cron) is not built.

**Calibration blocked on data.** Module 9 calibration loop is blocked until ≥20 `thesis_outcomes` rows have T+30 filled (fallback trigger 2026-10-01).

**Stale documentation.** `CLAUDE.md` references a "9-stock watchlist" and "19 engine tests"; the live system has **6 stocks** and **37 passing tests**. `CLAUDE.md` should be refreshed.

**`whatif-engine.ts` fidelity gap.** The TypeScript what-if engine uses a blend-of-multiples rather than the Python engine's Gordon+ROIIC primary path (hardcoded `blend: 0.5`); the "Engine base" card label needs correcting.

---

## 6. What Is To Be Built (Backlog)

The authoritative backlog lives in `data/todo_master_2026_05_26.md`, organized by tier with explicit re-entry triggers. Summary below.

### 6.1 Tier 1 — done
**C1 DCF role contextual routing + D-v1 archetype override loader — CLOSED 2026-05-26.** LITE auto-target band now $508 / $1,127 / $1,501. Settled the 25-day `user_dcf_is_wrong_primary` debt.

### 6.2 Tier 2 — build next (unblocked by C1)

| ID | Item | Notes |
|---|---|---|
| V2 | Config-routed `dcf_role` per archetype | Add `dcf_role` to `ticker_archetype_overrides.json`; precursor wiring so `analyst.py` passes `dcf_role` into `build_target`. Currently flag-gated via `--dcf-as-floor` only. |
| D1 | Kill-rule contextual routing | Route V3.4.3 kill rule by archetype: cyclicals < 0.90, regime-shift < 0.60, pre-revenue disabled. Depends on V2 wiring. |
| D-v2 | Archetype auto-promote audit | Make the `target_engine.py:2983` cyclicality heuristic regime-aware (recency-weight CV, or suppress when explicit override exists). Third instance of the "historical-math vs regime-shift" bug pattern. |
| D2 | Module 1 EDGAR rewrite | Split data guardrail: EDGAR cross-check = hard gate; trajectory-smoothness = informational only. Goal: ASTS-style 50x QoQ launch passes without an override flag. Uses existing `edgar_xbrl.py`. |
| D3 | Analysis routing by timing × held status | Route by `timing_category` (收获期/半步领先/远见期) × held; needs schema migration + seeds (see F7). |
| D4 | §10b tactical signals layer | Tactical (days/weeks) signals that never override thesis; options-flow scout + catalyst×options confluence. Trigger now met (ASTS gamma squeeze). |
| D5 | §7c expectations decomposition + fast-sell | Auto-extract implied expectations from Model B future-pricing into `socratic_analyses.implied_expectations` + kill-trigger notifications. Trigger met (3 structured chokepoints). Own 7-step cycle. |

### 6.3 Tier 3 — investigate before committing

- **E1** Non-US discovery archetype bypass (`MIN_QUARTERLY_ROWS_NON_US = 4` → 2 for early-revenue ramps).
- **E2** Signal-store census — confirm/document that the feedback loop is prior-only today.
- **E3** Insider-selling deviation framing ("397 sells vs 5yr-avg 20 = 20x normal") — identify source scout first.

### 6.4 Deferred — parked until a trigger fires

| ID | Item | Re-entry trigger |
|---|---|---|
| F1 | Model D (optionality / TAM frame) | Macro on ASTS + Models A/B/C fail to handle optionality |
| F2 | Lateral-trace discovery | A TSEM-like miss the engine didn't catch |
| F3 | Revolution impact spectrum (ai_helps/ai_threatens) | Calibration plan complete (blind-score 10 stocks first) |
| F4 | 灵感 / Spark conversation mode | ≥5 inadequate ad-hoc chat cases |
| F5 | 影响图谱 impact-graph frontend | F3 backend shipped + seeded |
| F6 | Position sizing by signal maturity (5→10→15-20%) | AXON T+30 lands (~2026-06-08) |
| F7 | Timing categorization schema + seeds | Needed before D3 |
| F8 | COHR threat notification on LITE | Notifications infra exists (needs check) |
| F9 | Adversarial filter prepass v3 re-wire | ≥20 closed outcomes (currently 0–1) |

### 6.5 Frontend backlog

- **Migration to v2 production wireframe** (`docs/wireframes/migration-plan-v1.md`): a 9-phase port of the warm-neutral `sr-` token system into the codebase, fixing DriftChip semantic labels, Hume-Notes monospace, the 8-tab model strip, and an orphan `conv-fade` token. Mostly planned; only artifact-save (Phase 0) clearly done.
- **Phase 7 frontend** (from the macro design): macro (宏观) tab, tech-revolution graph view replacing the linear wave bar, judgment-card Option C UX, and Spark mode in the Ask tab.
- **Model sandbox Phase 2/3:** read-only Excel grid replacing IncomeTab/CashTab (P2); AI-generated scenarios + editable cells + coherence validator (P3).

### 6.6 Infrastructure

- Move `data/.thesis-running-{TICKER}` lockfile to Supabase (cross-environment safety).
- Hard cost cap on Opus calls (fail if > N in 24h) — complements the existing `--no-thesis` cron guard.
- `run_macro.py` daily macro orchestrator (see §5).

### 6.7 Open questions — need a Hume decision (not code)

- **G1** Are max-30%-single-name / max-leverage hard gates (Category 1) or contextual routing (Category 2)? Decide when implementing F6.
- **G2** Is the "<10 hard gates" budget arbitrary? Decide at next quarterly audit (~2026-08-26).
- **G3** LITE position management at ~$947 (cost basis $70): trim / hold / split. Engine surfaces the math; the sizing call is Hume's. Time-sensitive.
- **G4** AXON T+30 outcome (~2026-06-08): first calibration data point; informs F6 timing.
- **G5** COHR decision after id=25 NO_REGIME_SHIFT: monitor for $240–$290 entry zone.

---

## 7. Near-Term Priority Sequence

Per the action sequence in `todo_master`:

1. **Now:** commit/push the session work + CHANGELOG entry (largely done).
2. **Week 2:** D2 (EDGAR rewrite) and D1 (kill-rule routing, after V2 wiring) — can run in parallel after C1.
3. **Parallel/ad-hoc:** E1–E3 quick data checks.
4. **Week 3+:** D3 → D4 → D5 in order of conviction.
5. **Watch 2026-06-08:** AXON T+30 → triggers the F6 position-sizing decision (G4).
6. **Quarterly (~2026-08-26):** re-run the filter audit; fold in the G2 decision.

---

## 8. Operating Principles (constraints on every change)

The codebase enforces a disciplined change philosophy worth preserving: one-step falsifiable changes (bundling causes contradictions); a complexity ratchet caution (a prior 17-fix episode *doubled* LITE's error — stay skeptical of magic numbers); the Hard-Gate / Contextual-Routing / Informational filter taxonomy for any new filter; a canonical 7-step workflow for non-trivial changes (light loop for surgical edits); milestone-level commit cadence with per-change CHANGELOG entries; and baseline-before-change discipline (the `v3.5-foundation` tag and basket snapshots exist precisely so downstream changes have unambiguous before/after evidence).

---

## 9. Bottom Line

The system is **healthy and operational**: scouts → analyst → engine → dashboard runs daily, the engine regression suite is green, and the two most ambitious recent additions (Socratic reasoning + macro/wave health) are live. The biggest structural bug (DCF undershoot on regime-shift names) is closed. The remaining work is mostly (a) **propagating** the DCF/archetype routing through the kill rule and the auto-promote heuristic, (b) **hardening data integrity** via an EDGAR-based guardrail, (c) **finishing the macro layer** with a cron orchestrator, and (d) **executing the frontend migration** to the production wireframe. Several reasoning refinements are deliberately parked until the first real outcome data (AXON T+30, ~2026-06-08) tells the system whether its recommendations are calibrated. The most time-sensitive item is not code at all — it is the LITE position decision at ~$947 (G3).

---

*Sources: `CLAUDE.md`, `CHANGELOG.md`, `data/todo_master_2026_05_26.md`, `config/watchlist.json`, `docs/design/MACRO_AND_WAVE_HEALTH_v1.md`, `docs/wireframes/migration-plan-v1.md`, `docs/reports/2026-05-*`, and live `scripts/` (engine tests run 2026-06-01: 37 passed).*
