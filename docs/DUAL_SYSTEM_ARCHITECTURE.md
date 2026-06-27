# Dual-System Architecture — target design & build sequence

**Owner:** Hume · **Drafted:** 2026-06-27 · **Status:** target architecture (revamp blueprint), build in sequenced steps

This is the organizing design the engine is being refactored toward. It is not a patch list — it names the two reasoning systems, maps them onto what already exists, and decomposes the revamp into atomic, individually-shippable steps. Read this before touching the judgment/valuation path.

---

## 1. The principle

Two distinct modes of thinking, **combined** into the final recommendation:

- **Type A — structural / backward-from-the-future.** Decide how the world works in **5–10 years** (treated as near-*factual* — 20y+ is unpredictable, 5–10y "we have a good idea now"), then reason **backward** to what to own now. Vision-derived ownership, *not* market timing. This is the only legitimate forward input, because it's structural inevitability (AI needs memory; physical AI needs more; compute demand compounds), not a market call.
- **Type B — tactical / respond-to-the-current-market.** You know *what* to own (from A) but **cannot predict the market**. Given current price + what the market is paying attention to, give the best response: buy / accumulate / wait / avoid. No prediction — respond to the present state.
- **Combination.** structural truth (A) × current-market response (B). The output is a *stance* from the 2×2 below; trade asymmetry (`risk_adj_ev_ratio`, `buy_below`) still sets **entry and size within** that stance.

**Facts over prediction.** Market timing is forbidden (the engine already enforces 10-Q actuals, no hand-set targets). The 5–10y structural state is the one place forward reasoning is allowed. Attention is a *current-market fact*, not a prediction.

### The combined verdict (2×2)

```
structural conviction (Type A, 5–10y truth)
        ▲
  HIGH  │  accumulate patiently   │   CONVICTION BUY
        │  (real, not yet noticed) │   (real truth, market waking up)
        │                          │   e.g. MU · SNDK
        ├──────────────────────────┼─────────────────────────
  LOW   │  ignore                  │   momentum trap
        │  (no truth, no traction) │   (attention, no substance — trade/avoid)
        └──────────────────────────┴─────────────────────────►
              LOW                         HIGH
              attention / current-market traction (Type B)
```

---

## 2. Current state — what exists, what's broken

The A/B split **already exists in the code** but runs with Type A's lights off:

| Layer | Today | Problem |
|---|---|---|
| **Type A** structural | `strategic_conviction` (thesis_v3.md) + Model B regime | computed then **discarded** (not persisted on `theses`); Model B has **no framework** for structural supply/demand or secular demand ([model-b-regime-lens-gap]) |
| **Type B** tactical | trade `conviction` + `risk_adj_ev_ratio` clamp | runs **unopposed** → 6/6 watchlist names BROKEN despite all being `strategic_conviction=HIGH` |
| **Attention** | raw signal in social/news/YouTube scouts + wave momentum | **never distilled** into a factor; the x-axis doesn't exist |
| **Discovery** | wide-net quant funnel (`scout_discovery.py`), watchlist-excluded | feeds candidates but doesn't **sort** them by A×B |

Net: a basket of structurally-strong names reads as uniformly "broken" because only Type B is wired, and the value judgment is invisible.

---

## 3. Build sequence

Each step is atomic, individually shippable, and tested. All touch the money/judgment path → **propose, human-approves the commit, no bundling.**

### Step 1 — Surface the structural axis *(foundational, cheapest)*
Persist + expose `strategic_conviction` and `risk_adj_ev_ratio` (already computed; currently dropped from the `theses` row at `run_thesis.py:928`). Migration: `ADD COLUMN IF NOT EXISTS`. Schema-drift-strip means it's safe pre-migration (fields stripped until the column exists, like `kill_gate_override`).
**Acceptance:** every thesis row carries `strategic_conviction` + `risk_adj_ev_ratio`; a verdict reads "strategic HIGH / trade BROKEN / buy below $X" instead of a bare BROKEN. (Dashboard surfacing follows.)

### Step 2 — Attention factor *(the x-axis)*
Distill the existing scouts (social mentions, news volume, relative volume/momentum from `wave_health`) into one `attention_score` per name/sector. Env-gated, additive, persisted alongside the thesis. Pure scoring + guarded data pull.
**Caution (load-bearing):** attention is a momentum signal and the system is built to resist momentum-chasing. It gates **timing / x-position only**, never conviction. Cap its influence.
**Acceptance:** `attention_score` computed for the watchlist; memory names (MU/SNDK) score high given current traction.

### Step 3 — Power up the structural axis *(Model B lens)*
Extend Model B's existing "is this a chokepoint?" self-check into a framework decision-tree: chokepoint / commodity-cyclical supply-demand / secular-inflection — each with numeric discipline (supply-growth vs demand-growth, ASP, content-per-unit × unit-growth). Judgment-prompt change → resets the cohort key, but the calibration clock is ~empty now (no ripe predictions until ~July) = cheapest time.
**Acceptance:** a memory name yields a structural-demand-aware regime verdict; re-run `stability_check` (watch variance vs the P1 self-consistency work).

### Step 4 — Combine into the 2×2 verdict
Deterministic, pure mapping: `(strategic_conviction, attention_score) → quadrant`; `risk_adj_ev_ratio` + `buy_below` set entry/size **within** the stance. Discovery candidates get placed in the grid.
**Acceptance:** the 6 watchlist names + discovery shortlist land in quadrants the data supports (MU/SNDK → conviction-buy); unit-tested mapping.

---

## 4. Guardrails & risks

- **Discipline preserved:** the trade-asymmetry gate (`risk_adj_ev_ratio`/`buy_below`) is **not** relaxed — it governs entry/size within the structural stance, so you never overpay even on a real truth.
- **Anti-momentum:** attention never upgrades a weak structural thesis. Structural-low + attention-high = *momentum trap*, explicitly to be avoided/traded, not owned.
- **Variance:** the Model B lens (Step 3) may raise verdict variance — tension with P1 self-consistency; re-run `stability_check.py --price` for a clean A/B.
- **Cohort reset:** editing `model_b_regime.md` (Step 3) resets the calibration clock — cheap now, expensive once calibration data accrues.
- **Money-path:** `run_thesis.py`, `finance_data.py`, `target_engine.py`, `model_b_regime.md` changes are propose → human-approve; never auto-committed.

See also: [model-b-regime-lens-gap], [dual-system-investing-philosophy], [hume-memory-sector-bull-thesis] in memory; `CHANGELOG.md` for per-change history.
