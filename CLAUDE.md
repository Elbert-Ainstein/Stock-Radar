# Stock Radar — AI Handoff Document

**Owner:** Hume (asyanurpekel@gmail.com)
**Last updated:** 2026-07-02 (full rewrite — the 2026-04-23 version described a system three pivots old and contained an inverted data directive; see the changelog entry of this date)
**Status:** Production, single-operator. 6-stock watchlist. Mid-pivot to the dual-system / 10× architecture (see `docs/ROADMAP.md`).

---

## What This Is

Stock Radar is a personal investment-research platform hunting 10× opportunities. Since May 2026 its **core is the thesis/judgment path**, not the original scout pipeline:

- **Thesis path (money path):** `scripts/run_thesis.py` — a 12-step Opus + web-search thesis per ticker → closing JSON (targets, dual conviction, risk_adj_ev_ratio) → **code-enforced trade gate** (`trade_gate.py`, clamps conviction/position by recomputed risk-adj-EV ratio) → **archetype-routed kill gate** (`kill_gate.py`, relax-only) → Model D vision bracket (transformational names) → Supabase `theses` + memory file. This produces the dashboard headline verdict.
- **Socratic judgment:** `scripts/run_socratic.py` — Models A (fundamentals) / B (regime) / C (adversarial) in parallel → corpus callosum → research round → rough target band, **sealed** into `prediction_log` (`checkpoint_seal.py`) and graded at T+30/60/90 by the cron grader (`run_checkpoint.py` — grades genuine Socratic seals only). Mode-of-N consensus exists (`consensus.py`, `SELF_CONSISTENCY_N`, default 1 = off; production convention is 5).
- **Valuation engine:** `scripts/target_engine.py` — Gordon+ROIIC-primary DCF with exit-multiple cross-checks, bottom-up WACC (constant across scenarios), three methods (EV/EBITDA-FCF, P/S for pre-profit, cyclical normalized-EBIT), archetype-routed horizons and dcf_role (transformational → DCF-as-floor).
- **Legacy pipeline (still scheduled, fate under decision):** scouts → `analyst.py` composite scoring → `generate_model.py` Opus scenario models → `stocks`/`analysis` tables. Runs 2× daily via GitHub Actions. See `docs/decisions/TARGET_SOURCE_OF_TRUTH_2026-07-02.md` — three unreconciled target numbers exist per ticker; the theses row is the verdict of record.
- **Context layers injected into judgment runs:** `[MACRO]`/`[WAVE]` (macro snapshot — stale, hand-seeded 2026-05-17; `run_macro.py` never built), `[VIX]` (`vix.py`), `[CHAIN]` (`analyst_panel.py` — 7-node AI-chain cycle clocks, deterministic propagation), validated_corrections, operator notes.
- **Discovery (dormant since 2026-05-09):** two generations; convergence UI renders May-era data; primary buttons are unwired. Revive-or-retire decision pending (`docs/ROADMAP.md`).

**Frontend:** Next.js 16 + React 19 dashboard (`app/`) — watchlist with thesis verdicts, per-stock model pages with engine-driven sliders, health panel. `next build` passes as of 2026-07-02. **Auth:** mutating `/api` routes require `SR_API_SECRET` when set (`middleware.ts`).

---

## Running the System

```bash
# Thesis (money path) — one ticker
python scripts/run_thesis.py LITE

# Socratic judgment round (production convention: SELF_CONSISTENCY_N=5)
python scripts/run_socratic.py LITE

# Grader (cron; grades ripened seals, source-filtered)
python scripts/run_checkpoint.py [--dry-run]

# Legacy pipeline
python scripts/run_pipeline.py                # scouts + analyst + models (exits nonzero on failure)
python scripts/run_pipeline.py --rebuild-only --no-thesis   # what the 2x-daily Action runs
python scripts/run_pipeline.py --ticker MRVL  # single-stock mini-pipeline

# Dashboard
npm run dev      # http://localhost:3000  (build: npx next build)
```

**Environment:** copy `.env.example` → `.env` — it lists exactly the variables the code reads (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `GEMINI_API_KEY`, `EODHD_API_KEY`, `ALPHA_VANTAGE_API_KEY`, optional `SR_API_SECRET`, `SELF_CONSISTENCY_N`). `pip install -r requirements.txt` covers the full money path.

---

## Watchlist (6 stocks)

**LITE, PLTR, RKLB, ACHR, CELH, SNDK** — source of truth is `config/watchlist.json` / the `stocks` table.

- **Memory names (SNDK; MU when tracked):** large single-quarter revenue jumps are **genuine supercycle prints, verified against SEC XBRL** (2026-06-26). The old "MU Data Source Bug" note was wrong — the defect was in the EDGAR cross-check's calendar-bucket alignment (fixed: nearest-period-end matching, 45-day tolerance). **Do not suppress or "correct" supercycle-scale revenue.**
- **SNDK** re-IPO'd 2025-02: pre-2025 data is the old SanDisk — `TICKER_DATA_CUTOFFS` in `finance_data.py` enforces the cutoff.
- Archetype tags are pending owner confirmation: `docs/decisions/ARCHETYPE_PROPOSALS_2026-07-02.md`. Until applied, kill evaluation defaults to GARP guidance for untagged names.

---

## Financial Data (source of truth rules)

- `finance_data.py` DataProvider chain (EODHD primary / yfinance / AlphaVantage), per-ticker overrides in `config/data_provider_overrides.json`, manual per-quarter patches in `config/manual_quarterly_overrides.json` (both currently empty — healthy).
- **Hard-fail contract:** models use 10-K/10-Q actuals or raise `EarningsFetchError`. Never estimate historicals, never use Perplexity numbers for financials.
- **EDGAR XBRL cross-check is the hard gate** (revenue, nearest-period-end alignment). Known holes (open debt): revenue-only (margins/shares unchecked), fiscal Q4 structurally outside the gate, label-based fallback when providers omit dates.
- `fetch_financials(as_of=...)` gives the point-in-time view for backtests/fixtures (restored 2026-07-02; drops periods not publicly filed by as_of, 45-day filing lag).

---

## Verification & Ops

- **Tests:** `python -m pytest scripts/ -q` — ~200 deterministic tests, <1s, offline. The only expected failure without live providers is `test_engine_fixtures::test_skip_floor` (fixtures need network; re-capture pending on the operator machine).
- **CI:** `.github/workflows/tests.yml` runs the suite on every push/PR. **Pre-commit hook is tracked** — install per clone with `bash scripts/hooks/install.sh`.
- **Migrations:** `supabase/` is append-only SQL applied MANUALLY in the Supabase SQL editor; the live DB drifts from the files. Current consolidated pending file: `supabase/2026-07-02_consolidated_pending.sql` (seal fields + append-only RLS, kill_gate_override, model_d_bracket, strategic axis, quarantine flag — includes verification queries). Writers strip-and-retry unknown columns with stderr warnings; the stripped data is lost for that row, so apply migrations promptly. Do NOT trust `validate_schema` — it checks only the 5 legacy tables.
- **Scheduled Actions run `main`.** Until the session branch merges, scheduled runs use old code (split-brain). `verify_model.py`'s Excel-parity leg is dead (needs a `recalc.py` that never existed) — "diffs=0" means *not checked*.
- **Backups:** prepared, not active — `docs/ops/BACKUP_PLAN_2026-07-02.md`.

---

## Key Design Rules (unchanged)

1. **No static targets** — targets emerge from current data; never hardcode or reverse-engineer a price.
2. **Bottom-up derivation** — each driver derived independently from base rates.
3. **The trade gate is code, not prose** — `risk_adj_ev_ratio` is recomputed from `risk_adj_target/spot` and the Step-12 clamp table is enforced in `trade_gate.py` (downward only). `kill_gate.py` is relax-only, archetype-routed. Strategic conviction (Type A) is never clamped by price.
4. **Facts over prediction** — the 5–10y structural state is the only allowed forward input; attention is a current-market fact, timing-only.
5. **Seals are append-only** — never mutate `prediction_log`/`prediction_outcomes`; corrections are new rows or dated service-role migrations. The grader filters to genuine Socratic seals.
6. **Money-path files (`run_thesis.py`, `run_socratic.py`, `finance_data.py`, `target_engine.py`, prompts) merge only with explicit owner approval.** Small logical commits; no "new"/"improvements" messages.

---

## Changelog Discipline

**Every session that modifies code appends a CHANGELOG.md entry** (summary, files, reasoning, falsifiable acceptance criteria). This rule was violated once (2026-07-01, reconstructed after the fact) — don't repeat that.

---

## Starting a New Session

1. Read this file, then `CHANGELOG.md` (top entries — it is the real history).
2. `docs/ROADMAP.md` — current priorities and which framework governs.
3. `docs/reports/CODEBASE_ASSESSMENT_2026-07-02.md` — the audit; where the bodies are buried.
4. Open decisions live in `docs/decisions/` — don't build on an undecided fork.
5. Run the suite before and after changes; engine/valuation changes need `test_engine*.py` green and a changelog entry with acceptance criteria.
6. Supabase column errors → check `supabase/2026-07-02_consolidated_pending.sql` was applied before adding ad-hoc columns.
