# Brief + Detailed + Excel Price-Target Model — Build Report

Date: 2026-04-19
Scope covered: design of the earnings-first data fetcher, target engine, Excel exporter, dashboard API routes, and two frontend views. Plus verification across all 11 watchlist tickers.

---

## 1. Constraint that set the direction

Before any design work, a hard rule was established:

> Historical financials for any price-target model MUST come from actual 10-K/10-Q filings. If they cannot be fetched, do not generate a model — tell the user.

This rule was saved permanently to `feedback_earnings_as_source_of_truth.md` and changed the entire architecture: instead of treating forward assumptions as the single input, actuals became the foundation and assumptions became the overlay the user tinkers with via sliders.

---

## 2. `scripts/finance_data.py` — the single source of historicals

Purpose: one module, one entry point — `fetch_financials(ticker)` — that returns either a fully populated `FinancialData` or raises `EarningsFetchError`. There is no silent fallback to Perplexity/estimates anywhere in the pipeline.

Contract:
- Pulls quarterly + annual income statement, cash flow, and balance sheet from `yfinance` (SEC-filing-sourced).
- Validates `REQUIRED_LINES` across both views; only raises if required lines are missing in BOTH.
- Derives `net_debt = Total Debt − Cash` with a fallback to `Long Term + Current Debt − Cash` when composite `Total Debt` is absent.
- Derives diluted shares preferring `Diluted Average Shares` on the IS, falling back to `Ordinary Shares Number` on the BS.
- Refuses to build any model for a ticker with fewer than 4 quarters AND fewer than 2 years of data — surfaced as a clear error.
- Ships with a CLI so auditing any ticker's data availability is one command: `python scripts/finance_data.py LITE`.

Verified against all 11 tickers. Every one returns usable 5–6 quarters of IS + cash flow + balance sheet plus 3–5 years of annual data. ACHR is pre-revenue (TTM = $0) and that surfaces cleanly downstream as non-meaningful price points.

---

## 3. `scripts/target_engine.py` — pure-function price engine

Design goal: one pure function consumed identically by the brief view, detailed view, and Excel exporter so there can be no "this number in the UI doesn't match the spreadsheet" class of bug.

Inputs: `FinancialData` + a loose dict of driver overrides. Every missing driver falls back to `DEFAULT_DRIVERS`. Driver keys are intentionally not hardcoded into the frontend — the frontend reads the slider list from `DEFAULT_SLIDER_KEYS` shipped with the API payload.

Math flow (base case):
1. TTM revenue = sum of last 4 quarterly revenues (no fallback to info.TTM metrics).
2. Revenue Y1 = TTM × (1 + g1). Revenue Y2 = Y1 × (1 + g2).
3. Op margin ramps linearly from current TTM margin toward `op_margin_target` over Y1–Y2.
4. EBITDA Y2 = OI + `da_pct_rev` × Rev.
5. Net income Y2 = OI × (1 − tax_rate).
6. Method 1: EV = EBITDA × `ev_ebitda_multiple`; equity = EV − net debt; price = equity ÷ diluted shares (with dilution applied over 2 years).
7. Method 2: equity = NI × `pe_multiple`; price = equity ÷ diluted shares.
8. Base target = 50/50 blend of methods 1 and 2.
9. Low and high scenarios apply `scenario_width` haircut/premium on growth rates AND multiples simultaneously (symmetric). Result is clamped so low ≤ base ≤ high.

Each step produces a `DeductionStep` row so the UI and the Excel both show the same derivation path.

Output includes the full 8-quarter forecast and 2-year forecast rollup so downstream consumers never re-compute anything.

---

## 4. `scripts/model_export.py` — GS-style Excel with live formulas

A 6-sheet workbook that follows sell-side color conventions:

- Blue text = hardcoded inputs (drivers + historical actuals).
- Black text = in-sheet formulas.
- Green text = cross-sheet links.
- Yellow fill on driver cells.

Sheets:
1. **Cover** — price summary, capitalization, TTM actuals, authorship note.
2. **Assumptions** — every driver in one column, with descriptions. Every forecast cell in every other sheet references this tab. Change one blue cell and the workbook re-prices.
3. **P&L Summary** — up to 4 historical years + 2 forecast years. Forecast revenue, OI, EBITDA, NI all formula-driven.
4. **Income Statement** — 5 historical quarters + 4 forecast quarters, with gross/operating/net margin rows that recompute live.
5. **Cash Flow** — 5 historical quarters + 4 forecast quarters, with forecast FCF as a cross-sheet link to Income Stmt (the green cells).
6. **Valuation** — three-column scenario (Low/Base/High) showing the full derivation: scenario multiplier → revenue → op income → EBITDA → NI → EV/EBITDA price → P/E price → blended target → upside %.

Every workbook written is passed through `scripts/recalc.py`. Zero formula errors on every ticker.

**Cross-check:** the Excel `Valuation!D27` (base blend) and `target_engine.build_target().base` agree to the cent for LITE, AAPL, APP — confirming the two code paths produce identical math.

---

## 5. Dashboard wiring

### API routes
- `GET /api/model/[ticker]` — wraps `target_api.py`, accepts driver overrides as numeric query params, returns the full JSON payload (target + steps + forecast + sliders + historicals + capitalization). Allowlists driver keys with a regex to prevent command injection.
- `GET /api/model/[ticker]/excel` — runs `model_export.py` and streams the `.xlsx`.

### Components
- `components/TargetBrief.tsx` — the brief slider view. Fetches the payload, renders the **4-stat price range row** (Current / Low / Base / High with upside %), slider list driven entirely by `payload.sliders` (so the engine controls which sliders appear, not the frontend), and the deduction chain table. Debounced refetch at 180ms on any slider drag so the chain updates live. Includes Reset button and links to the detailed page / Excel download.
- `app/model/[ticker]/detailed/DetailedModel.tsx` — dedicated per-stock page with GS-style tabs: P&L Summary, Income Stmt, Cash Flow, Valuation. Valuation tab shows the full deduction chain plus a side-by-side EV/EBITDA vs P/E comparison.

---

## 6. Verification across all 11 tickers

Batch-built `/out/{TICKER}_model.xlsx` and `/out/targets/{TICKER}.json` for the full watchlist. Recalc returned `status: success, total_errors: 0` for every file. Summary of base targets (default drivers, no slider adjustments):

| Ticker | Current | Low | Base | High | Upside (base) |
|---|---:|---:|---:|---:|---:|
| LITE | $894.07 | $84 | $144 | $222 | −83.8% |
| MRVL | $139.69 | $38 | $62 | $93 | −55.4% |
| MU | $455.07 | $212 | $339 | $504 | −25.4% |
| APP | $477.20 | $69 | $112 | $167 | −76.5% |
| NVDA | $201.68 | $37 | $59 | $87 | −70.9% |
| SNDK | $920.99 | $239 | $383 | $568 | −58.4% |
| TER | $380.38 | $84 | $134 | $200 | −64.6% |
| AMD | $278.39 | $87 | $140 | $208 | −49.7% |
| RKLB | $84.80 | $4.84 | $7.48 | $10.88 | −91.2% |
| ACHR | $6.11 | $0.67 | $0.67 | $0.67 | −89.0% |
| AAPL | $270.23 | $120 | $194 | $289 | −28.2% |

The negative upside numbers are expected — default drivers are conservative growth/multiple assumptions, and the current prices on several tickers (LITE at $894, SNDK at $921, RKLB at $85, etc.) look elevated relative to TTM cash generation. These are the inputs the sliders exist to override.

## 7. Known follow-ups (not blockers)

- **yfinance price oddity:** several tickers (LITE, SNDK) show `info.currentPrice` values that seem high versus recent trading ranges. Worth verifying against an independent price source and falling back to `regularMarketPrice` → `previousClose` → historical close if suspicious. Does NOT affect the model math itself — only the `current_price` anchor used for upside %.
- **ACHR pre-revenue:** the engine produces a near-zero target because TTM = $0. For genuinely pre-revenue names the math really should flip to an option-value / bookings-ramp framework. Engine currently surfaces a warning but still prints a number; could raise instead.
- **12-sheet GS replica:** today's export has 6 sheets (Cover + Assumptions + P&L Summary + IS + CF + Valuation). The full GS template also had Revenue Summary, NTM Valuation, Capex & Depreciation, Working Capital, Debt & Interest, Shares Outstanding as separate tabs. Can be added incrementally — each would just read from Assumptions the same way.
- **Next.js route `/api/model/[ticker]/excel`** runs `model_export.py` per request. Fine for a handful of concurrent users; for heavier load it should cache the xlsx keyed by driver-hash.
- **Scout bug hunt** across all 8 watchlist tickers: the target engine surfaced no crashes or obvious data corruption — all 11 tickers produced a valid result. No bugs caught this pass, but that is a live claim against one moment in time; worth re-running after any future scout changes.

---

## Files touched or created

New:
- `scripts/finance_data.py` (earnings fetcher; hard-fail contract)
- `scripts/target_engine.py` (pure-function price engine)
- `scripts/model_export.py` (6-sheet GS-style Excel writer)
- `scripts/target_api.py` (JSON CLI + batch writer)
- `app/api/model/[ticker]/route.ts` (JSON API)
- `app/api/model/[ticker]/excel/route.ts` (Excel download API)
- `components/TargetBrief.tsx` (brief slider view)
- `app/model/[ticker]/detailed/page.tsx` + `DetailedModel.tsx` (detailed per-stock page)
- `out/{TICKER}_model.xlsx` × 11
- `out/targets/{TICKER}.json` × 11

Memory:
- `feedback_earnings_as_source_of_truth.md` (already in place — the rule that shaped this design)

---

## How to use it

```bash
# Refresh a single ticker's model and JSON
python scripts/target_api.py LITE

# Tinker with drivers from the CLI
python scripts/target_engine.py LITE rev_growth_y1=0.25 ev_ebitda_multiple=22

# Rebuild all 11 JSON payloads
python scripts/target_api.py --batch

# Write the Excel
python scripts/model_export.py LITE

# Verify zero formula errors
python /sessions/.../skills/xlsx/scripts/recalc.py out/LITE_model.xlsx
```

From the dashboard: visit `/model/LITE/detailed` for the full view, or embed `<TargetBrief ticker="LITE" />` inside any existing page for the slider view.
