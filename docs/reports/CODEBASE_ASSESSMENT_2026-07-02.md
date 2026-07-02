# Stock Radar — Comprehensive Codebase Assessment

**Date:** 2026-07-02
**Scope:** Full repository — strategy docs, valuation engine, financial data layer, Socratic judgment system, thesis/money path, legacy pipeline & scouts, discovery, frontend/API, infra/QA.
**Method:** 9 parallel subsystem deep-reads; every high/critical claim adversarially re-verified against the actual code (49 verifications: 36 confirmed, 13 confirmed-with-corrections, 0 refuted); empirical checks (test suite run, bug reproductions executed against engine code, git history inspection).

---

## 1. Executive summary

The direction is right and the engineering culture is genuinely unusual in its honesty — but the system has been **building new layers faster than it wires, verifies, and retires the old ones**, and that gap is now where the risk lives.

Five headline conclusions:

1. **The strategic pivot (dual-system Type A/B) is the correct diagnosis** of the 6/6-BROKEN failure, and the docs behind it (DUAL_SYSTEM_ARCHITECTURE.md, TEN_X_PROBLEM_DEFINITION.md) are sharp. But Step 1 is **not fixed end-to-end** — the structural axis is persisted-in-code only (migrations unapplied, zero consumers, invisible in UI), and the two newest frameworks (dual-system 2×2 vs 10× gated cascade) overlap heavily with no doc saying which supersedes which.

2. **The 2026-06-27 QA verdict "the running engine is sound" is wrong.** Two confirmed, numerically-reproduced correctness bugs sit in the engine's money path: an archetype/discount-year mismatch that inflates compounder/transformational targets ~19–28%+ (measured +19.5% on a stub), and a P/S-mode net-debt double-count worth exactly |net_debt|/share (measured +27% on a cash-rich stub). Both sit precisely in the paths the offline test suite doesn't cover.

3. **The single most important architectural gap:** `risk_adj_ev_ratio` — the number that clamps a thesis to BROKEN and that the kill gate keys on — is **emitted by the LLM and never recomputed in code**, even though both operands (risk_adj_target, spot) are in hand at the call site. The "HARD GATE" is prompt prose; code only ever relaxes it upward.

4. **The calibration/feedback loop — the system's entire epistemic backbone — is being poisoned right now**, days before the first T+30 grades ripen (early July, i.e., this week). The legacy pipeline logs all-zero prediction rows (it reads a `target_price` key that doesn't exist in the analyst output), the grader has no source filter so those junk rows get graded alongside real Socratic seals, the prediction_logger has an off-by-one that loses *entire rows* while the checkpoint_seal migration is unapplied, and the July-1 `_dbg.py`/`_fb.py`/`_g.py` commit shows corrupt seals are already being probed — undocumented, against the project's own changelog rule.

5. **Operations are split-brain.** Scheduled GitHub Actions run `origin/main` (2026-05-30, pre-EDGAR-fix) while all June money-path work lives only on the session branch; `run_pipeline` exits 0 on failure so Actions stay green regardless; no CI runs pytest; the pre-commit hook exists on one machine only; the cron layer hardcodes another machine's paths. Meanwhile several safety nets documented as active are dead (verify_model Excel parity, target-swing circuit breakers, schema validator blind to every drifting table, kill-condition eval failing open to "safe").

**The right next move is the one the project already named on 2026-06-27 — "settle before building further" — but applied for real this time:** a consolidation sprint (fix the confirmed math bugs, enforce the gate in code, apply migrations, un-poison calibration before grades ripen, unify deployment) before Steps 2–4 of the dual-system or any 10× build-out.

---

## 2. Direction — where the project is going, and whether it holds together

### 2.1 The evolution has been coherent and failure-driven

Four pivots, each triggered by an observed, documented failure — not fashion:

| Era | Trigger | Response |
|---|---|---|
| Apr 2026 | — | Original scouts → analyst → DCF pipeline ("Auto Mode") |
| May 2026 | Auto produced a useless "BROKEN $878" on LITE | Socratic layer: Models A/B/C + corpus callosum, judgment card, macro/wave context, operator notes, anti-sycophancy rules |
| Jun 2026 | Measured 60% Model-B verdict reproducibility; MU/SNDK false rejects | Rigor arc: checkpoint seal + grader, EDGAR hard gate, archetype-routed kill gate (D1), Model D vision lens, stability harness, mode-of-N consensus (P1) |
| Late Jun 2026 | 6/6 watchlist BROKEN sweep — including RDDT at +18% engine upside and strategic HIGH | Dual-system blueprint (Type A structural × Type B tactical, 2×2 verdict) + 10× problem definition |

This is a healthy pattern. The changelog records wrong hypotheses and retracts them (the MU "corrupted feeds" theory, the Model D "inverted bracket" — more on that below), which is rare discipline.

### 2.2 But the strategic layer is currently in an unresolved superposition

- **Two live frameworks, unreconciled.** DUAL_SYSTEM_ARCHITECTURE.md (06-27) prescribes a 4-step build sequence (attention factor → Model B lens → 2×2 verdict). TEN_X_PROBLEM_DEFINITION.md (06-28, one day later) re-decomposes the same territory into six pieces with a *gated cascade* ("combine conditionally, not averaged") and explicitly recommends **hand-validating on memory/HBM before building anything**. The 10× doc's B1/B2 duplicate the dual-system's phase-modulator and attention factor. No document says which governs. A build session picking "dual-system Step 2" could spend weeks on an axis the newer doc has already re-cut.
- **No authoritative roadmap exists.** `docs/ROADMAP.md` is referenced by CLAUDE.md:253 and README.md:230 but does not exist. BUILD_PLAN_v2.md / CLEANUP_v2.md / PHASE_0_RUNBOOK.md, referenced in the changelog, were never committed. The backlog is fragmented across a stale May todo, HANDOFF_PRD (P4/P5 still open), and the two strategy docs.
- **Step 1 of the dual-system is code-complete but operationally inert.** `strategic_conviction`/`risk_adj_ev_ratio` are added to the theses row (run_thesis.py:936-937) but: (a) the migration is unapplied so the columns are stripped at write time (loudly, to stderr — but the data is still lost); (b) grep across all `**/*.{ts,tsx}` finds **zero** frontend references — `lib/data.ts` THESIS_FIELDS explicitly enumerates thesis columns and omits all four new fields, so even post-migration the dashboard *cannot* show them; (c) no grader or outcome-seeder consumes them. The exact 6/6-BROKEN misread the fix was built for would recur today, pixel for pixel.

**Assessment:** the *thinking* is ahead of the *system*. That's fine — as long as the next unit of work is reconciliation and wiring, not a fifth layer.

### 2.3 The two 10× loops — 0→1 and 1→100 — and what each demands of the system

TEN_X_PROBLEM_DEFINITION.md's core insight is that a 10× is produced by one of **two different self-reinforcing loops**, and they are not variants of one thing — they have different physics, different observables, different valuation lenses, different failure modes, and different sizing rules. The engine today speaks only the language of the second one, and only its *value* half.

#### The 0→1 loop: fuel → ignition → flywheel → new curve

The company holds a **latent capability ("fuel")** — something it is *building* that the future will require — before that capability produces earnings. The loop, when it works:

1. **Fuel accumulates** (capability, capacity, ecosystem position) — visible only in the *activity record* (A1): what they build, ship, invest in; who adopts; who partners. **Doing, not announcing** — a binding design win or PO is fuel evidence; an MOU/LOI is slideware.
2. **Ignition** — the fuel catches a demand curve that didn't exist before (or existed only latently). The leading, factual signal is **deal flow**: design wins, customer commitments, capacity reservations — not earnings, which are lagging and already priced by the time they confirm.
3. **The flywheel turns** — the defining test of the big prize. A true flywheel is **user/adoption count that compounds on its own** (each turn improves the product/ecosystem/data position, which pulls the next cohort in), *not bought growth* — paid acquisition does not compound. A turning flywheel is what separates the ~**100× class** from the ~**10× one-shot** (a single product cycle that ignites once and doesn't self-reinforce).
4. **A new curve emerges** — the crucial phrase in the doc is "**a new curve, not faster old growth**." The business's future is not an extrapolation of its past; that is exactly why earnings/valuation cannot see it, and why the engine labels real 0→1 setups BROKEN.

Properties of this loop: it is **invisible to the P&L until after ignition** (pre-ignition the numbers look terrible, and any fair-pricing lens says avoid); the prize is huge but the base rate is low, so the play is **small, asymmetric sizing**, accumulated early while attention is low, with the exit tied to phase/runway, not to a price target. Sourcing can't be screened for — financial screens structurally miss it (the doc's "the vision is the funnel": derive the capabilities a 5–10y world requires, inventory who is *already building* them). Anti-loophole guards: real fuel ≠ slideware; the flywheel must actually be turning; a model asked "how big can this get" will inflate, so the downside scenario must be *forced* (which is exactly what Model D's parser does — probabilities must sum to 1 with a mandatory failure case).

**What exists in code for this loop today:** Model D (vision scenarios → optionality PV) is the only 0→1-native instrument, and it's wired, gated to transformational names, and parser-disciplined — but its bracket compares frames incompatibly (§3.2) and only LITE is tagged transformational. The kill gate has a `pre_revenue` carve-out (with a fail-open edge, §4.2). Nothing implements A1 (activity record), A2 (fuel/flywheel classification), or ignition detection (B1). Most tellingly, **the discovery funnel's hard filters — revenue growth >15%, gross margin >30% — structurally exclude 0→1 candidates**, i.e., the intake contradicts the framework outright: ACHR/RKLB-class names on the owner's own watchlist could not pass the system's own screen.

#### The 1→100 loop: demand wave → bottleneck → pricing power → capex response → bottleneck migration

Here the curve already exists — a demand wave is underway (AI compute demand compounding) — and the 10× comes from owning the **chokepoint** the wave must pass through. The loop:

1. **Demand compounds** along a chain (compute → memory → optical → custom silicon → packaging → power — the analyst panel's 7 nodes are literally this chain).
2. **Capacity at the chokepoint lags** — supply growth < demand growth is the measurable trigger. This is arithmetic, not narrative: supply-growth vs demand-growth, ASP trajectory, content-per-unit × unit growth (exactly the numeric discipline the dual-system doc's Step 3 prescribes for the Model B lens).
3. **Pricing power emerges** — the bottleneck owner takes price; margins expand; earnings surprise repeatedly to the upside (the "genuine memory supercycle" the EDGAR investigation confirmed for MU/SNDK is this step, live).
4. **Capex responds** — high returns pull investment into capacity; LTAs and capacity reservations (deal flow again) confirm the wheel is turning and also start the clock on step 5.
5. **The bottleneck dissolves or migrates** — supply catches up, pricing power expires, and the chokepoint moves down the chain (the doc's own sequence: GPU → HBM → packaging → power). This is why the loop is cyclical at long horizon and why "durability" is a facet of the bottleneck question, not a separate axis.

Properties: this loop **is legible to earnings and valuation** — B3 (the engine) is the right value gate for it, provided cyclical discipline (normalized EBIT, not peak-multiple-on-peak-earnings). The prize is bounded ("value capture," not a new curve) but the probability is higher, so sizing is **larger**, with one hard correlation rule: names on the same wave are **one bet** (MU + SNDK is one memory bet, not two ideas). Timing: the runway gate — is there demand runway left, is the bottleneck about to dissolve — and the phase modulator (ride-with-exit in early/mid euphoria, sit out in late). The characteristic failure modes are symmetric: mistaking a commodity for a bottleneck (no pricing power → you own a cyclical at the top), and holding through bottleneck migration (the moat evaporates on schedule).

**What exists in code for this loop today:** more than for 0→1, but none of it routes. The cyclical valuation mode (normalized-EBIT, trimmed-mean margins, structural-break windows) is the right value gate; the analyst panel's [CHAIN] clocks are a real, deterministic implementation of steps 1–2 awareness; the EDGAR fix un-blinded the data layer to the supercycle. But the memory names carry no archetype tags (§4.2), so cyclical routing and kill-gate interpretation never fire for them; the demand-cycle vs price-cycle separation the doc demands ("the engine fused these into 'late-cycle' and got it wrong") is not yet implemented; and the attention factor and 2×2 that would place MU/SNDK in the CONVICTION BUY quadrant are unbuilt.

#### How the two loops relate — and the one cascade that serves both

The loops are connected in sequence: **a 0→1 winner's new curve becomes the demand wave that creates the next 1→100 bottlenecks in its own supply chain** (AI models were the 0→1; HBM/optical/power are the resulting 1→100s). That is why the doc computes sector/chain facts once and shares them, and why the same gated cascade covers both modes with a single branch at the structural gate:

- **Structural gate** — real prize? *Branch:* real fuel (0→1) or bottleneck-with-pricing-power (1→100). No → AVOID.
- **Confirmation gate** — is the wheel turning? Deal flow signing → continue; ease-only/no deals → WATCH; deals drying or pricing power expiring → AVOID.
- **Runway gate** — room left in the phase? Exhausted → EXIT/AVOID.
- **Value gate** — price sane? (B3 — the engine, the only piece built.) Fully priced → WATCH/small; reasonable → BUY.
- **Size** — by mode (0→1 small/asymmetric; 1→100 larger), by correlation (same-wave names = one bet), by attention (high = ride, low = accumulate).

The 6/6-BROKEN incident, in this vocabulary, was the system **running the value gate alone, on both kinds of names, with no structural gate in front of it** — so 0→1 names failed for looking expensive against earnings they don't have yet, and 1→100 names failed for looking expensive at precisely the point in the loop where pricing power makes trailing multiples meaningless. The two loops fail the *same* gate for *opposite* reasons — which is the cleanest argument in the whole repo for why the cascade must be conditional and ordered, never a weighted average.

---

## 3. Progress — what's real, what's half-built, what's dead

### 3.1 Genuinely solid (verified)

- **Test suite:** 147 passing deterministically in <1s, no network (verified in this audit). Engine math (37), consensus/mode-of-N, kill-gate routing, seal fingerprints, EDGAR fiscal alignment (incl. the SNDK straddle regression) are well covered.
- **Seal/grade loop mechanics:** append-only design intent, idempotent date-pinned grader, cohort keys from prompt hashes, honest `version_cohort_break=None` for unknown. Institutional-grade design.
- **kill_gate.py:** pure, relax-only, copy-not-mutate, machine-readable override record. Exemplary hard-gate *shape* (the input it keys on is the problem — §4.2).
- **Model D parser discipline:** probabilities must sum to ~1.0, forcing a downside scenario into every vision valuation — the right guard against manufactured bull cases.
- **finance_data architecture:** provider ABC, per-ticker chains, two-tier operator overrides with provenance, re-IPO data cutoffs, EDGAR-as-ground-truth philosophy, live-spot-vs-EOD-close separation.
- **API route hygiene:** atomic per-ticker lockfiles, ticker regex validation, driver-key allowlists, subprocess injection discipline. The completeness critic confirmed **no secret has ever been committed** in git history.
- **CHANGELOG.md:** the best artifact in the repo. Falsifiable acceptance criteria, live validations, honest "not committed" flags, self-recorded retractions.

### 3.2 Half-built / wired-but-dark

- Dual-system Step 1 (persisted, unconsumed — above). Steps 2–4: zero code.
- Mode-of-N consensus: shipped, live-validated — and **default-off in production**. Nothing anywhere sets `SELF_CONSISTENCY_N=5` (not cron, not env); every production seal takes the known-60%-reproducible N=1 path. And even at N=5, only round 1 is damped — the corpus callosum, research round, and the **rough_target_range call that emits the actual sealed/bet numbers remain single-sample**.
- Analyst panel [CHAIN]: built, tested, injected — but the macro block it rides with is a hand-seeded snapshot from **2026-05-17** (Warsh/Hormuz/hike-odds), injected into every judgment run seven weeks later; `run_macro.py` (P5) was never built.
- Model D: wired and gated correctly, but the bracket compares a **5-year PV at 12%** (vision ceiling) against a **12–18-month undiscounted** risk-adj target (engine floor). The frames differ by roughly the 5-year discount factor (~0.57×), so the LITE "0.8× inverted bracket," recorded as a datum, is substantially a **frame artifact** — like-for-like it is ~1.4×. This changes the June 26 conclusion.

### 3.3 Dead, dormant, or bogus (all verified)

- **Discovery (gen-2):** dormant since 2026-05-09. Its intake script (`discovery_ingest.py`) was a **hard SyntaxError from its creation commit** until 2026-06-24 — i.e., the committed multi-market intake *never once ran from repo history* and nothing noticed for 6.5 weeks. The dashboard "Queue thesis" / "Dismiss" buttons perform **no network call** (local state only). The panel renders May-era tags with hardcoded "last 30 days" claims and an API-fabricated `run_at` freshness timestamp.
- **verify_model.py Excel parity:** requires a `recalc.py` that has never existed; returns exit 0 with "diffs=0" meaning *not checked*.
- **Circuit breakers:** `check_target_quality`'s TARGET_SWING / REGIME_CHANGE / KILL_SIGNAL_CONTRADICTION checks can never fire — no call site passes the history arguments.
- **backtest.py:** reads columns (`composite_score`, `direction`, `realized_return_pct`) that don't exist in `signal_outcomes` — every signal scores 5.0 and reads "bullish"; its metrics are market beta, not scout skill. Imported nowhere.
- **position_sizing.py / paper_trade.py:** zero importers; paper_trade reads a `models.json` nothing writes and misparses `analysis.json`'s shape (all scores → 0 → close everything).
- **scout_filings:** a never-implemented stub still registered as a live free scout, emitting placeholder signals that satisfy sufficiency checks.
- **Point-in-time backtest/fixtures:** `backtest_targets.py`, `capture_engine_fixtures.py`, `test_engine_fixtures.py` all pass `as_of=` to a function that dropped that kwarg ~2026-05-07 → TypeError. **The `test_skip_floor` failure everyone attributes to "no network in the sandbox" is actually this bug — the fixtures skip 100% regardless of network.** (Reproduced empirically in this audit.)

---

## 4. Where the logic fails or is weak — verified findings

Ordered by consequence, not by subsystem. Every item below was adversarially re-verified against the code; several were reproduced numerically.

### 4.1 Engine math correctness (contradicts the 06-27 "engine is sound" verdict)

1. **[CRITICAL — confirmed, reproduced] Archetype valuation-year vs discount-year mismatch** (`target_engine.py:1495-1501, 1623`; `registries.py:117-123`). Terminal value is taken at the archetype's year (transformational Y4, compounder/cyclical Y5) but discounted using years derived from the *global* VALUATION_YEAR=3. Line 1622's `actual_discount_years = max(0, val_year - (val_year - discount_years))` is algebraically a tautology — dead code that was supposed to be the fix. Effect: 1–2 years of growth accrue **free of discounting** for compounder/transformational names. Measured +19.5% on a stub; total archetype-vs-garp delta on identical inputs can exceed +50%. LITE is tagged transformational — its targets carry this today.

2. **[CRITICAL — confirmed, reproduced] P/S mode double-counts net cash / double-penalizes debt** (`target_engine.py:1973-1979, 2089-2107`). Terminal P/S is derived from `market_cap / ttm_rev` — an **equity** multiple — but the scenario price then treats Rev×P/S as *EV* and subtracts net debt again. Measured: identical stub, net_debt 0 → −$2B: base $73.29 → $93.09 (+27%). This is the mode used precisely for the hardest names (pre-profit RKLB/ACHR profiles), and it's wrong by exactly |net_debt|/share, silently.

3. **[HIGH — confirmed] One-directional Gordon reconciliation with circular exit multiples** (`target_engine.py:1574-1607`). The blend corrects Gordon *only when it undershoots* the exit-multiple leg; overshoots are kept (log only). Exit multiples are anchored to the **current** EV/EBITDA, so in a frothy tape the "bottom-up" target partially re-derives the current price. Systematic upward bias.

4. **[HIGH — confirmed] Cyclical stocks get no-op sliders via the API** (`target_api.py:176`). The API checks `valuation_method == "cyclical_normalized"` but the engine emits `"cyclical"` (the changelog records fixing this exact string in three frontend files — the API-side check was missed). Cyclical names ship standard sliders (`ev_ebitda_multiple`, `ebitda_margin_target`) that `_scenario_price_cyclical` ignores — a user stress-testing MU/SNDK-class downside moves a slider that does nothing and concludes the downside is robust.

5. Medium tier, briefly: bear margin floored at TTM can exceed base mid-cycle (the bear case can't model the turn it exists for, `target_engine.py:2643`); WACC releverage reads *net* debt not gross (`:937`); hardcoded 4.3% risk-free/ERP constants with no refresh path (`:147`); scenario "monotonicity fix" reorders whole ScenarioResult objects, mislabeling drivers in the deduction chain (`:3293`).

### 4.2 The gate that guards the money is not enforced in code

6. **[CRITICAL — confirmed] `risk_adj_ev_ratio` is LLM prose, never recomputed** (`run_thesis.py:858-956`; `kill_gate.py:76-89`; `thesis_v3.md:164-181`). The clamp table ("directional, not advisory") lives only in the prompt. Code has `spot` and `risk_adj_target` in hand simultaneously and never computes the ratio to cross-check the model's self-report; `kill_gate` only ever *relaxes* BROKEN upward, never clamps downward. A model that emits ratio 0.97 when the numbers imply 0.55 (arithmetic slip or gate-gaming — the changelog itself flagged "prompt may game the gate" on 05-10) sails through, persists, and renders as a buy-tier badge. This inverts the system's core discipline claim. **The fix is ~5 lines of arithmetic.**

7. **[HIGH — confirmed] Archetype routing is inert for 5 of 6 watchlist names.** `config/ticker_archetype_overrides.json` tags only LITE (+AMD, not on the watchlist); all 6 `watchlist.json` archetypes are None. The D1 kill gate and the [ARCHETYPE_OVERRIDE] prompt leg read only that config → strict no-ops for PLTR/RKLB/ACHR/CELH/SNDK, and `kill_condition_eval` defaults everything to **GARP guidance** — so SNDK (memory cyclical mid-supercycle) gets kill-evaluated under rules where a routine cyclical drawdown reads as thesis deterioration. The uniform clamp that produced the 6/6-BROKEN sweep persists for every untagged name. Related: on the legacy path, `analyst.py:874` loads archetypes from a `models` table **nothing writes** — always None.

8. **[HIGH — confirmed] Fail-open kill evaluation** (`kill_condition_eval.py:140-147, 221-229`). Missing API key, timeout, 429, bad JSON — all return `status='safe'`. Worse, the UI *suppresses* the reasoning field when status is safe, so "Evaluation failed" is unviewable, and `checked_at` refreshes — a dead safety net presented as a fresh green light, precisely during the outages when risk is highest.

9. **[HIGH — confirmed] A truncated thesis silently becomes the latest verdict** (`run_thesis.py:858`). `extract_closing_json(text) or {}` — a max_tokens truncation persists an all-null row (conviction None, targets None) that masks yesterday's good thesis in the latest-wins API.

### 4.3 The calibration loop is being poisoned — and grades ripen this week

This cluster is the most time-sensitive in the report. The system's long game is "seal predictions → grade at T+30/60/90 → calibrate." Every leg has a hole, and the first real grades land in early July — now.

10. **[HIGH — confirmed, worse than first claimed] The legacy pipeline logs all-zero prediction rows twice daily** (`run_pipeline.py:770-788`). It reads `analysis_entry.get("target_price")` — a key that **does not exist** in analyst.py's output (the real target lives at `event_impacts.final_target`) — so target, current price, low, high are all zero, plus hardcoded 0.2/0.6/0.2 probabilities. The comment calls this dataset "irreplaceable."

11. **[HIGH — confirmed] The grader has no source filter** (`run_checkpoint.py:186-192`). It loads *every* prediction_log row — so the zero-target legacy junk gets graded into `prediction_outcomes` alongside real Socratic seals, and grades are append-only by design. Once the July cohort is graded against fabricated bands and zero ref prices, the corruption is permanent by the system's own rules.

12. **[HIGH — confirmed by simulation] prediction_logger off-by-one loses entire rows** (`prediction_logger.py:55-59, 99-115`). Five always-present seal columns vs a 5-attempt strip budget: with the checkpoint_seal migration unapplied (it is one of the pending ones), stripping consumes all 5 attempts and **the whole row is lost**, not just the seal fields — for both nightly batches and Socratic seals.

13. **[Context] The undocumented July-1 incident.** Commit `04d43be` ("new") adds `_dbg.py`/`_fb.py`/`_g.py` — ad-hoc probes for "bad current_price (null/0)" seals and "BAD PICK" grading rows — with no CHANGELOG entry, violating the project's own rule. The corruption these scripts hunt is exactly what items 10–12 predict.

14. **[CRITICAL — confirmed with corrections] Event-magnitude calibration math is statistically invalid and scales live targets** (`calibration.py:163-183`). Each stock's *total* price move is attributed to *every* pending event, daily analysis rows pseudo-replicate the same outcome into dozens of correlated "samples," and the resulting ratios (clamped at 3×) multiply live event contributions in the authoritative blend. One 30% earnings pop can triple every event type's weight.

15. Adjacent: **target-convergence calibration grades 12-month targets against 7–90-day outcomes** (every long-horizon prediction reads "too bullish" by construction); **bets inherit semantically inverted fields** (`run_judgment.py:60-73, 217-219` links the latest socratic_analyses row of *any* mode; run_thesis's `auto` dual-writes store `buy_below` — an entry *trigger* — as `downside_price`, a risk floor).

### 4.4 The judgment layer's epistemics

16. **[HIGH — confirmed] Production seals are N=1 from a measured 60%-reproducible model** (§3.2). The fix exists, is validated, and is off.
17. **[HIGH — confirmed] Consensus tie-break is a network-latency race** (`consensus.py:102`; samples appended in `as_completed` order; `Counter.most_common(1)` breaks ties by insertion order). The unit test asserts a determinism production doesn't have. A 2-2 verdict split is decided by which API call returned fastest.
18. **[HIGH — confirmed] validated_corrections circularity** (`run_socratic.py:614-641`). The engine's own single-run LLM research, once operator-promoted, becomes cross-ticker "ground truth" that all five prompts *forbid models from contradicting* — including against fresh primary sources. One misread filing propagates as unfalsifiable fact to every future run on every related ticker.
19. **[MEDIUM — confirmed] `fill()` injects context blocks 2–3× into every judgment prompt** (`run_socratic.py:165`), splicing [MACRO]/[VIX]/[CHAIN] mid-instruction and mangling the anti-anchoring rules the prompts carefully encode.
20. Also: K=5 stability comparisons are statistically meaningless for keep/kill decisions on context blocks; the [MACRO] block is 7 weeks stale (§3.2); paid PR newswires sit inside the web-search allowlist (narrative-injection surface for exactly the microcap-promotion pattern a 10× hunter will meet).

### 4.5 Legacy pipeline (still running twice daily, still spending tokens)

21. **[CRITICAL — confirmed, reproduced] Event recency decay is completely broken** (`event_reasoner.py:117-132`). `date_str[:len(fmt.replace('%',''))]` truncates every date so `strptime` fails for all three formats → `return 0.0` days → **every dated event carries full weight forever**. A 5-month-old catalyst contributes undecayed to `final_target` — which `merge_enabled=True` makes the authoritative legacy target.
22. **[HIGH — confirmed] Composite weights are nondeterministic between two wrong states** (`feedback_loop.py:67-73` vs `analyst.py:107-115`): either the feedback DEFAULT_WEIGHTS silently replace analyst FACTOR_WEIGHTS (zeroing YouTube — the pipeline pays Gemini for a scout that contributes nothing) or `get_adaptive_weights` crashes on a registry key mismatch.
23. **[HIGH — confirmed] `--auto-thesis-after` crashes with NameError** (`HERE`/`REPO_ROOT` undefined, `run_pipeline.py:109`) — and would double-run the thesis if fixed. The dashboard add-stock flow passes this flag.
24. **Three unreconciled persisted targets per ticker:** `stocks.target_price` (generate_model's base scenario, LLM-refreshed twice daily — overwriting any hand-edited thesis/kill text), `analysis.event_impacts.final_target` (engine+criteria+event blend), `theses.thesis_target/risk_adj_target` (thesis path — the dashboard headline). No reconciliation, no precedence rule. **Ask AI answers "should I buy?" from the oldest of the three** (`app/api/ask/route.ts` never queries `theses`, and hardcodes a legacy model ID).

### 4.6 Frontend integrity

25. **[HIGH — confirmed] The flagship number is tautological** (`TargetPriceModel.tsx:305, 777, 786-791`). `ImpliedTargetBox` receives the same value as both implied price and thesis target whenever the engine loaded — the "target met or exceeded" badge compares the engine base *to itself* and is effectively always green; slider stress-tests never move the headline.
26. **[HIGH — confirmed] What-if sandbox frozen at engine v1** (`whatif-engine.ts:104-111`): fixed 50/50 exit-multiple blend, discount hardcoded to ^2 regardless of the horizon selector, while the engine moved to Gordon+ROIIC-primary. Tornado charts and saved scenarios rank sensitivities under a model the engine no longer uses.
27. **[HIGH — confirmed] Brief-page cyclical math omits discounting** (`helpers.ts:176-189`) — the deduction chain and sensitivity tables run ~25% above the engine base shown in the headline of the same page (at 12% WACC).
28. Also: watchlist UPSIDE is computed against `thesis_target` (the bull destination, not the risk-adjusted target) while ThesisHeader's "Floor (DCF)" cell displays **spot**; the kill-status badge can never appear on the dashboard (`killConditionEval` never mapped in `loadStocks`); the 30D sparkline is the current score duplicated; **`next build` fails typecheck** (two structural type errors masked by an `any[]` escape) — the app is dev-mode only.

### 4.7 Ops, security, and the QA net

29. **[CRITICAL — confirmed] Split-brain deployment.** `origin/main` = 8c4e505 (2026-05-30); the session branch carries +3,861 lines including the EDGAR fix, engine v3 changes, and all Step-1 work. Scheduled Actions run main. Local runs use the new engine. Two different engines write the same database.
30. **[HIGH — confirmed] Green-no-matter-what.** `run_pipeline` never `sys.exit(1)`; scout-phase failures don't even set `error_msg`, so pipeline_runs and the Health panel show SUCCESS when every scout fails. No CI runs pytest. No alerting anywhere.
31. **[HIGH — confirmed] `validate_schema` certifies "all OK" while ignoring every table where drift is live** (theses, prediction_log, prediction_outcomes) and points at a migration.sql that doesn't contain the missing columns.
32. **[HIGH — critic] The control plane is unauthenticated** — no middleware, zero auth checks across `app/api`: any LAN peer can start Opus pipelines, fire $3 thesis runs per ticker in parallel (the NavBar button does exactly that with no budget cap), delete stocks, and hit a DELETE endpoint that `pkill`s 12 generic process patterns on the host.
33. **[HIGH — critic] `requirements.txt` cannot run the money path** (no `anthropic`, no `PyYAML`) — the manual Full Pipeline workflow's thesis stage silently no-ops with a green check; no second machine can reproduce production.
34. Also: "append-only" seal tables have `FOR ALL USING(true)` anon policies (no DB-level append enforcement — relevant to the corrupt-seal investigation); zero backup automation for the one-copy state (Supabase + gitignored `data/memory/*.md` incl. hand-written Hume Notes, on one laptop); refresh-prices cron (~90 runs/weekday, no pip cache) can plausibly exhaust the Actions free tier and silently halt *all* scheduled workflows; a stale duplicate watchlist sits at `config/config/watchlist.json`; docs say `SUPABASE_KEY` while code reads `SUPABASE_ANON_KEY` and `.env.example` omits both.

### 4.8 Data-layer gaps (beyond the fixed SNDK bug)

35. **[HIGH — confirmed, reproduced] The EDGAR gate aligns on parsed period *labels*, ignoring the provider's actual `date` field** (`finance_data.py:452-468` reads `_date`, which no provider ever sets — they all store the true end under `date`). A fiscal quarter ending early in a calendar quarter (the exact SNDK shape) is silently *exempted* from the gate rather than checked.
36. **[HIGH — confirmed] Fiscal Q4 is structurally unverifiable** — the XBRL extractor keeps only 60–100-day duration facts and never synthesizes Q4 = FY − (Q1+Q2+Q3), so ~25% of every TTM window (one quarter in four) is permanently outside the hard gate.
37. **[HIGH — confirmed] The gate checks revenue only** — margins, operating/net income, and share counts are trusted blind, even though the layer's own founding incident (MU 77% margin bug) was a *margins* bug, and the XBRL fetch already pulls income facts and discards them.
38. `shares_diluted` silently degrades to basic shares (inflating per-share targets on high-SBC names, PLTR-class); no data-recency check exists (a provider lagging a quarter yields a silently stale TTM against a live price); `cross_validate()` is CLI-only despite CLAUDE.md's claim; scout_quant remains yfinance-first, bypassing this entire layer.

---

## 5. Documentation drift — the context layer is actively harmful

CLAUDE.md is injected into every AI session and is now dangerous, not just stale:

- **The "MU Data Source Bug" section instructs the opposite of reality.** SEC XBRL proved (06-26) the $23.86B/$41.46B figures are genuine supercycle revenue; the bug was in the cross-check. A new session following CLAUDE.md would re-suppress exactly the memory-supercycle signal the dual-system doc identifies as the CONVICTION BUY quadrant (MU/SNDK).
- It describes only the April architecture — no run_thesis, run_socratic, kill gate, seals, Model D, analyst panel, dual-system. Says 9 stocks (it's 6), 19 tests (147), a pre-commit hook that doesn't exist in any fresh clone, a 4-layer JSON repair that was replaced by structured outputs, and a `docs/ROADMAP.md` that was never committed.
- **Ground-rule erosion is visible in git:** the "money-path = human-approved, logical milestones" rule ended as two mega-bundles ("8cf72e4", 52 files) and then "new"/"improvements" one-word commits, with the July-1 commit skipping the changelog entirely. The 05-24 truncation incident ("no version history to restore") is the documented cost of exactly this pattern.

---

## 6. Recommendations — a consolidation sprint, in priority order

**This week (time-critical — before the first grades ripen and bake in):**
1. **Un-poison calibration:** add a source/mode filter to `run_checkpoint._load_seals`; fix or disable the run_pipeline prediction snapshot (it currently logs zeros); fix the prediction_logger off-by-one; apply all four pending migrations (5-minute SQL-editor task that unblocks kill_gate_override, model_d_bracket, the strategic axis, and seal integrity at once); write the CHANGELOG entry for the July-1 seal investigation.
2. **Enforce the gate in code:** recompute `risk_adj_ev_ratio = risk_adj_target / spot` in `run_thesis` and clamp conviction downward per the table. ~5 lines; converts the system's central discipline claim from prose to code.

**Next (mechanical fixes to confirmed math bugs):**
3. Fix the archetype discount-year mismatch (use `val_year`-consistent discounting) and the P/S net-debt double-count (either make P/S a pure equity multiple or convert to an EV/S anchor). Re-run verify paths; add offline tests for the P/S and archetype≠garp paths — the current suite covers neither.
4. Fix `event_reasoner._days_since` (one-line slice bug) or, better, decide the legacy blend's fate explicitly (see 7).
5. Fix the `as_of` TypeError trio and re-capture engine fixtures — this also corrects the false belief that `test_skip_floor` is network-gated.

**Then (ops unification):**
6. Merge the session branch to main (or stop scheduled Actions until merged); make `run_pipeline` exit nonzero on failure; add a pytest job to CI; commit the pre-commit hook as a tracked script with an installer; fix `requirements.txt`; put minimal auth in front of the API routes; set up Supabase backups + version `data/memory/`.
7. **Decide the single source of truth for targets/conviction** and demote or retire the other two. The legacy generate_model path burns Opus twice daily to produce numbers the dashboard no longer headlines, overwrite operator-edited kill conditions, and feed a broken event blend.
8. Tag archetypes for all 6 watchlist names (or wire the classifier output into the gate path) — this is what actually activates D1/V2 for the watchlist.

**Strategy:**
9. Write the one-page reconciliation of dual-system vs 10× (which doc governs, what Step 2 actually is), commit it as `docs/ROADMAP.md`, and rewrite CLAUDE.md to describe the real system — with the MU section inverted.
10. Follow the 10× doc's own advice before building: hand-validate the gated cascade on memory/HBM. Given items 1–8, the cheapest alpha right now is not a new axis — it's making the existing axes tell the truth.

---

## 7. Closing assessment

The vision→scouts→judgment→calibration arc is the right shape, the failure-driven pivots have been intellectually honest, and the newest strategic docs are the sharpest thinking in the repo. The codebase's weakness is not direction — it's **accumulated unverified wiring**: gates that are prose, nets that are dead, loops that are dark, and two deployment realities writing one database. Nearly every critical finding above is cheap to fix relative to what it protects; almost none of them requires new design. The project's own 06-27 instinct — settle before building further — was correct. It just hasn't happened yet.
