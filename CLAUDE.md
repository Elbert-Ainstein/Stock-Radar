# Stock Radar — AI Handoff Document

**Owner:** Hume (asyanurpekel@gmail.com)
**Last updated:** 2026-04-23
**Status:** Production system, daily pipeline operational, 9-stock watchlist active

---

## What This Is

Stock Radar is a full-stack investment research platform that uses an AI agent system to find and track 10x stock opportunities. It combines 10 independent "scout" modules (each gathering different signal types) with an analyst aggregation layer, an institutional-grade DCF valuation engine, and an interactive Next.js dashboard.

**Goal:** Automated daily pipeline that gathers signals, generates targets, evaluates kill conditions, and surfaces conviction-ranked stocks with probability-weighted price targets.

---

## Architecture Overview

```
YouTube ──┐
News ─────┤
Catalyst ─┤
Moat ─────┤                                    ┌── Dashboard (Next.js)
Quant ────┼── Scout Signals ──→ Analyst ──→ Target Engine ──→ Model UI
Social ───┤                                    │
Insider ──┤                                    ├── Event Reasoner
Filings ──┤                                    │
Fundmtls ─┘                                    └── Kill Condition Eval
```

**Data flow:** Scouts → Supabase → Analyst → Target Engine → Dashboard
**Frontend:** Next.js 16 + React 19 + Tailwind + Three.js (discovery globe)
**Backend:** Python 3 scripts, Supabase PostgreSQL
**APIs:** Perplexity (research), Claude (analysis/models), Gemini (YouTube), EODHD/yfinance (financials)

---

## Directory Structure

```
stock-radar/
├── app/                    # Next.js frontend
│   ├── dashboard/          # Main dashboard (scores, signals, scout panels)
│   ├── model/              # Interactive target price model builder
│   │   ├── components/     # DeductionChain, SensitivityTable, SliderRow, etc.
│   │   ├── hooks/          # useEnginePayload, usePipeline
│   │   ├── helpers.ts      # Valuation math (PE, PS, cyclical)
│   │   └── types.ts        # ValuationMethod, EnginePayload, StockData, etc.
│   ├── discovery/          # Universe expansion scanner (3-stage funnel)
│   └── api/                # Next.js API routes (stocks, pipeline, model, scout)
├── scripts/                # Python backend
│   ├── run_pipeline.py     # Master pipeline (runs all scouts → analyst → models)
│   ├── analyst.py          # Signal aggregation & composite scoring
│   ├── generate_model.py   # Target price model generator (Perplexity + Claude)
│   ├── target_engine.py    # Institutional-grade DCF engine
│   ├── target_blend.py     # Blends DCF targets with analyst targets
│   ├── finance_data.py     # Financial data fetcher (DataProvider ABC, multi-source)
│   ├── forward_drivers.py  # Forward-looking driver extraction from scout signals
│   ├── event_reasoner.py   # Event → probability-adjusted price impact
│   ├── kill_condition_eval.py  # Thesis-break evaluation via Claude
│   ├── feedback_loop.py    # Scout accuracy tracking & weight adjustment
│   ├── scout_*.py          # 10 scout modules (quant, news, catalyst, moat, etc.)
│   ├── utils.py            # Shared utilities (env, watchlist, timestamps)
│   └── supabase_helper.py  # Supabase DB interaction layer
├── config/
│   ├── analyst_prompt.md   # Guideline for model generation (valuation framework)
│   ├── watchlist.json      # Tracked stocks with theses, targets, criteria
│   └── youtube_channels.json
├── data/                   # Pipeline output artifacts (analysis.json, signals, etc.)
├── supabase/               # SQL migrations (NOT always applied to live DB!)
├── docs/                   # ROADMAP.md, architecture docs, handoff notes
└── lib/                    # Shared TypeScript (data types, Supabase client)
```

---

## Running the System

### Full Daily Pipeline
```bash
cd stock-radar/scripts
python run_pipeline.py          # All scouts + analyst + feedback + model generation
python run_pipeline.py --free   # Free scouts only (no API keys needed)
python run_pipeline.py --ticker MRVL  # Single-stock mini-pipeline
```

### Model Generation Only (skip scouts)
```bash
python generate_model.py --all              # Regenerate all models
python generate_model.py --ticker LITE      # Single ticker
python generate_model.py --all --parallel 3 # Control parallelism (default: 3)
```

### Dashboard
```bash
cd stock-radar
npm run dev   # http://localhost:3000
```

### Required API Keys (.env)
```
ANTHROPIC_API_KEY=    # Claude — model generation, analysis, kill conditions
PERPLEXITY_API_KEY=   # Perplexity Sonar — forward research, news, catalysts
GEMINI_API_KEY=       # Gemini — YouTube transcript analysis
SUPABASE_URL=         # Supabase project URL
SUPABASE_KEY=         # Supabase anon/service key
EODHD_API_KEY=        # EODHD — financial data (primary provider)
ALPHA_VANTAGE_API_KEY=  # Alpha Vantage — fallback financial data
```

---

## Current Watchlist (9 stocks)

MRVL, SNDK, MU, LITE, APP, AEHR, TER, NVDA, AMD

---

## Valuation System

### Three Methods
- **P/E** — For profitable companies with stable earnings (default for most)
- **P/S** — For high-growth pre-profit or negative-earnings companies
- **Cyclical (EV/EBIT)** — For companies driven by industry cycles (Damodaran normalized-earnings approach)

### Archetype System (5 types)
Each stock is classified into a primary investment archetype that determines the analytical framework:

| Archetype | Framework | Key Question | Example |
|-----------|-----------|--------------|---------|
| **GARP** | Growth at Reasonable Price (Lynch) | Is growth fairly priced? | MRVL |
| **Cyclical** | Normalized Earnings (Damodaran) | Where in the cycle? | MU |
| **Transformational** | Right-Tail Optionality (Baillie Gifford) | How big can TAM get? | — |
| **Compounder** | Quality Earnings Power (Buffett) | How durable is the moat? | NVDA |
| **Special Situation** | Event-Driven | P(event) × upside? | — |

Archetypes are classified by Claude during model generation and tracked for stability over a 4-run rolling window. If classifications flip between runs, the stock is auto-flagged as a hybrid.

### Cyclical Mode (important — recently wired)
When `archetype.primary === "cyclical"`:
- Valuation uses Revenue × Normalized EBIT Margin × EV/EBIT = EV − Net Debt = Equity / Shares
- Dashboard sliders switch to EBIT margin + EV/EBIT (instead of P/E or P/S)
- Sensitivity table rows become EBIT margins (not revenues)
- DeductionChain shows the full normalized-earnings waterfall
- Bear case must model the cycle turning, not just a token haircut

The `ValuationMethod` type is `"pe" | "ps" | "cyclical"` (defined in `app/model/types.ts`).

### Target Engine (DCF)
- Institutional-grade discounted-forward DCF in `target_engine.py`
- Constant WACC across scenarios (no double-counting risk)
- Terminal growth capped at 2.5%
- Input validation catches None/NaN/absurd values
- `merge_enabled=True` — event-adjusted blend targets are authoritative
- Forward drivers auto-loaded from Supabase scout signals

---

## Known Issues & Gotchas

### Supabase Schema Drift
`supabase/migration.sql` does NOT always match the live database. Columns may be missing. The pipeline handles this by stripping unknown columns and retrying (loop up to 5 missing columns). If you see column errors, add them via Supabase SQL Editor:
```sql
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS <column_name> <type>;
```

Recent columns that may need adding:
- `archetype` (jsonb) on `stocks` table
- `research_cache` (jsonb) on `stocks` table
- `secondary` (text) on `archetype_history` table
- `justification` (text) on `archetype_history` table

### MU Data Source Bug
yfinance returns inflated MU Q1 FY26 revenue ($23.86B vs real ~$8.7B). TTM reads $58B vs real ~$40B. MU targets are unreliable until finance_data.py is fully migrated to EODHD. The `finance_data.py` has a DataProvider abstraction (yfinance/EODHD/AlphaVantage) with auto-detect and cross-validation, but EODHD may not be the default for all tickers yet.

### Financial Data Source of Truth
Financial models MUST use 10-K/10-Q actuals from `finance_data.py`. Hard-fail if fetch fails — never fall back to estimates or Perplexity-sourced numbers. The quant scout data is "ground truth" for current-state financials.

### Model Generation
- `generate_model.py` uses Claude Opus for primary generation, Sonnet for retries
- Prompt includes OUTPUT SIZE RULES to prevent truncation (max 3 sentences for notes, 2 for criteria detail)
- max_tokens = 32,000 with 4-layer JSON repair (clean parse → brace extraction → regex repair → truncation repair → retry with compact prompt)
- If a model truncates AND repair fails, it auto-retries with halved research text and "MAXIMALLY CONCISE" override
- The analyst_prompt.md in config/ is NOT injected into the generation prompt anymore (was causing redundancy/bloat)

### Growth Rate Signal Blending
`compute_smart_defaults` must weighted-blend growth signals (guidance, moat, TAM), never single-path waterfall. This was a critical fix — LITE went from $131 → $284 → $1139 as blending was corrected.

---

## Key Design Decisions

1. **No static targets** — All targets are derived from current data, factoring industry cycles, timeline, and external risks. Never hardcode a price target.

2. **Bottom-up derivation** — Each model input (revenue, margins, multiple) is derived independently from base rates. The target price EMERGES from inputs — it is never reverse-engineered from a desired price.

3. **Scenario probabilities are state-contingent** — Bear probability reflects current cycle position (late-cycle: 30-45%, mid: 20-30%, early: 10-20%), not fixed ranges.

4. **MECE criteria** — 8-12 criteria per stock covering 5 driver groups: Revenue (R), Margins (M), Multiples (P), Capital Structure (S), External/Macro (E). Criteria within the same group are NOT additive.

5. **Event impact blending** — Events (catalysts, risks) are converted to probability-adjusted price impacts by the event_reasoner, then blended with the DCF target via target_blend.py.

6. **Kill condition evaluation** — Each stock has a specific kill condition. Claude evaluates whether it's safe/warning/triggered using current evidence. A triggered kill condition should prompt position review.

---

## Verification

After making changes to the target engine, model export, or API routes:
```bash
python scripts/verify_model.py    # Checks engine ↔ Excel ↔ JSON parity across watchlist
pytest scripts/test_engine.py -v  # Regression tests (19 tests, no network needed)
```

A **pre-commit hook** runs both automatically:
- `test_engine.py` runs on every commit
- `verify_model.py` runs only when engine-related files are staged (target_engine.py, generate_model.py, finance_data.py, helpers.ts, etc.)

### Dashboard Health Panel
The dashboard has a "Health" button in the header that shows:
- **Data Providers** — which API keys are configured (EODHD, Perplexity, Claude, Gemini, etc.)
- **Regression Tests** — live pass/fail from `test_engine.py`
- **Pipeline Health** — last run status, scout success rate, run ID

API endpoint: `GET /api/health`

---

## Pipeline Performance Notes

- Full pipeline with 9 stocks takes ~10-15 minutes (scouts run in parallel)
- YouTube scout is the slowest (Gemini API + transcript fetching, ~2 min/stock)
- Model generation runs ~1-2 min/stock with Claude Opus
- Perplexity timeout is 30s (typical response: 3-10s)
- Claude timeout is 180s
- Gemini timeout is 30s per call, with 3 models × 2 attempts fallback

---

## Changelog

**IMPORTANT:** Every session that modifies code must append entries to `CHANGELOG.md` at the project root. Each entry includes: summary, files modified, reasoning, and before/after impact. This is how we track what changed and why across sessions.

---

## What to Do When Starting a New Session

1. Read this file first
2. Read `CHANGELOG.md` for recent changes
3. Check `docs/ROADMAP.md` for current priorities
4. Check `config/watchlist.json` for the active stock list
5. If making changes to valuation logic, run `verify_model.py` after
6. If making changes to the pipeline, test with `--ticker <single>` before `--all`
7. If Supabase errors appear about missing columns, add them via SQL Editor — don't assume migration.sql is in sync
8. **Update `CHANGELOG.md` before ending the session**
