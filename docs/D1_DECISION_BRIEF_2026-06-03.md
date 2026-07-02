# D1 — Archetype-Routed Kill Rule · Decision Brief

**Date:** 2026-06-03 · **For:** Hume
**Status:** Awaiting one decision before build · **Stakes:** changes a live trade gate (conviction + position size)

**The decision in one line:** D1 loosens the "this trade is broken" gate for regime-shift names only. You are choosing *how* to enforce that — **who applies the threshold** (code vs the prompt) and **how far it reaches** (the thesis path now, or also the live Socratic path). The thresholds themselves are already settled.

---

## 1. What the kill rule does today

Every thesis computes `risk_adj_ev_ratio = risk_adj_target / current_price` — the probability-weighted exit price divided by today's price. A fixed table in `prompts/thesis_v3.md` then clamps the trade:

> `risk_adj_ev_ratio < 0.90` → `conviction: BROKEN`, `position_size_pct: 0%` — regardless of how strong the strategic thesis is.

In plain terms: *if the math says your probability-weighted exit is more than ~10% below where you'd buy, the trade is dead.* This rule exists for a real and good reason — the **AXON / COHR / ALAB pattern**: the secular story is correct, but the multiple is already at peak, so the asymmetry is inverted and you shouldn't buy. The gate catches exactly that.

## 2. The problem it now causes

The same uniform 0.90 gate mis-fires on **regime-shift / transformational names**. Those names are valued deliberately conservatively — and as of V2 (shipped this session) they use **DCF-as-a-floor**, which by design produces a cautious `risk_adj_target`. So a genuinely strong regime-shift bet can show a ratio below 0.90 and get stamped `BROKEN` / 0% — not because the trade is bad, but because the math under it is intentionally cautious.

LITE is the live example: a high-conviction AI-photonics regime-shift name that the uniform gate would mark broken on conservative EV math alone. That's a false kill, and it's the motivating case in the backlog (D1's pass criterion is "re-run on LITE and confirm it no longer fires BROKEN").

## 3. The fix

Route the kill threshold by archetype instead of applying one number to everyone:

| Archetype group | Kill threshold | Rationale |
|---|---|---|
| cyclical / garp / compounder / special-situation | **0.90** (unchanged) | The gate works as designed for these. |
| transformational (regime-shift) | **0.60** (wider) | Only kill when the math is *really* bad, not merely conservative. |
| pre-revenue (≈zero TTM revenue) | **gate disabled** | The ratio is meaningless with no revenue/EV anchor. |

These thresholds come straight from the backlog and are **not** part of the open decision — they're settled.

---

## 4. The actual decision — two dials

### Dial 1 — who enforces the threshold?

- **In code (Python post-processor) — recommended.** After the model returns, code re-routes: if a trade was forced `BROKEN` purely by the ratio gate but the archetype's wider threshold isn't breached, relax it; for pre-revenue, skip the gate. Deterministic, unit-testable, and **ungameable**. The changelog already committed to exactly this ("V3.4.3.1 Python post-processor").
- **In the prompt.** Inject the archetype-specific threshold table into the prompt so the model reasons with the right gate. The prose stays coherent, but this is the *same gate already flagged as gameable* (a small probability nudge clears it), and the outcome can't be unit-tested.

### Dial 2 — how far does it reach?

- **Thesis path only (`run_thesis`) — recommended for now.** Low blast radius; it's the older single-model path and doesn't disturb the live opus-4-8 judgment layer we just upgraded.
- **Also the Socratic path.** Apply the same routing to the live Model-B regime judgment. Broader and higher impact (Socratic is the active path), but it must reconcile with Model B's existing regime handling to avoid double-counting — so it belongs in its own deliberate step, not bundled here.

---

## 5. The full option space (for completeness)

The two dials above collapse five concrete implementations:

1. **Python post-processor, thesis only** — *recommended.* Testable, deterministic, low risk.
2. **Parameterize the prompt** — coherent prose, but gameable and untestable.
3. **Post-processor + Socratic** — consistent across both paths, but touches the live layer; higher stakes.
4. **Hybrid (prompt states the rule, code enforces it)** — coherent + guaranteed, but most work and two places to maintain.
5. **Move the clamp fully into Python** (model emits raw inputs; one `apply_kill_gate` is the sole source of truth) — cleanest long-term and removes the gameable prompt gate entirely, but the biggest change and it alters the contract.

## 6. Recommendation

**Build #1 now, in the spirit of #5.** A pure, exhaustively-tested `apply_kill_gate(parsed, archetype)` that is the deterministic source of truth for the ratio clamp, wired into `run_thesis`, thesis-path only. Reasoning:

- The project already decided the gate should be enforced in Python and is ungameable — that rules out the prompt-only route.
- A kill clamp is a **Hard Gate**; by your own filter philosophy it should be a deterministic rule, not model discretion.
- Scoping to the thesis path keeps the blast radius small and leaves the just-upgraded Socratic layer untouched. The Socratic version (#3) is the right *next* step, done deliberately.

## 7. The one subtlety to get right

Coherence. When the post-processor relaxes a `BROKEN`, the model's own prose still argued `BROKEN` under the old 0.90 table — so the override must be annotated in `kill_triggers`, e.g. *"uniform gate said BROKEN at 0.90; routed to LOW for transformational — ratio 0.78 ≥ 0.60 archetype floor."* Otherwise the sealed record contradicts itself. This is handled in the post-processor, not left implicit.

## 8. Validation

The pure `apply_kill_gate` logic gets full unit-test coverage here (every archetype × ratio band, plus the pre-revenue case). The behavioural confirmation is yours: one live Opus thesis run on **LITE**, expected to no longer fire `BROKEN` / 0% — the backlog's stated pass criterion.

## 9. After you decide

If you confirm #1: I build and test `apply_kill_gate`, wire it into `run_thesis` with the annotation, add the unit suite, and write the CHANGELOG entry — then hand you the one-line live-validation command. If you'd rather a different dial setting, the same plan adapts. If you'd rather hold D1, the next move on the track is the Opus cost cap.

---

*Source: `prompts/thesis_v3.md` (kill table, lines ~166–181), `scripts/run_thesis.py` (post-parse hook), `scripts/target_engine.py` (archetype + V2 dcf_role routing), and the D1 entry in `data/todo_master_2026_05_26.md`.*
