# Decision memo — single source of truth for targets & conviction

**Status: AWAITING OWNER DECISION** · drafted 2026-07-02 (consolidation sprint 4.2)

## The problem

Three independently-computed target numbers are persisted per ticker, with no
precedence rule and no reconciliation. The audit found LITE simultaneously
showing thesis BROKEN/$581 in the dashboard header and a ~$1,100+ legacy blend
on the model page; Ask AI answers "should I buy?" from the oldest of the three.

| # | Number | Producer | Refresh | Who reads it today |
|---|--------|----------|---------|--------------------|
| 1 | `stocks.target_price` (+ scenarios, model_defaults, thesis/kill text) | `generate_model.py` — Opus, base scenario | 2× daily via scheduled rebuild | Ask AI (`/api/ask` — its ONLY source), model-page fallback, discovery promote |
| 2 | `analysis.event_impacts.final_target` | `analyst.py` → engine base + criteria% + event% blend (`merge_enabled=True`, "authoritative") | 2× daily | Model page event panel / implied-target delta |
| 3 | `theses.thesis_target` / `risk_adj_target` / conviction | `run_thesis.py` — Opus + web search + engine floor + kill/trade gates | Manual / per-run | **Dashboard headline** (StockRow, ThesisHeader), outcomes seeding |

Aggravations: #1's twice-daily regeneration **overwrites operator-edited
thesis/kill-condition text**; #2 inherited the (now fixed) broken event decay
for months; #3 is the only one that passes through the kill gate and the new
code-enforced trade gate — i.e., the only *disciplined* number.

## Options

**A. Thesis-as-truth, demote the legacy generators (RECOMMENDED).**
- `theses.*` is the verdict of record everywhere: dashboard (already), model
  page headline, **Ask AI repointed to theses + live engine payload**.
- `generate_model.py` leaves the 2×-daily schedule → on-demand only (new
  ticker, operator button). Its scenario JSON stays for the slider UI.
  It stops overwriting `thesis`/`kill_condition` text (operator-owned fields).
- `analysis.final_target` becomes a display-only "signal blend" panel, no
  longer labeled authoritative.
- Consequences: single verdict everywhere; ends ~2×6 Opus generations/day
  (the largest recurring spend); stocks.scenarios can go stale between
  on-demand runs (acceptable — sliders re-derive from the live engine payload);
  requires a ~1-day wiring pass (Ask AI context builder, generate_model upsert
  field list, analyst-rebuild workflow note).

**B. Keep all three, add precedence + a disagreement badge.**
- Rule: theses > engine payload > analysis blend > stocks; UI shows an amber
  "sources disagree N%" badge when |#1−#3|/#3 > 15%.
- Cheapest (half-day), no behavior retired — but the spend, the overwrite
  problem, and Ask AI's stale source all persist. A patch, not a fix.

**C. Single verdict service.**
- One writer produces one `verdicts` row per run (engine + events + thesis +
  gates), everything else reads it. Cleanest end state, ~1 week, and touches
  every consumer — wrong moment mid-pivot; revisit after dual-system Step 4
  defines the 2×2 verdict shape (it may BE this service).

## Recommendation

**A now, C later.** A kills the active harms (spend, overwrites, Ask AI's
wrong buy verdicts) with modest work; C is the natural home for the 2×2
verdict when Step 4 lands. If A is approved, the implementation order is:
(1) stop generate_model overwriting operator text, (2) repoint Ask AI,
(3) unschedule generate_model, (4) relabel the analysis blend panel.
