# C1 Cycle Report — DCF Role Contextual Routing (v1)

**Date:** 2026-05-26
**Status:** SHIPPED + VALIDATED
**Workflow:** 7-step per `feedback_change_workflow`
**Iterations:** 2 (squad cycle found 3 fixes; validation iter 1 surfaced cyclical-routing block; iter 2 unblocked via `--archetype` override and PASSED)

---

## Preamble: what changed and why

**The 25-day debt:** Hume's 2026-05-01 architectural decision (`user_dcf_is_wrong_primary`) called for repositioning forward DCF from primary to downside-floor for regime-shift candidates. The reasoning: Gordon Growth's ≤4.5% terminal perpetuity cap structurally undershoots 10x setups (trough / regime / compression / re-rating dynamics). Memory captured the call; code never followed. Auto mode continued producing DCF-primary targets that systematically undershot LITE-like names.

**Surface case for this cycle:** Socratic id=21 (2026-05-25) used §7b future-pricing math to produce LITE target_low $570 / target_high $1,280 conditional. Pure-DCF fair value at moat-collapse: $290-$350. Auto mode on LITE would produce something near the pure-DCF figure as PRIMARY and V3.4.3 kill rule would fire BROKEN. Two engine modes architecturally disagreed on the same stock. C1 closes that gap.

**Approach:** introduce `dcf_role` field on `ScenarioResult` with two values (`primary` default, `downside_floor` flag-activated). When role is `downside_floor`, exit multiples drive `terminal_ev` and Gordon Growth is kept as a floor reference for display. Default behavior on all existing callers unchanged (they don't pass `dcf_role` → get "primary" → zero regression). Flag-gated activation via `scripts/test_dcf_floor.py --dcf-as-floor`. V2 wires into production paths after V1 validates.

---

## Iter 1: Initial application + review squad

### Step 1: Apply

`scripts/target_engine.py` — 8 surgical edits:
1. `ScenarioResult` dataclass +3 fields (`dcf_role`, `dcf_floor_terminal_ev`, `dcf_floor_price`)
2. `_scenario_price` signature +1 param (`dcf_role: str = "primary"`)
3. Blending logic branched on `dcf_role` (lines 1517-1607)
4. `dcf_floor_price` computation block (lines 1632-1636)
5. `ScenarioResult` return statement includes new fields
6. `build_target` signature +1 param (`dcf_role: str = "primary"`)
7. Two internal `_scenario_price` call sites pass `dcf_role` through
8. P/S blend `ScenarioResult` reconstruction carries new fields

`scripts/test_dcf_floor.py` — new file, V1 validation CLI:
- argparse with `tickers` positional + `--dcf-as-floor` flag
- single-stock dry-run wrapping `build_target(fin, dcf_role=...)`
- LITE-specific pass criterion check at end

File deltas: target_engine.py +3,460 bytes (153,519 → 156,979). test_dcf_floor.py new at ~4.7KB.

### Step 2-3: Self-review

Pass: default-path preservation confirmed; `elif gordon_ev > 0` preserves original `if gordon_ev > 0` branch behavior exactly. Branching covers 4 edge cases (both exit mults / one / Gordon fallback / nothing). Floor storage gated on Gordon being present AND different from terminal. ast.parse OK. Signatures intact via Python introspection (`build_target` sig contains `dcf_role`; `ScenarioResult.__dataclass_fields__` contains 3 new fields with correct defaults).

Two minor surprises flagged in step 3 for the cycle report:
- Pre-revenue stocks (negative FCF/EBITDA) silently fall back to Gordon-as-primary in `downside_floor` mode. V1 conservative behavior. Model D / `reference_only` role is the real fix for that asset class.
- Print noise (6 stderr lines per run with flag). Acceptable for verification.

### Step 4: Review squad

Invoked `review-squad:critic` and `review-squad:red-team` in parallel.

**Critic findings:**

1. **Pass criterion unfalsifiable.** `target_high >= $580` could be met by coincidentally inflated exit multiples without proving the routing logic is correct. The test couldn't distinguish "exit multiples capture regime shift correctly" from "exit multiples happen to be high right now."
2. **`terminal_ev != gordon_ev` float-equality guard.** Worked for direct-assignment identity match but was a latent defect — would break on numerical equality with sub-cent floating-point drift.
3. **Architectural claim asserted, not implemented.** The flag swaps Gordon's perpetuity cap for peer-multiple mean-reversion. Code does nothing to make exit multiples regime-aware. (Same point Hume already flagged pre-application as "comp selection is the next seam to watch" — documented as a deferred concern.)

**Red-team findings:**

1. **Gordon-fallback silently produces `dcf_floor_terminal_ev=None` while Gordon drives the primary.** When both exit multiples are non-positive in `downside_floor` mode, the code falls back to `terminal_ev = gordon_ev`. The floor check `terminal_ev != gordon_ev` evaluates False (object identity), so floor stays None. Result: `dcf_role="downside_floor"` returned with `dcf_floor_terminal_ev=None` — a contradictory state where the field describes what was REQUESTED, not what HAPPENED.
2. **Stale or sector-mismatched exit multiples** can inflate the average; pass criterion as written can't detect inflation-driven success vs structural success. (Same as critic #1.)
3. **PS-blend reconstruction copies `dcf_floor_price` from ev_result without recalculating** for blended_price. Could produce `dcf_floor_price > blended_price` — logically inverted "floor."
4. **(Hidden) Archetype-horizon Gordon calibration inconsistency.** Pre-existing flaw; the new field merely makes it visible. Cycle-report note only.

### Step 5-6: Triage and loop

3 sound findings, 0 nonsense (no proposals were skippable). Applied 3 fixes in one iteration:

- **Fix #1** (`test_dcf_floor.py`): replaced single-check pass criterion with 5 path-dependent checks: target_high >= $580 AND dcf_role on upside+base is "downside_floor" AND dcf_floor_price is populated AND floor < target_high AND gap ratio >= 1.5x.
- **Fix #2** (`target_engine.py`): added `gordon_fallback_fired` boolean tracking; returned `effective_dcf_role = "primary" if gordon_fallback_fired else dcf_role`. Replaced float-equality control flow with boolean flag. Field now describes ACTUAL driver, not request.
- **Fix #3** (`target_engine.py`): in PS-blend reconstruction, gated `dcf_floor_price = None` when `ev_result.dcf_floor_price >= blended_price`. Floor framing doesn't apply cleanly in the blend zone.

ast.parse OK both files. Signatures still intact.

---

## Iter 2: Validation run (LITE with `--dcf-as-floor`)

### Step 1 (this iter): Run command

```bash
python scripts/test_dcf_floor.py LITE --dcf-as-floor
```

**Output highlight:**
```
[routing] LITE: early auto-promote to cyclical (archetype=None, CV=24.16>0.50;
  2 sign-changes in margin trajectory; prior negative-margin year)
```

**Result:** ALL 5 CHECKS FAIL. target_high $202 vs spot $911. All scenarios show `dcf_role: primary`.

### Diagnosis

Two distinct issues uncovered that self-review + squad cycle BOTH missed:

**Issue A — LITE mis-routed to cyclical.** The archetype auto-promote heuristic detected cyclical signals (CV>0.50, margin sign-changes, prior negative-margin year) from LITE's pre-2024 data — the 2018-2023 cyclical optical components era + the 2022-2023 correction. The heuristic's signal IS in the data, but the data is from a previous business regime that has been structurally superseded by AI demand. The auto-promoter applied historical pattern to a fundamentally changed business.

**Issue B — dcf_role doesn't reach `_scenario_price_normalized`.** Cyclical mode uses a separate scenario function I did not modify. The flag was silently ignored along this path. Self-review focused on `_scenario_price` only; squad cycle examined PS-blend path but not normalized path.

### Step 5 (decision): Path forward

Discussed 4 options with Hume. He chose **C** (do A first, then B in separate cycle, queue D for archetype auto-promote audit).

Hume's reinforcing reasoning: "The goal of C1 is to validate dcf_role math. LITE being misrouted to cyclical is a DIFFERENT bug that BLOCKS validation of the FIRST bug's fix. Option A unblocks validation with 10 lines. You need to see the dcf_role math produce correct output on a secular path before you can trust it on ANY path."

Saved a meta-memory (`feedback_regime_shift_vs_historical_math`) capturing the observation: DCF, V3.4.3 kill rule, and archetype auto-promote are all Category-2-acting-like-Category-1 filters that apply historical math to current-but-changed businesses. Same pattern, three different sites in the codebase. Per filter philosophy, each needs a contextual routing fix with operator override. Per `feedback_one_step_falsifiable`, they get fixed independently, not bundled.

### Step 1 (re-apply with fix A): `--archetype` override

`scripts/test_dcf_floor.py` +10 lines:
- `run_one()` signature gains `archetype: str | None = None`
- `build_target(fin, dcf_role=dcf_role, archetype=archetype)` passes through
- argparse adds `--archetype` flag with help text citing `regime-shift-vs-historical-math` memory

### Steps 2-3 (iter 2 self-review)

Trivial change, light loop per workflow boundary. ast.parse OK. Flag visible in `--help` output.

### Step 5 (iter 2 validation)

```bash
python scripts/test_dcf_floor.py LITE --dcf-as-floor --archetype=secular_growth
```

**Output:** ALL 5 CHECKS PASS.

```
target_high $1,121.22 >= $580 ........................ ✓
dcf_role='downside_floor' on upside+base ............. ✓
upside.dcf_floor_price populated ($146.78) ........... ✓
floor < target_high .................................. ✓
target_high / floor = 7.64x >= 1.5x .................. ✓  (gap real)
```

Engine target band: $399 / $855 / $1,121.
Socratic id=21 target band: $570 / ~$925 / $1,280 conditional.
**Two engine paths now AGREE on LITE.**

Routing line confirms LITE hit P/S BLEND zone (score 0.35) — which exercised the PS-blend dcf_floor_price guard (red-team finding #3) in production. Output coherent; no floor inversion.

---

## Final diff summary

**Files changed:**
- `scripts/target_engine.py` (+3,460 bytes, 153,519 → 156,979): 8 edits + 3 squad-cycle fixes = 11 total surgical edits. Backwards-compatible (default `dcf_role="primary"` → zero regression on existing callers).
- `scripts/test_dcf_floor.py` (new, ~7.3KB): V1 validation CLI with `--dcf-as-floor` and `--archetype` flags.

**Memory files:**
- `feedback_regime_shift_vs_historical_math` (new): unifying observation across DCF, kill rule, archetype auto-promote.
- `MEMORY.md` updated with new index entry.

**Files unchanged (deliberately):**
- `analyst.py`, `model_export.py`, `target_api.py`, `verify_model.py`, etc. → V1 doesn't touch production paths. V2 wires `dcf_role` into these.
- `_scenario_price_revenue_multiple` (P/S mode): doesn't use Gordon, flag is naturally a no-op there.
- `_scenario_price_normalized` (cyclical mode): KNOWN GAP. Wiring `dcf_role` here is task **B** in the queue (next sub-cycle of C1).

---

## Implications

1. **Auto-vs-Socratic divergence on LITE is closed.** With `--dcf-as-floor --archetype=secular_growth`, Auto produces $399/$855/$1,121; Socratic id=21 produced $570/~$925/$1,280. Same direction, comparable magnitudes. The two engine modes now answer the same question for the same stock.

2. **The 25-day debt is settled.** Hume's 2026-05-01 architectural call is implemented behind a flag. V2 makes it config-routed via archetype tagging.

3. **V3.4.3 kill rule (D1 in deferred queue) is now actionable.** The kill rule fires on `risk_adj_ev_ratio < 0.90` computed from DCF-derived targets. With DCF demoted, the ratio's denominator changes. Need to re-run V3.4.3 logic with new target — expected to STOP firing BROKEN on regime-shift candidates like LITE.

4. **Comp-selection is now the load-bearing assumption.** With Gordon demoted, exit multiples drive `terminal_ev`. The peer-comp selection that produces `ev_ebitda_multiple` and `ev_fcf_sbc_multiple` becomes the next seam to audit. Hume flagged this pre-application; reviewers also flagged it. Documented as a Tier 2 follow-up after D1/D2.

5. **Archetype auto-promote heuristic is on the audit list.** The cyclical mis-routing of LITE is the same architectural failure mode as DCF undershooting. Will be tackled as its own cycle (queue item D in the master to-do) once D1 (kill rule re-keying) and D2 (EDGAR rewrite) land.

---

## Surprises

1. **Cyclical auto-promote on LITE was a complete blind spot.** Self-review focused on `_scenario_price`; squad cycle focused on PS-blend; neither examined the cyclical scenario function (`_scenario_price_normalized`). Iter 1 validation surfaced this in one run. The 7-step workflow's validation step is what catches what static review misses. Documented as a meta-lesson: future audits should explicitly enumerate ALL scenario functions when reviewing engine changes.

2. **The three failure modes (DCF perpetuity / kill rule / archetype heuristic) are the same bug.** Hume named the unifying pattern during iter 1 → iter 2 transition: "historical math applied to a fundamentally changed business." Three independent filters expressing the same flaw. Saved as `feedback_regime_shift_vs_historical_math` for future audits to use as diagnostic.

3. **P/S blend zone was unexpectedly hit on LITE.** Iter 2's routing message `BLEND mode — routing score 0.35` means red-team finding #3 (PS-blend dcf_floor_price carry-through) wasn't theoretical — it was triggered on the first real validation run. The fix worked: no floor inversion, output coherent. The squad cycle was real value, not paranoid.

4. **Gordon-floor per scenario varies 3.3x.** Downside $45, base $124, upside $146. The "floor" framing is per-scenario, not portfolio-level. Downside-scenario Gordon is the most pessimistic interpretation of pure-DCF math. For position management UX, the question is which Gordon to display — answer is probably "show all three" with explicit scenario labels.

5. **Engine target_high $1,121 vs Socratic id=21 $1,280 is closer than expected.** I would have predicted a wider gap; the engine's 5-year forecast vs Socratic's 3-year horizon should have introduced more divergence. The independent convergence at ~$1.1-1.3K suggests the math is more robust to forecast-horizon choice than I feared.

---

## Status of follow-ups

**Open (queued):**

- **B** — wire `dcf_role` through `_scenario_price_normalized` (cyclical scenario function). Estimated ~50 lines, separate small cycle. Pass criterion: re-run LITE with `--dcf-as-floor` but WITHOUT `--archetype` override; expect cyclical mode to respect the flag and produce a higher target than iter 1's $202.
- **D1** — V3.4.3 kill rule audit against current LITE inputs with new dcf_role-aware target. Quick check: does the kill rule still fire BROKEN on LITE now? Per filter philosophy, eventual fix is archetype-keyed threshold.
- **D2** — EDGAR validation rewrite (Module 1 split: EDGAR hard / trajectory informational).
- **Archetype auto-promote audit** (deferred per master to-do as the third instance of the regime-shift-vs-historical-math pattern). Needs its own cycle.

**Closed:**

- C1 (this cycle): DCF role contextual routing v1 — shipped behind flag, validated on LITE.

---

## Pre-conditions for V2 (when ready)

To move from V1 (flag-gated, per-run) to V2 (config-routed):
1. Add `dcf_role` field to `config/ticker_archetype_overrides.json` schema (NOT `ticker_archetypes.json` — they're different files with different vocabularies).
2. Default per-archetype: cyclical → "primary"; secular_growth / transformational / regime_shift → "downside_floor"; pre_revenue / early_revenue_ramp → "reference_only" (after Model D ships).
3. `build_target` reads `dcf_role` from config when `archetype` is set and no explicit `dcf_role` is passed.
4. Validation: run V2 across full watchlist; spot-check 5+ stocks where V1 + Socratic agree.

Do NOT ship V2 until D1 (kill rule audit) closes. B (cyclical-path wiring) was investigated and skipped — cyclical mode uses normalized EBIT × through-cycle multiple, not Gordon Growth, so there's no DCF to demote on that path. D-v1 (the archetype override loader, see addendum below) is the right fix for the LITE-as-cyclical case.

---

## D-v1 addendum (same-session continuation, 2026-05-26)

After the C1 cycle closed, investigation of "B" (wire `dcf_role` through `_scenario_price_normalized`) revealed that the cyclical scenario function doesn't use Gordon Growth at all — its terminal value is `terminal_ebit × ev_ebit_mult` (already an exit-multiple approach). There was no DCF role to demote on that path. B as originally scoped was a no-op.

The actual LITE-as-cyclical bug was elsewhere: `config/ticker_archetype_overrides.json` had explicitly tagged LITE as "transformational" since 2026-05-11 (to address this exact regime-shift failure mode), but **no engine-side loader was ever built** to consume the config. The file's own README claimed it was loaded via `_load_archetype_override(ticker)` — but that function didn't exist. Only `analyst.py` consulted archetype state, via Supabase. Other callers passed `archetype=None`, triggering the cyclical auto-promote heuristic that we'd hit in iter 1.

### D-v1 surgical fix

`scripts/target_engine.py` — 2 edits:

1. Added module-level helper `_load_archetype_override(ticker)` reading `config/ticker_archetype_overrides.json`. Module-level cache, underscore-prefix key filtering, case-insensitive lookup, graceful FileNotFoundError handling.

2. `build_target` consults the override when `archetype is None`. Stdout logs `[target_engine] {TICKER}: archetype override loaded from config: '{archetype}'` when fired.

### D-v1 validation

`python scripts/test_dcf_floor.py LITE --dcf-as-floor` (no `--archetype` override):

- New line: `[target_engine] LITE: archetype override loaded from config: 'transformational'` ✓
- `[routing] LITE: early auto-promote to cyclical` did NOT appear (override suppressed it) ✓
- All 5 pass criterion checks ✓
- target_high $1,501.37, target_base $1,126.85, target_low $508.02 (using transformational archetype's 7-year Y4-exit horizon)
- Gordon floor refs: $65/$186/$226 across scenarios
- Gap ratio 6.64x

The C1 + D-v1 combination closes the regime-shift failure mode for any LITE-equivalent stock that's been operator-tagged in the override config. Without C1, the dcf_role flag wouldn't exist. Without D-v1, the override wouldn't load. Both are required.

### Behavior change for other build_target callers

`verify_model.py`, `model_export.py`, and any other caller that passes `build_target(fin)` without archetype will now load from the override config. For LITE and AMD specifically (the 2 currently-tagged tickers), those callers will now route through "transformational" archetype. This is the INTENDED fix — the override existed to address the regime-shift failure mode but had no engine-side consumer until today.

### Numerical surprise to flag

Transformational archetype produces target_high $1,501 — materially HIGHER than iter 2's secular_growth $1,121 and Socratic id=21's conditional $1,280. The transformational archetype uses 7-year forecast horizon + Y4 exit + bull-tail-tilted scenarios (per the config README). Whether this is "right" or "overshooting" is a separate question — Auto mode now disagrees with Socratic in the OPPOSITE direction from where they started (Auto bullish, Socratic bearish). Not a foundation issue but worth a sanity check before deploying V2.

### D-v1 deltas

- `scripts/target_engine.py`: 161,757 bytes (was 158,688 after C1) — D-v1 added ~3,069 bytes for the helper + hook.
- No other files touched.
- ast.parse OK. Smoke test confirmed override loader returns "transformational" for LITE/AMD, None for untagged tickers.

### D-v1 is part of the same cycle

D-v1 closes the same architectural failure mode as C1 (regime-shift candidates getting wrong-regime math). C1 fixed the DCF-vs-exit-multiple seam; D-v1 fixed the archetype-routing seam. Both are required for LITE to produce sensible Auto-mode output. The squad cycle, validation iterations, and meta-memory (`feedback_regime_shift_vs_historical_math`) all apply across both.
