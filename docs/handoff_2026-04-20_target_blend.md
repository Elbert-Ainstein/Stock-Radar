# Handoff — Spectrum-Aware Target Blend (Phase 2.5)

**Date:** 2026-04-20
**Branch:** event-target main
**Canonical design doc:** `docs/event_target_plan.md`
**Related memory:** `.auto-memory/project_scout_progress.md`

---

## Why this work exists

The same +5% event signal means different things for different companies.
For a revolutionary projection-bet (AMD, LITE AI-infra), events are the
leading evidence the thesis is playing out — they should flow nearly
fully into the target. For a mature returns-focused company (KO, AAPL
dividend aristocrat), events are mostly noise around established financials
— the quarterly fundamentals already reflect truth, so events should be
damped.

A static `proposed_target_with_events` that just stacked criteria + events
at full weight treated every company the same. The user explicitly flagged
this: *"make sure to use dynamic weights. Some companies have strong
projection, some have high returns now. We need to be good at where to
be in the spectrum."*

Phase 2.5 builds the adaptive blend and wires it through analyst →
Supabase → (next) dashboard.

---

## What is SHIPPED

### Phase 1 — Audit-only event pipeline (2026-04-18)
Events flow from scouts (news, catalyst, moat) through the reasoner into
`event_impacts.summary.event_adjustment_pct`. Side-by-side with
criteria. Not merged into the authoritative target.

### Phase 2 — Per-type stack-cap dedup (2026-04-20)
`event_reasoner._apply_type_stack_cap()` groups events by type, applies
diminishing weights `[1.0, 0.45, 0.20, 0.10, 0.05]`, caps cluster at
template magnitude_max. Prevents 5 correlated `market_share_gain` facets
from stacking as 5 independent stories. AMD pre-dedup +15.0% →
post-dedup +11.5%.

### Phase 2.5 — Dynamic blend module (JUST SHIPPED)
**`scripts/target_blend.py`** — two functions:

1. `compute_projection_score(fundamentals, quant, stock_config) → dict`
   - Score on 0.0 (pure returns/now) → 1.0 (pure projection/future)
   - Signals: revenue growth YoY, forward PE, user tags
     (revolutionary/hypergrowth vs dividend_aristocrat/mature),
     valuation method (PS vs PE)
   - Returns `{score, baseline, contributors[], raw_score,
     final_explanation}` so the dashboard renders exactly why.

2. `blend_targets(base, criteria_pct, event_pct, projection_score) → dict`
   - `event_weight = 0.30 + 0.70 × projection_score`  (range 0.30–1.00)
   - `final_target = base × (1 + criteria_pct + event_weight × event_pct)`
   - Returns full deduction chain: base, criteria component, raw event
     component, weighted event component, total adjustment, final target,
     human-readable formula string.

CLI demo results (sanity check):
- AMD (rev 34%, fwd PE 25, revolutionary tags) → score 0.80 → weight 0.86
- KO-style (rev 4%, fwd PE 22, div aristocrat) → score 0.10 → weight 0.37
- LITE (rev 28%, fwd PE 38, ai_infrastructure) → score 0.90 → weight 0.93

### Analyst wiring (JUST SHIPPED)
`scripts/analyst.py`:
- Graceful-degrade import for `target_blend` (mirrors the
  `event_reasoner` pattern — fallback uses neutral 0.65 event_weight if
  module absent).
- After `event_summary` is computed, call `compute_projection_score()`
  then `blend_targets()`.
- `event_impacts` output dict now includes: `projection_score`,
  `blend`, `final_target`, `blend_available`. Legacy
  `proposed_target_with_events` (static full-weight) retained so the UI
  can diff old vs new.
- `merge_enabled` stays `False` until Phase 2.5 dashboard update lands —
  flipping it later will make downstream consumers read `final_target`
  instead of `adjusted_target`.

---

## OPEN BUG (currently fixing)

AMD first rebuild after wiring returned projection_score **0.65**, not
the expected ~0.80. Root cause: `target_blend.py` read
`revenue_growth_yoy` from `fundamentals_data` only, but scouts actually
store revenue growth as:
- `quant.data.revenue_growth_pct` → `34.1` (percentage-points)
- `fundamentals.data.revenue_growth_yoy` → fraction (currently empty
  for AMD)

**Fix applied** (just edited `scripts/target_blend.py`):
- Probe `fundamentals_data.revenue_growth_yoy` first
- Fall back to `quant_data.revenue_growth_pct` and divide by 100
- Defensive normalization: if caller passes value ≥ 1.5, treat as
  percentage-points and auto-convert to fraction

**Not yet re-verified** — next step is to rebuild AMD and confirm
projection_score jumps to ~0.80 and blend reads back correctly from
Supabase.

---

## WHAT'S NEXT (in order)

### 1. Verify the fix — rebuild AMD + audit blend math (Task #82)
```bash
cd "stock-radar"
python scripts/rebuild_analysis.py --ticker AMD
# Then pull the row:
python -c "from scripts.utils import load_env; load_env(); from scripts.supabase_helper import get_client; import json; r = get_client().table('latest_analysis').select('event_impacts').eq('ticker','AMD').execute().data[0]['event_impacts']; print(json.dumps(r['projection_score'], indent=2)); print(json.dumps(r['blend'], indent=2))"
```

Expect:
- projection_score.score ≈ 0.80 (0.50 baseline + 0.20 rev growth + 0.15 tags – 0.05 PE)
- blend.event_weight ≈ 0.86
- blend.final_target ≈ $555 ($500 × 1 + 0.86 × 11.54% = $549.6 → $550-555 range)

### 2. Full watchlist rebuild
```bash
python scripts/rebuild_analysis.py
```
Spot-check each ticker's `projection_score.final_explanation` and
`blend.formula` for intuition. Specifically:
- AMD, LITE → high score, event_weight ≥ 0.85
- SNDK, MU → mid score
- APP, NVDA → mid-high score
- MRVL, TER → whatever the data supports (may be 0 events)

### 3. Dashboard transparency (Task #81)
`app/model/model.tsx` — `EventImpactsPanel`:
- Add collapsed-by-default "Why this weighting?" section showing:
  - `projection_score.final_explanation` (the trail string)
  - `projection_score.contributors[]` as a mini-table
  - `blend.formula` as a single-line deduction chain
  - Badge: "Projection-heavy" (≥0.70) / "Balanced" (0.40-0.70) /
    "Returns-heavy" (<0.40)
- Two target lines side-by-side:
  - `criteria_eval.adjusted_target` labeled "Criteria-only"
  - `event_impacts.final_target` labeled "With events (weighted)"
- Diff badge if they differ by >5%

### 4. Phase 2.5 flip decision
Once dashboard shows the deduction chain and the numbers look right
for a few days of live runs, flip `merge_enabled=True` in analyst
output. That switches the authoritative target from
`criteria_eval.adjusted_target` to `event_impacts.final_target`
for downstream consumers (rankings, alerts, brief view).

---

## Key file touchpoints

| File | What lives there |
|------|------------------|
| `scripts/target_blend.py` | New module — projection score + blend fn |
| `scripts/event_reasoner.py` | Phase 2 stack-cap dedup |
| `scripts/analyst.py` | Imports, wires blend after event_summary, adds fields to `event_impacts` output |
| `scripts/rebuild_analysis.py` | Emergency "recompute analysis from existing Supabase signals" |
| `supabase/2026-04-20_event_impacts_and_amd.sql` | event_impacts column + AMD config backfill |
| `supabase/2026-04-20_refresh_views.sql` | Refresh latest_analysis + latest_signals views after column add |
| `app/model/model.tsx` | `EventImpactsPanel` — awaiting Phase 2.5 transparency update |
| `docs/event_target_plan.md` | Canonical design doc |

---

## Data shape dependency notes

Watch out for these inconsistencies when touching blend code:

- Revenue growth is stored **two ways**: `fundamentals.revenue_growth_yoy`
  as fraction vs `quant.revenue_growth_pct` as percentage-points. Blend
  probes both.
- Criteria adjustment percent is in **percentage-point terms** (e.g.
  11.5 means 11.5%, not 0.115). Blend respects this convention from
  analyst.
- `latest_analysis` view column is `criteria_eval` in DB, not
  `criteria_evaluation`. Python model serializes as
  `criteria_evaluation` but DB stores/serves as `criteria_eval`.
- Supabase view staleness: adding a column to `analysis` table does
  NOT auto-propagate to `latest_analysis` view. Must `DROP VIEW` +
  `CREATE VIEW` to refresh column list.

---

## How to resume

Open this file plus `.auto-memory/project_scout_progress.md`, then
run step 1 above. If projection_score and blend numbers look right,
move to step 2 (full watchlist) and then step 3 (dashboard UI).
