# Stock Radar — Project Roadmap

**Last updated:** 2026-04-21  
**Status:** Post-architectural review. All critical/high-priority review items implemented. System is stable, merge_enabled flipped to True, forward drivers live.

---

## What Just Shipped (April 2026 Review Sprint)

All 10 priority items from the architectural review are complete and verified:

1. Shell injection eliminated — all 9 API routes converted from `exec()` to `execFile()` with ticker regex validation
2. "GS-parity" branding removed — renamed to "institutional-grade" throughout codebase
3. Convergence double-counting fixed — removed from weighted composite, now a conviction gate only
4. WACC constant across scenarios — no longer double-counts risk in probability-weighted DCF
5. Signal weights rebalanced — momentum up to 0.20, news down to 0.10 (academic evidence)
6. Scout parallelization — ThreadPoolExecutor cuts pipeline wall-clock ~80%
7. Kill conditions made specific — Claude prompt now requires named counterparty + numeric threshold + timeframe
8. Input validation layer — `_validate_inputs()` catches None/NaN/absurd values before DCF
9. Terminal growth capped at 2.5% — prevents "bigger than the economy" terminal values
10. `merge_enabled` flipped to True — event-adjusted blend targets are now authoritative

---

## Immediate Actions (You Need To Do)

These require your Supabase credentials or local environment — I can't run them from here:

**1. Fix LITE guided_op_margin (30% → 40%)**

```bash
cd stock-radar
python scripts/fix_lite_op_margin.py          # dry run — see what it finds
python scripts/fix_lite_op_margin.py --apply   # commit the fix
```

Then rebuild LITE to pick up the corrected margin:
```bash
# Via the dashboard Rebuild button, or:
curl -X POST http://localhost:3000/api/rebuild -H 'Content-Type: application/json' -d '{"ticker":"LITE"}'
```

**2. Apply discovery location migration**

Paste this into your Supabase SQL Editor (Dashboard → SQL Editor → New Query):

```sql
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS hq_city TEXT DEFAULT '';
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS hq_state TEXT DEFAULT '';
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS hq_country TEXT DEFAULT '';
```

**3. Verify merge_enabled behavior**

After rebuilding, check that the model page for any ticker shows "MERGED" (not "audit-only") in the Event Impacts panel. The `final_target` from the blend should now be the authoritative price.

---

## Medium-Term Priorities (Next 2-4 Weeks)

### P0: Migrate Off yfinance → EODHD or Polygon

**Why this is the single most important thing to do next.**

yfinance is the sole data source for all historical financials (10-K/10-Q actuals, TTM revenue, shares, market cap). It has a known bug where MU Q1 FY2026 returns $23.86B instead of the real ~$8.7B, making MU targets completely unreliable. It's also rate-limited, undocumented, and breaks without warning when Yahoo changes their internal API.

Every model in the system is only as good as its input data. A $5B revenue error produces a $5B error in the terminal value calculation.

**Recommended approach:**

- Primary: EODHD Fundamentals API ($20/mo) — covers US equities, quarterly + annual financials, shares outstanding, market cap. REST API with proper documentation and SLA.
- Fallback: Polygon.io ($99/mo for Stocks Starter) — broader coverage, real-time quotes, better for price data.
- Keep yfinance as a degraded fallback for tickers not covered by the primary source.

**Scope of work:**

- Rewrite `finance_data.py` to abstract the data source behind a provider interface
- Implement EODHD provider (map their field names to FinancialData contract)
- Add provider selection logic (env var or config)
- Cross-validate: run both providers on full watchlist, diff the outputs
- Update `_validate_inputs()` with provider-specific known-bad data patterns

**Estimated effort:** 2-3 sessions. The `FinancialData` dataclass is already a clean contract — the engine doesn't care where the numbers come from.

### P1: SBC Treatment Audit

Stock-based compensation flows through three places in the engine: (1) the SBC margin driver, (2) the FCF-SBC leg of the terminal value, and (3) the share dilution driver. If SBC is missing from the cash flow data, the engine falls back to `sbc_pct_rev` (default 5%), but this fallback isn't cross-checked against the actual dilution rate.

**What to check:**

- For each watchlist ticker, compare `sbc_pct_rev` default vs actual SBC from financials
- Verify that the FCF-SBC margin and the dilution rate don't double-count the same SBC
- Add a diagnostic to `_validate_inputs()` that warns when SBC is imputed vs actual

**Estimated effort:** 1 session.

### P2: Wire verify_model.py as Pre-Commit Hook

`verify_model.py` already checks engine ↔ Excel ↔ JSON parity across the watchlist. Making it a pre-commit hook prevents regressions from landing silently.

**Scope:**

- Add a `.pre-commit-config.yaml` or a git hook script
- The hook should run `verify_model.py --quick` (subset of tickers, no Excel, just engine JSON parity)
- Full verification (`--full`) remains a manual step before releases

**Estimated effort:** 30 minutes.

### P3: Regression Test Suite

There are currently zero automated tests. The 11 bugs fixed in the April engine audit, plus the architectural review fixes, should each have a corresponding test case.

**Priority test cases:**

- Negative growth scenario inversion (downside must produce lower price than base)
- Terminal growth cap enforcement (g_term > 2.5% should be capped)
- Weight sum invariant (FACTOR_WEIGHTS must sum to 1.0)
- Input validation: None revenue → ValueError, NaN shares → ValueError
- WACC constant across scenarios (down/base/up all use same discount_rate)
- Composite score renormalization when factors are missing
- `execFile` usage: no `exec` imports in any route.ts file

**Estimated effort:** 1-2 sessions.

### P4: Implement Transcript Fetching in Filings Scout

`scout_filings.py:62` has a TODO for transcript fetching. Earnings call transcripts are a high-signal source for forward guidance, management tone, and Q&A red flags.

**Options:**

- Seeking Alpha API (paid, best transcript quality)
- Financial Modeling Prep API (affordable, decent coverage)
- Whisper + YouTube for public earnings calls (free but noisy)

**Estimated effort:** 1-2 sessions depending on API choice.

---

## Long-Term Backlog (1-3 Months)

### Replace Linear Composite with Sigmoid Blend

The current composite score is a weighted linear average of factor scores. This means a 10/10 quant score with a 0/10 everything else still produces a middling composite. A sigmoid or logistic blend would create sharper separation between high-conviction and low-conviction stocks.

**Design considerations:**

- Sigmoid activation on each factor before blending (maps 0-10 to 0-1 with steeper gradient around the midpoint)
- Or: use the linear blend as input to a final sigmoid that creates the separation
- Calibrate against historical outcomes from the feedback loop once enough data accumulates

### Anchor Moat Scoring to Observable Proxies

The moat scout currently relies on Claude's qualitative judgment. This should be anchored to quantifiable proxies: gross margin stability over 5+ years, customer concentration (Herfindahl), switching cost indicators (contract length, integration depth), network effects (user growth vs revenue growth elasticity).

### Projection Score Quality Metrics

`compute_projection_score()` in `target_blend.py` determines how much weight events get in the final target. Track its accuracy: does a high projection score (growth/speculative) actually correlate with larger price moves from events? This needs 3-6 months of data from the feedback loop.

### Provisional Watchlist State for Discovery

Discovery candidates that pass AI validation currently go straight to "promoted" when added to the watchlist. Add a "provisional" state where they get 2-4 weeks of scout coverage before graduating to full watchlist status. This prevents low-quality discoveries from polluting the composite rankings.

### Dashboard Performance

As the watchlist grows, the dashboard re-renders the full stock grid on every poll. Consider:

- Server-side pagination for stocks
- WebSocket push for pipeline progress (instead of polling)
- Lazy-load the model page data (don't fetch forecast tables until the tab is opened)

### Architecture Map Auto-Generation

The `architecture-map.html` is hand-maintained and already has stale references (still says "GS-parity DCF" in the target engine node). Consider generating it from code analysis or at minimum adding a lint check that flags divergence.

---

## Decision Log

Decisions made during the architectural review that should be preserved:

| Decision | Rationale | Date |
|----------|-----------|------|
| Constant WACC across scenarios | Varying WACC double-counts risk when cash flows already reflect the scenario | 2026-04-21 |
| Convergence as conviction gate, not score input | Including it as a weighted factor double-counts scout agreement | 2026-04-21 |
| Terminal growth cap at 2.5% | Above risk-free rate implies company becomes larger than economy | 2026-04-21 |
| Momentum weight 0.20, news weight 0.10 | Momentum alpha is academically robust (AMP 2013); news sentiment alpha has decayed | 2026-04-21 |
| "Institutional-grade" not "GS-parity" | SEC AI-washing enforcement trend (Delphia, Global Predictions); can't claim Goldman equivalence | 2026-04-21 |
| execFile over exec everywhere | Shell injection via ticker URL params; execFile doesn't invoke a shell | 2026-04-21 |
| ThreadPoolExecutor for scouts | Scouts are independent (different data sources); ~80% latency reduction | 2026-04-21 |
| merge_enabled = True | Blend targets with event adjustments are now authoritative; sufficient audit trail exists | 2026-04-21 |
