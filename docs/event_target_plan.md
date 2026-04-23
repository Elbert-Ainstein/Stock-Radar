# Event-Driven Price Target Plan

Version 0.1 — 2026-04-17

## 1. The gap

Today `adjusted_target` in `analyst.py` is purely a function of the pre-defined `criteria` list per stock. If an event isn't pre-enumerated as a criterion, it cannot move the target — even if it obviously should. The LITE Canada-facility acquisition is a textbook case: it materially changes the capacity ceiling and thus the revenue model, but no existing criterion captures it.

The news scout already ingests this information — it just dies at the "overall sentiment score" stage. We need a path from **structured event → causal chain → target adjustment** that runs alongside the criteria adjustment, not in place of it.

## 2. What the research says

I pulled from both academic event-study literature and practitioner frameworks. The relevant takeaways:

**Magnitudes of market reactions are well-calibrated empirically.** 3-day cumulative abnormal returns (CARs) have consistent ranges per event type: M&A target firms +15-30%, top-decile earnings surprises +3-5%, FDA approvals for small biotech +15-40%. A narrow 3-day window captures 80-90% of the total price adjustment for well-defined events in liquid markets. We can anchor our baseline impacts to these empirical distributions rather than asking an LLM to invent them.

**Scenario-weighted targets are the industry standard.** The institutional approach is Bull/Base/Bear × Probabilities = expected value, with 12-24 month horizons. Our current system already has scenario data in `stocks.scenarios` — we should lean into that structure rather than invent a new one.

**Catalyst tracking is the explicit layer between news and target.** Pro analysts maintain a "catalyst list" per stock with: firm dates, quantified impact on key numbers or multiple, probability of occurrence, and entry/exit bands. This is exactly the layer we're missing.

**LLM event extraction is a solved problem by 2026.** Recent papers show direct text-to-structured-output extraction achieves state-of-the-art F1 on financial benchmarks. The risk is not extraction — it is magnitude estimation. That is where templating helps.

**Confidence must decay with time.** Prediction performance degrades on longer horizons; model conviction should too. Events older than their expected resolution window should either materialize (become a criterion hit) or fade out.

## 3. Architecture

Three new components, one extension, one schema change:

```
Scout layer
  scout_news.py            [EXTEND]  emit events[] alongside bull/bear counts
  scout_fundamentals.py    [EXTEND]  emit events[] from deep analysis
  (scout_youtube, social)  [OPTIONAL] extend later

Analyst layer
  event_reasoner.py        [NEW]  LLM-driven chain-of-causality impact sizing
  event_templates.py       [NEW]  type → baseline magnitude/horizon/confidence
  event_dedup.py           [NEW]  semantic dedup + persistence across runs
  analyst.py               [EXTEND]  call reasoner, sum into adjusted_target

Data layer
  events (new table)       [NEW]  persistent per-stock event store
  analysis.event_impacts   [NEW]  JSONB column; breakdown per run
```

Data flow end-to-end:

```
raw news / fundamentals
       │
       ▼
scout emits events[]: [
  { raw_summary, url, date, primary_ticker }
]
       │
       ▼
event_dedup.py
  - semantic group across scouts + prior runs
  - assign stable event_id = hash(canonicalized_summary)
  - mark as NEW / CONTINUING / RESOLVED / STALE
       │
       ▼
event_reasoner.py  (one Claude call per NEW or UPDATED event)
  - classify → event_type  (lookup template for baseline range)
  - reason chain: event → op effect → financial effect → valuation effect
  - pick magnitude within template range, with explanation
  - estimate probability-of-materialization
  - output: { type, direction, magnitude_pct, confidence,
              probability, time_horizon_months, chain, evidence }
       │
       ▼
analyst.py
  - apply recency decay + probability + confidence
  - cap per-event and total saturation
  - combine: adjusted_target = base × (1 + crit_pct/100 + event_pct/100)
  - write events[] into analysis.event_impacts
       │
       ▼
dashboard / model page
  - show criteria adjustment and event adjustment separately
  - expandable chain per event
  - mute / override control per event
```

## 4. Event taxonomy (v1)

The taxonomy is deliberately narrow at launch — 15 types, enough to cover 90%+ of what our current scouts actually surface. Expand as gaps appear.

| Event Type | Baseline target Δ | Baseline confidence | Horizon | Notes |
|---|---|---|---|---|
| `ma_target` | +15 to +35% | 0.85 | 1-6mo | Target of acquisition announced |
| `ma_acquirer` | -5 to +5% | 0.55 | 6-18mo | Depends on synergy quality |
| `regulatory_approval` | +8 to +25% | 0.90 | immediate | FDA, FAA TC, CE mark, etc. |
| `regulatory_rejection` | -10 to -40% | 0.90 | immediate | |
| `earnings_beat_raise` | +3 to +10% | 0.80 | 3-9mo | Top/bottom line + guide-up |
| `earnings_miss_cut` | -5 to -15% | 0.80 | 3-9mo | |
| `capacity_expansion` | +1 to +6% | 0.50 | 12-24mo | **LITE Canada case** |
| `supply_constraint` | -2 to -8% | 0.70 | 3-9mo | |
| `customer_win_major` | +2 to +8% | 0.60 | 6-18mo | Anchor customer or >5% revenue |
| `customer_loss_major` | -5 to -15% | 0.80 | 6-12mo | |
| `product_launch` | +2 to +8% | 0.55 | 6-18mo | Commercial launch, not demo |
| `product_delay` | -2 to -10% | 0.80 | 3-12mo | |
| `exec_change_positive` | +2 to +6% | 0.40 | 12-24mo | Proven operator hired |
| `exec_change_negative` | -3 to -12% | 0.70 | 3-12mo | Unexpected CEO/CFO departure |
| `litigation_adverse` | -3 to -12% | 0.75 | 6-24mo | Material ruling |
| `litigation_favorable` | +1 to +5% | 0.60 | 6-24mo | |
| `competitive_threat` | -2 to -10% | 0.45 | 12-36mo | New entrant, price cut, etc. |
| `sector_tailwind` | +1 to +5% | 0.40 | 12-24mo | Macro / commodity / policy |
| `sector_headwind` | -1 to -5% | 0.40 | 12-24mo | |
| `buyback_large` | +1 to +4% | 0.70 | 3-12mo | >5% of market cap |
| `dividend_cut` | -5 to -15% | 0.90 | immediate | Signals deteriorating cash |

Baseline values are **anchors for the LLM**, not hard limits. The reasoner picks a value within the range and writes a justification that can be inspected.

## 5. Causal chain format

Every event carries a 3-level chain so the user can audit the logic and the system can apply compound confidence:

```json
{
  "event_id": "lite_2026q1_canada_facility",
  "type": "capacity_expansion",
  "summary": "Lumentum acquires Montreal photonics facility",
  "direction": "up",
  "chain": [
    {
      "level": 1,
      "claim": "Facility adds ~25% to datacom transceiver production capacity",
      "confidence": 0.80,
      "reasoning": "Based on announced facility sqft + industry capacity benchmarks"
    },
    {
      "level": 2,
      "claim": "Enables +4% to +8% revenue ceiling over 18 months if demand holds",
      "confidence": 0.60,
      "reasoning": "Assumes current backlog utilization; demand gates realization"
    },
    {
      "level": 3,
      "claim": "Translates to +3% to +5% target price at current PS multiple",
      "confidence": 0.55,
      "reasoning": "Sector ~6x forward P/S; partial uplift to the multiple itself"
    }
  ],
  "magnitude_pct": 4.0,
  "probability": 0.70,
  "compounded_confidence": 0.264,  // product of levels
  "expected_contribution_pct": 4.0 * 0.70 * 0.264 = 0.74,
  "time_horizon_months": 18,
  "first_seen": "2026-03-15",
  "status": "active",
  "evidence": [
    {"url": "...", "headline": "...", "source": "Reuters", "date": "2026-03-15"}
  ]
}
```

`expected_contribution_pct` is what gets summed into `event_adjustment_pct`.

## 6. Decay, dedup, and saturation

**Recency decay.** The contribution of an event decays with age:
```
recency_weight(days_old) = exp(-days_old / 90)   # 90-day half-life ≈ 62 days
```
A 30-day-old event retains 72% weight, 180 days → 14%. For horizon-matched events (e.g., a 12-month-horizon catalyst 6 months in), decay is linear toward the horizon date instead.

**Probability decay.** If the event has a predicted horizon and passes without materialization, probability drops to zero and the event is marked `stale` (still visible, not contributing).

**Saturation caps.** Two layers:
- **Per-event cap:** no single event contributes more than ±10% to target.
- **Total cap:** `event_adjustment_pct` clamped to ±15% regardless of how many events stack. Above that, show but don't apply.

**Dedup.** Headlines about the same event cluster via:
1. Cosine similarity on summary embeddings (>0.85) within a 7-day window
2. Same `(ticker, event_type)` within 30 days merges into the same `event_id`
3. Duplicates boost `evidence[]` and nudge confidence up, but do not add a second magnitude

**Overlap with criteria.** Before summing, check whether any active event semantically overlaps with an already-met or already-failed criterion. If it does, pick whichever has higher confidence and suppress the other — avoids double-counting when a news headline triggers both.

## 7. Integration with existing code

Minimal changes to what already works:

**scout_news.py** — extend the Perplexity prompt to also return a structured `events[]` array (in addition to the current bull/bear sentiment count). The existing composite-score path is unaffected.

**scout_fundamentals.py** — similar extension, targeted at longer-horizon thesis events (market expansion, moat changes, etc.) rather than news-flow events.

**analyst.py** — after the existing `evaluate_criteria(...)` call, run:
```python
events = event_dedup.canonicalize(all_events_for_ticker, prior_events_for_ticker)
reasoned = event_reasoner.reason(events, stock_context)
event_adjustment_pct = event_reasoner.sum_adjustments(reasoned)
```
Then change the final line of the adjusted-target block from:
```python
adjusted_target = round(base_target * (1 + adjusted_pct / 100))
```
to:
```python
adjusted_target = round(base_target * (1 + (criteria_pct + event_pct) / 100))
```

**analysis schema** — add `event_impacts` JSONB column and a new `events` table keyed by `(ticker, event_id)` for persistence across runs.

**dashboard** — on the model page, show the target-adjustment breakdown as two stacks:
- Criteria impacts (existing)
- Event impacts (new) — each event as a row, expandable to show the chain, with a mute toggle

## 8. Phased rollout

**Phase 1 — MVP event extraction + direct impact (week 1-2).**
Goal: events surface in the UI with hard-coded baseline impacts. No chain reasoning yet.
- Extend `scout_news.py` to emit `events[]` with `{type, summary, direction, url, date}`
- Add `event_templates.py` with the table above
- Add a minimal `event_reasoner.py` that just applies the baseline midpoint × `probability=0.5`
- Add `event_impacts` field to `analysis.json`
- Render the event list on the dashboard model page
- Do NOT merge with `adjusted_target` yet — display side-by-side for audit

**Phase 2 — Chain reasoning + confidence (week 3).**
Goal: replace naive midpoints with LLM-reasoned chains.
- Build full `event_reasoner.py` using Claude API
- Implement confidence compounding
- Add recency decay
- Merge `event_adjustment_pct` into `adjusted_target`
- Dashboard shows chain expandable per event

**Phase 3 — Dedup + persistence (week 4).**
Goal: stable event IDs across runs, no double-counting.
- Add `events` table
- Implement semantic dedup via embeddings
- Detect overlap with criteria; suppress duplicates
- Add saturation caps

**Phase 4 — Criteria promotion loop (week 5).**
Goal: recurring events organically grow the criteria list.
- When same `(ticker, event_type)` appears ≥3 times over ≥60 days, propose a permanent criterion
- Dashboard has "Approve / Reject / Edit" UI for proposals
- Approved criteria write back to `stocks.criteria` and take over that event type

**Phase 5 — Calibration & validation (ongoing).**
Goal: know whether our impact templates are accurate.
- Track every event's predicted target move vs. subsequent realized move
- Weekly summary: hit rate, magnitude error, bias by type
- Rolling recalibration of template ranges

## 9. Validation plan

We need a way to tell whether the event model is actually helping. Three mechanisms:

**Backtest.** For the existing 6 stocks, replay past 90 days of news headlines, extract events, and compare our predicted target moves to (a) actual price moves and (b) median analyst target revisions. Target: directional accuracy ≥65% on material events (>3% predicted).

**Ablation.** Run the analyst with and without event adjustments for a month. Flag any run where `|event_adjustment_pct| > 5%` so we can review whether the reasoning was correct. Keep the ablation log for calibration.

**Trigger audit.** Every event flagged `magnitude_pct > 5%` or `confidence < 0.3` produces an audit entry in the dashboard so it can be spot-checked before affecting the composite.

## 10. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| LLM hallucinates magnitudes | High | Templated ranges; LLM picks within range; include reasoning trail |
| Double-count vs existing criteria | High | Semantic overlap check; pick higher-confidence source |
| Stale events drag target | Medium | Hard time decay; invalidate on horizon pass without materialization |
| Same headline in 5 outlets inflates | High | Semantic dedup with 7-day window; boosts confidence not magnitude |
| Adversarial / PR / pump news | Medium | Source quality weighting; skip press releases for magnitude, use only for context |
| Feedback loop (our target up → news → more positive extraction) | Low | Weekly cap on total target movement; diff check |
| Composite score inflation from events + criteria both moving | Medium | Report `adjusted_target` with breakdown; alert on |total_adjustment| > 20% |
| Perplexity / Claude API failures mid-pipeline | Medium | Graceful degradation: fall back to prior-run events with extra decay |

## 11. Open design choices

Three decisions I need your call on before Phase 1 starts:

**A. Magnitude picker — LLM-free or LLM-chosen within range?**
Option 1: LLM picks a number within the template range with a reasoning string.
Option 2: Deterministic midpoint, LLM only classifies.
Default recommendation: Option 1 but with the LLM's reasoning visible so we can audit.

**B. Chain depth — 3 levels or 4?**
3 levels = Event → Operational → Financial → Valuation. Cleaner, compounded confidence degrades less.
4 levels = Event → Operational → Financial ceiling → P&L impact → Valuation. More auditable but noisier (confidence compounds multiplicatively).
Default recommendation: 3 levels; add level-4 optional for complex events.

**C. When to promote an event to a criterion?**
Option 1: Auto-promote after N occurrences + 60 days (user gets notification, not approval gate).
Option 2: Always require explicit approval.
Default recommendation: Option 2 for the first month, switch to Option 1 once we trust the taxonomy.

## 12. Data contracts

For reference, the exact interfaces between components:

**Scout → Analyst (events array):**
```json
{
  "ticker": "LITE",
  "events": [
    {
      "raw_summary": "Lumentum agrees to acquire Ciena's Canadian photonics facility in Montreal",
      "source": "Reuters",
      "url": "https://...",
      "date": "2026-03-15",
      "detected_by": "News"
    }
  ]
}
```

**Reasoner output (per event):**
```json
{
  "event_id": "lite_2026q1_canada_facility",
  "ticker": "LITE",
  "type": "capacity_expansion",
  "summary": "Lumentum acquires Montreal photonics facility",
  "direction": "up",
  "magnitude_pct": 4.0,
  "probability": 0.70,
  "compounded_confidence": 0.264,
  "expected_contribution_pct": 0.74,
  "time_horizon_months": 18,
  "chain": [ ... ],
  "evidence": [ ... ],
  "first_seen": "2026-03-15",
  "last_updated": "2026-04-17",
  "status": "active"
}
```

**Analyst output (addition to `criteria_evaluation`):**
```json
"event_impacts": {
  "events": [ ... ],
  "event_adjustment_pct": 1.2,
  "criteria_adjustment_pct": 10.0,
  "total_adjustment_pct": 11.2,
  "capped_at_saturation": false,
  "computed_at": "2026-04-17T..."
}
```

`adjusted_target` on the dashboard shows: `base × (1 + total_adjustment_pct/100)` with hover-breakdown.

---

Next action: lock the three open choices, then start Phase 1.
