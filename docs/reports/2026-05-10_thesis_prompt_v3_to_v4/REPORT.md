# Thesis Prompt Architecture — V3.4.2 → V3.4.3 → V3.4.4

**A decision report on the negative-EV gate, the single-point-estimate problem, and where the prompt sits in the broader system.**

Date: 2026-05-10
Author: Stock Radar working notes
Status: v1 — post squad review (critic + fact-checker + outsider + red-team + synthesizer); five must-fix items applied; remaining qualifications marked inline.

**What the squad caught and what was fixed:**
- *Critic*: cutoffs (5 thresholds) anchored on N=3, defended only definitionally → caveat added in Appendix B.
- *Fact-checker*: AMD self-catch was misattributed to "loss-scenario rule" → corrected in Appendix C to target-derivation math at Step 5/7. MU mechanism flagged as unverifiable from current artifacts.
- *Outsider*: two critical findings ("engine already produces 3 scenarios," "calibration is a month away") were buried in Section 5 → both surfaced to the top of the executive summary.
- *Red-team*: V3.4.3 kill rule is gameable (6pp probability shift on one catalyst clears the gate) → V3.4.3.1 (Python post-processor) committed as named follow-up rather than contingent. Option 2 effort estimate corrected from "1 day" to "~3 days" after verifying `analyst.py:1189` drops `_tres.low/high`.
- *Synthesizer*: validation re-run tests convergence with V4, not correctness → caveat paragraph added to Section 7.

The squad's "ignore" list (claims that survived review): the V4 mechanism math (COHR 0.871, AMAT 0.816, U 0.952 EV ratios all check out), the architectural framing of single-call vs two-agent, the philosophical constraint-vs-expansion arc in Section 6.

---

## Executive summary

**Three framing facts that should be read before the rest of this report:**

1. **The engine already produces conservative / central / bull forward-EPS scenarios via `target_engine.py` and has been doing so for months.** The thesis prompt does not consume the engine's scenarios as input; it reconstructs its own forward path from scratch. We have been operating two parallel forward-EPS estimators that don't talk to each other. This fact is most consequential for the V3.4.4 decision (Section 4–5) and is the strongest argument for Option 2 (engine-feed) over either prompt-only path.

2. **No version of this prompt — V3.4.2, V3.4.3, V4, or V3.4.4 — has yet been calibrated against realized 12-month returns.** The 8-ticker cohort is a comparison test (V3.4.3 vs V4 architecture), not an outcome test. Outcome calibration is gated on N≥20 thesis rows (deferred Session 6 task #45) and is at least a month away. Every recommendation in this report is therefore epistemically constrained to "this architecture matches V4" rather than "this architecture makes money."

3. **LITE is the load-bearing test case and the architectures disagree by an order of magnitude on it.** V3.4.2 says HIGH 25% target $1,139; V4 says BROKEN 0% with buy_below $96 — requiring a 66% drawdown before entry. LITE is the stock Hume has studied more deeply than any other, the one with $42B backlog sold-out-through-2028, the reference 10x candidate. The kill-rule MECHANISM (V3.4.3 inlining V4's math) is mechanically sound regardless of which architecture is right on LITE. But the EV-INPUT CORRECTNESS is a separate question — the kill rule can be perfectly implemented while its inputs systematically over-weight downside (Step 8 forces named loss scenarios) and under-weight upside (Step 10 catalysts are deltas off a single base case, not full alternate forward-EPS paths). If LITE rallies above $400–500 in the next 90 days, V4 was wrong and "validating V3.4.3 by matching V4" locked in replicated bias rather than a real validation. If LITE drops below $200, V4 was right and the kill-rule architecture is validated against the hardest single case. Either way, **LITE's T+90 outcome is the highest-information signal in the system right now**, and the kill-rule's gate-vs-inputs distinction is the lens through which to read it.

With those framing facts in mind:

We ran an 8-ticker cohort (MU, LITE, AXON, AMD, COHR, ALAB, AMAT, U) through both the production V3.4.2 single-call architecture and a V4 spike that uses a two-agent dialogue (Strategic Agent + Tactical Agent + bidirectional channel, 2-round bounded). AMD was skipped on V4 (`--skip-v4-on-broken` flag was active and V3.4.2 self-caught with BROKEN), so V4 ran end-to-end on seven tickers. All seven V4 runs produced position size ≤10%: six produced BROKEN with 0%, one produced WEAK with 10% (U). V3.4.2 produced HIGH or MEDIUM conviction at 20–25% size in four of those same seven cases (LITE, AXON, COHR, ALAB) and a partial divergence on U (MEDIUM 20% vs V4's WEAK 10%).

The largest single divergence was ALAB: V3.4.2 said HIGH 25% target $345 at the same hour V4 said BROKEN 0% target $185 with buy_below $165 — a 46% target gap and a 25-point sizing gap on the same name, same price, same data.

The mechanism is identifiable, not mysterious. V4's Tactical agent computes a probability-weighted exit price (the prompt's existing risk-adjusted target divided by current price), treats values below 1.0 as direct evidence the trade has inverted asymmetry, and refuses to take a position regardless of how strong the strategic case is. V3.4.2's single-call architecture computes the same number internally but never applies it as a binding constraint; the persona-split text that asks one LLM call to wear "strategic" and "tactical" hats sequentially leaks the strategic conviction into the sizing recommendation in roughly half the cases.

V3.4.3 inlines V4's mechanism as a numerical gate at Step 9 and Step 12. It captures the win at roughly 1/4 the LLM cost (one Opus call per thesis vs. four). Empirical anchoring for the gate cutoffs comes from three V4 datapoints (COHR ratio 0.871 → BROKEN, AMAT 0.816 → BROKEN, U 0.952 → WEAK 10%). N=3 is small, but the cutoffs are conservative-by-design: a stock with risk_adj_ev_ratio of 0.95 is by construction a stock whose own probability-weighted exit price equals current entry, which is a defensible refusal threshold even without empirical validation.

A separate concern surfaced during the AMD case study, raised by Hume directly: the prompt produces a **single point estimate** for forward EPS and for the multiple. Step 4 emits one quarterly EPS path through Q4 2027. Step 5 derives one thesis multiple. Step 6 produces one NTM EPS at the target date. Step 9 weights against named downside risks but does not symmetrically explore upside via alternate forward-EPS scenarios. For a thesis target like AMD's $440, that means the BROKEN call is conditional on margins not exceeding 35%, on warrant dilution arriving on schedule, and on multiple compression to 35–40x. If any of those is too conservative, the trade flips from BROKEN to LIVE. Today the system has no mechanism to surface that conditionality.

V3.4.4 (proposed) addresses this by replacing the single forward-EPS path with a triple — conservative / central / bull — each anchored to named drivers (e.g., "MI450 ramp at-spec," "MI450 pulled in two quarters," "MI450 hits ASP $32k vs $29k"). The risk-adjusted EV calculation at Step 9 then weights across both downside risks and forward-EPS scenarios symmetrically. Cost is marginal (no second LLM call; the prompt is longer but a single Opus call still completes within token budget).

The decision being requested:

1. Ship V3.4.3 as the kill rule (already patched into `scripts/prompts/thesis_v3.md`, awaiting validation re-run).
2. Validate V3.4.3 against V4 on the 8-ticker cohort. Pass criterion: V3.4.3 lands within 5% of V4 sizing on at least 7/8 tickers. Cost: ~$25.
3. Decide whether V3.4.4 EPS-scenario-triple ships now, after V3.4.3 validation, or never. The case for "now" is that the AMD case shows the single-point-estimate limitation will continue producing false BROKENs on accelerating-EPS names; the case for "later" is N=8 is too small to know whether single-point is actually a binding problem in production.

The deeper question that frames all three decisions is whether the thesis prompt is even the right place for the kind of nuance Hume is asking for, or whether the prompt should be a binary buy/no-buy gate and the upside-scenario exploration belongs in a separate layer. That is the architectural question this report is meant to answer.

---

## Section 1 — What we tested

The cohort was assembled in two batches. The first three tickers (MU, LITE, AXON) were run as part of the V4 spike experiment on 2026-05-09. The next five (AMD, COHR, ALAB, AMAT, U) were added on 2026-05-10 via the automated `scripts/run_architecture_experiment.py`. All eight were run on V3.4.2 production prompts and on V4 spike prompts on the same day at the same spot prices, with the same scout-verified financials block as input.

Selection was non-random. The first three were chosen because each had been the subject of recent investigation: MU for the data-contamination saga, LITE as Hume's reference 10x candidate, AXON as the case that motivated the V4 architecture in the first place. The five additional tickers were chosen to span archetypes: AMD (mega-cap AI infra, +345% trailing 52 weeks), COHR (mid-cap optical networking, +357% trailing 52 weeks), ALAB (small-cap AI interconnect, recent IPO trajectory), AMAT (mega-cap WFE, +172% trailing 52 weeks), U (mid-cap software turnaround, -10% trailing 52 weeks but +121% YTD from trough). The deliberate diversity was meant to test whether the V3.4.2 vs V4 divergence was a sector-specific artifact or a structural one.

The summary matrix:

| Ticker | V3.4.2 conv / size / target | V4 conv / size / target / buy_below |
|---|---|---|
| MU | BROKEN / 0% / $910 | BROKEN / 0% / — |
| LITE | HIGH / 25% / $1139 | BROKEN / 0% / $96 |
| AXON | HIGH / 25% / ~$680 | BROKEN / 0% / $590 |
| AMD | BROKEN / 0% / $440 | (skipped — V3.4.2 self-caught) |
| COHR | MEDIUM / 25% / $476 | BROKEN / 0% / $310 (buy_below $280) |
| ALAB | HIGH / 25% / $345 | BROKEN / 0% / $185 (buy_below $165) |
| AMAT | LOW / 0% / $490 | BROKEN / 0% / $394 (buy_below $370) |
| U | MEDIUM / 20% / $38 | WEAK / 10% / $29 (buy_below $22) |

Reading across rows reveals two patterns. The first is that V3.4.2 already produces tighter sizing on archetype-cyclical names where its native loss-scenario rule binds (MU, AMD, AMAT). The second is that V3.4.2 leaks on names where strategic conviction is high and the stock is trading near or above its modeled fair value (LITE, AXON, COHR, ALAB, U). We named this the AXON-pattern after the original case that surfaced it.

The AXON-pattern, stated cleanly: a stock with a real and verifiable secular thesis, trading at or above the multiple the thesis itself implies, with all five of V3.4.2's filters passing. The persona-split text in V3.4.2 — which asks one LLM call to switch between Strategic Mode and Tactical Mode — produces strategic conviction HIGH and then anchors the tactical sizing to that conviction rather than to the math the same call just produced. The result is a recommendation to size 20–25% at a price where the prompt's own risk-adjusted target sits below spot.

V4's two-agent dialogue separated those reasoning paths into two distinct LLM calls: Agent A produces the strategic case without any price-level outputs at all (it is forbidden by prompt to emit prices, multiples, or sizing); Agent B produces the tactical case taking A's output as input but constructing its own EV math from scratch. Agent B has no incentive to be coherent with A's conviction level; it is graded on whether its EV math survives forensic scrutiny.

---

## Section 2 — Why V4 produced different answers

The V4 win is mechanical, not architectural-magic. Reading Agent B's outputs across the 8-ticker run, the same calculation appears in every BROKEN case:

For COHR at $335.26: Agent B computed weighted scenarios producing risk-adjusted EV of $292. That is 87% of spot. Agent B treated this as direct evidence that the trade has negative asymmetry and refused to size, despite accepting Agent A's STRONG strategic rating without dispute. Quote from the round-2 tactical output: *"The strategic thesis is STRONG and I do not dispute it. The demand is real, the NVIDIA partnership is verified, the cycle is early-to-mid. But the stock price has already captured this thesis. At 43x forward earnings, the market is pricing in multi-year double-digit growth with margin expansion — which is exactly what the thesis predicts. There is no gap between the thesis and the market's pricing."*

For AMAT at $435.44: Agent B computed weighted EV of $355 (82% of spot). Same refusal, same logic.

For U at $28.16: Agent B computed weighted EV of $26.80 (95% of spot). Here the asymmetry is thinner — a 5% gap rather than a 13% or 18% one — and Agent B produced WEAK with 10% size rather than BROKEN with 0%. This case is what tells us the gate is not binary; it scales smoothly from "trade is wrong" through "trade is mediocre" to "trade is good."

The V3.4.2 prompt at Step 9 already instructs the LLM to compute the same number — "Compute from your actual enumerated risks: thesis target × (1 – cumulative risk probability) + Σ(risk probability × risk price)." The number is produced in the closing JSON as `risk_adj_target`. But V3.4.2 never instructs the LLM to compare this value to the current spot price, never tells it that a value below spot is binding evidence, and never gates conviction or sizing on the result. The number is computed and then ignored.

V4 made it binding by separating the Tactical agent into its own call with its own success criterion — "produce a position recommendation that survives forensic scrutiny on every input." That agent, given Step 9's math and asked whether to size into a trade where the math says EV < spot, refused.

The cost question is real and now (after a fact-check) more grounded. A V4 thesis run is structurally four Sonnet calls per ticker (Strategic R1, Tactical R1, Strategic R2, Tactical R2; verified against `scripts/run_thesis_v4_spike.py`). A V3.4.2 thesis is one Sonnet call with ~7 web searches. The model is **Sonnet, not Opus** — the earlier draft of this report incorrectly stated Opus. Per-run cost estimates baked into the experiment runner script (`run_architecture_experiment.py:54-58`) put V3.4.2 at $3–5 per run and V4 at $12–20 per run. Annualized at 100-name watchlist with weekly refreshes: V3.4.2 ≈ $21k/yr, V4 ≈ $83k/yr. **Treat as directionally correct (4x cost gap) but absolute-magnitude unverified until token logging is added.** The 4x ratio is robust; the dollar values are not.

The V3.4.3 patch was designed to extract V4's mechanism and apply it inside a single LLM call, betting that the win is in the math rather than in the dialogue.

---

## Section 3 — V3.4.3 inlining

The patch lives in `scripts/prompts/thesis_v3.md` and is two changes plus a closing-JSON addition.

Step 9 was rewritten to make the EV/spot ratio explicit and named: the LLM computes `risk_adj_ev_ratio = risk_adj_target / current_price`, states the division, and states whether the value is above or below 1.0. The prompt language then introduces the AXON-pattern by name and instructs the LLM that a ratio below 1.0 with a strategic-thesis-correct setup is the canonical signal for "thesis real, trade wrong at this entry." The prompt explicitly forbids hand-waving the ratio away with strategic conviction; if the LLM wants to produce a non-trivial position despite the ratio, it must explain which specific risk probability or risk price it is challenging.

Step 12 was extended with a numerical clamp table that overrides strategic_conviction:

| risk_adj_ev_ratio | Maximum conviction | Maximum position_size_pct |
|---|---|---|
| < 0.90 | BROKEN | 0% |
| 0.90–0.95 | BROKEN | 0% |
| 0.95–1.00 | LOW | 10% |
| 1.00–1.10 | LOW–MEDIUM | 15% |
| 1.10–1.25 | MEDIUM | 25% |
| ≥ 1.25 | HIGH | 35% |

The table is described as "directional, not advisory." If the ratio is 0.87, conviction is BROKEN and position is 0%, regardless of strategic conviction. The prompt explicitly tells the LLM that if it wants to break the table, the legitimate move is to reconstruct Step 9 inputs (challenge specific catalyst probabilities or upside price impacts), not to write a sizing recommendation that contradicts the table.

The closing JSON now includes `risk_adj_ev_ratio` as a first-class field so the gate's output is queryable in Supabase, surface-able on the dashboard, and trackable across reruns.

The cutoffs (0.95, 1.00, 1.10, 1.25) come from three V4 empirical datapoints. That is a small N. The defense for shipping anyway is that these cutoffs are conservative-by-construction: a 0.95 ratio means probability-weighted exit equals 95% of spot, which represents a 5% expected loss before transaction cost and opportunity cost. Refusing to size meaningfully at that ratio is defensible without statistical validation.

The risk in V3.4.3 is gameability. The kill rule operates on a number the LLM itself produces. If the LLM realizes that ratios below 0.95 trigger a BROKEN, it may inflate catalyst probabilities or upside price impacts to lift the ratio above the threshold. Step 12 explicitly tells it not to, but that is a soft constraint on a system that has historically been responsive to similar soft constraints (Step 6's "no beat-adjustment double-count" appears to hold; Step 8's "minimum weight for required loss scenario" required two iterations to land). Whether it holds for the EV ratio is an empirical question the validation re-run will answer.

The validation plan is a re-run of the same 8-ticker cohort on V3.4.3, comparing position_size_pct outputs to V4's positions bucket-by-bucket (0% / 10% / 15% / 25% / 35%). The pass criterion is that V3.4.3 lands within one bucket of V4 on at least 7/8 names. If pass, V4 is retired and the spike folder stays as research artifact only. If fail, V4 was doing irreducible work the single-call cannot replicate, and V4 graduates to production despite the cost.

---

## Section 4 — The deeper limitation

The AMD case study from earlier today surfaced a problem the V3.4.3 patch does not address.

The V3.4.2 thesis on AMD at $455.19 produced strategic_conviction HIGH, conviction BROKEN, position 0%, thesis target $440. The prompt did its job by its own rules. It built quarterly EPS through Q4 2027, derived a 35x base / 40x stretch / 50x breakout multiple via comp tables and historical anchors, computed NTM EPS at May 2027 as $11.01, multiplied through to get a $440 target ($11.01 × 40), observed that spot $455 sits 3% above the stretch case, and refused.

Hume's pushback: "the bot cannot project forward EPS or multiples?" The bot can. It does. The point being raised is more subtle. The bot produces a **single** forward-EPS path, anchored conservative-by-design (Step 6 explicitly forbids beat-adjustment double-counting; Step 4 anchors to verified actuals plus management guidance). Bull-case earnings outcomes — MI450 ramps a quarter early, operating margin reaches 38% rather than 35%, warrant dilution arrives back-loaded — are not modeled as alternate scenarios. They show up only in the catalyst list at Step 10, where they are weighted into the risk-adjusted EV but at price-impact deltas (e.g., "+$50") that come from a single-point bull adjustment, not from running an entirely alternate forward-EPS path.

The asymmetry matters. Step 8 forces the LLM to construct named loss scenarios with explicit price targets (e.g., "Risk 1: MI450 delay → stock to $295"). Step 10 asks for catalysts but does not require the same level of rigor — there is no "construct a fully alternate forward-EPS path where catalyst X is true." So the downside is enumerated bottom-up; the upside is enumerated as deltas from the single base case.

For mean-reverting and cyclical names, this is fine. The base case is the right anchor. For accelerating-secular names — exactly the kind of stock Hume is hunting (10x candidates) — the base case may systematically undershoot because the catalyst that turns it into a 10x is not a delta off the base; it is an entirely different forward-EPS regime.

This is also why the AXON-pattern is uncomfortable in a specific way. AXON, COHR, ALAB, LITE are all names where a real bull case exists ("the secular thesis plays out faster than anyone expects, NTM EPS hits 1.5x the modeled value, multiple sustains higher because growth doesn't decelerate"). V3.4.3's kill rule will correctly refuse the trade at current entry on its risk-adjusted ratio. But it will not surface the conditional bull case that would change the answer if true. Hume sees a BROKEN signal and has to do the bull-case construction in his head.

V3.4.4 proposes a Step 6b that requires the LLM to produce three forward-EPS paths:

- **Conservative**: Step 4's existing build minus 5–10% on margins or revenue, anchored to "what if guidance compresses or competitive pressure increases."
- **Central**: Step 4's existing build, the prompt's current single-point estimate.
- **Bull**: an explicitly constructed alternate where named upside drivers are true. Required to name the drivers (e.g., "MI450 ramp pulled forward two quarters; ASP at $32k vs $29k; warrant vesting back-loaded by 4 quarters") and show the EPS impact of each.

Step 9's risk-adjusted EV math then runs across both downside risks AND the forward-EPS triple. Each forward-EPS scenario gets a probability and a corresponding thesis target (multiple held constant unless the bull case argues for sustained higher multiple). The aggregate EV combines: P(downside risks) × downside prices + P(conservative path) × conservative target + P(central path) × central target + P(bull path) × bull target.

The closing JSON gains three forward-EPS paths and three corresponding thesis targets, plus a primary thesis_target that picks the highest-probability path. The dashboard can surface all three for the analyst to inspect.

The cost of V3.4.4 is small — no second LLM call, just a longer single prompt. The benefit is asymmetric exploration: the bull case is now first-class, named, and inspectable.

The risk of V3.4.4 is that it adds complexity to a prompt that has already grown from V3.0 (10 steps) to V3.4.3 (12 steps with sub-steps and a kill rule). The memory note `feedback_engine_complexity_ratchet.md` from May 1 explicitly warned against this: 17 fixes doubled LITE error to +98% and produced an 86% miss rate. The lesson there was on the engine, not the prompt, but the principle generalizes — additional structure has to earn its keep.

The case for V3.4.4 earning its keep: the AMD case is not idiosyncratic. Any accelerating-secular name will have the same single-point-estimate problem, and Stock Radar's stated purpose is finding 10x candidates which by definition are accelerating-secular names. Without symmetric upside exploration, the system will systematically under-call exactly the trades it is built to find.

The case against V3.4.4: N=1 (AMD today). Wait until V3.4.3 has run on a larger cohort and we see whether the BROKEN signals are systematically wrong on accelerating-secular names, or whether the kill rule's conservatism is actually what the system needs.

---

## Section 5 — Where this sits in the broader system

It is worth zooming out. The thesis prompt is one layer of Stock Radar. Below it sit the scouts (insider, news, sentiment, financial) feeding the discovery universe. Beside it sit the engine (target_engine.py — the institutional-grade DCF) and the model export to Supabase. Above it sits the dashboard (Next.js, watchlist, stock detail pages, model picker). The thesis prompt's narrow job is to produce a position recommendation given verified financials, scout signals, and the analyst memory.

Different layers have different relationships to the same questions.

The engine projects forward earnings using a normalized-margin methodology with cycle awareness, archetype detection, and a target-engine merger that auto-loads forward drivers from Supabase scout signals (per `project_forward_drivers_architecture.md`). It produces multiple scenarios — conservative / central / bull — with archetype-aware tilts. It does this in code, deterministically, on every refresh. The output goes to Supabase as `targets` rows.

The thesis prompt does not consume the engine's scenarios as input. The thesis prompt re-builds quarterly EPS from scratch via web search and management guidance, picks one multiple, derives one target. The engine's three-scenario output and the thesis prompt's single-point output sit side by side in Supabase without any cross-validation, confidence interval, or disagreement surfacing.

This is a significant architectural fact that the report should not hide. **The engine already does what V3.4.4 proposes for the prompt.** The engine has been doing it for months. The thesis prompt has been ignoring the engine's scenario output and reconstructing its own forward path. We have been operating with two parallel forward-EPS estimators, neither aware of the other, neither calibrating against the other.

There are three possible responses to this fact:

1. **V3.4.4-prompt-only**: add the EPS scenario triple to the thesis prompt. Simplest path. Requires the LLM to do the work the engine already does, with worse computational discipline but better narrative output.
2. **V3.4.4-engine-feed**: have the prompt consume the engine's three scenarios as input rather than reconstructing them. The prompt's job becomes "reconcile scenarios with current price and produce a position recommendation" rather than "build the model." This is much smaller in prompt-token cost and uses the better tool for each job (engine for math, prompt for narrative).
3. **No-V3.4.4**: ship V3.4.3 and accept the AXON-pattern limitation as a known property of the system. Surface the engine's scenarios on the dashboard alongside the thesis output and let the analyst (Hume) reconcile manually.

Option 2 is the architectural answer if we believe the thesis prompt should be a binary buy/no-buy gate while the engine should own forward projection. Option 1 is the answer if we believe the prompt should be self-contained and the engine should be a cross-check rather than a feed. Option 3 is the answer if we believe the system is mature enough to ship and what's needed is Hume using it on real decisions, not more architectural development before any positions are taken.

The autonomous-trader memory note (`user_autonomous_trader_goal.md`) is relevant here. The end goal is a system Hume trusts enough to act on without manual override. Each architectural layer added before that point is a layer that has to be calibrated and that may add false confidence. The memory note `feedback_calibration_before_build.md` from earlier this month said exactly this: run target+control-group calibration before deploying new scoring systems; spread between group means is the falsifiable signal.

V3.4.3 has not been calibrated yet. The 8-ticker run is a comparison test (V3.4.3 vs V4) not an outcome test (V3.4.3 vs realized 12-month returns). The calibration question is a different question and is gated by the deferred Session 6 task (#45) — which itself is gated on N≥20 thesis rows. We are at N=8 on architecture testing, N≈14 on production thesis rows. Calibration is at least a month away.

---

## Section 6 — The grand-scheme question

Hume asked for "the grand scheme of things." The honest answer is this:

The thesis prompt evolution from V3.0 → V3.4.3 has been a sequence of patches in response to specific failure modes. Each patch was justified at the time. The cumulative effect is a 12-step prompt with sub-steps, a kill-rule table, two conviction surfaces, dual JSON fields, and roughly 4,500 words of instruction. Compared to V3.0 the prompt is roughly 3x longer and considerably more procedural.

The patches have consistently moved in the direction of constraining the LLM rather than expanding what it can do. The persona-split was constraint (don't be globally optimistic). The historical-peak anchor was constraint (don't pull multiples from analogies). The carve-out ceiling was constraint (don't justify above-peak). The minimum loss scenario was constraint (don't assign 5% to a base-rate-15% event). The kill rule is constraint (don't size into negative-EV trades). V3.4.4 if shipped would be expansion (run alternate scenarios) but framed as constraint (don't single-point-estimate accelerating-secular names).

This pattern is consistent with the system being in a particular phase: the LLM is producing outputs that look right structurally but fail on specific predictable patterns, and we are codifying the failures into rules. That is the right phase if we believe the system is close to production and the remaining work is calibration. It is the wrong phase if we believe the foundational structure is wrong and we are bandaging.

The signal that the foundational structure is wrong would be: even after all the constraints, the system still produces outputs that fail on patterns the constraints were meant to catch. If V3.4.3 ships and the AXON-pattern still leaks, that is the foundational signal. If V3.4.3 catches AXON but produces false BROKENs on accelerating-secular names that V3.4.4 would catch, that is a more mundane evolutionary signal.

Two specific risks are worth naming.

The first is the autonomous-trader risk. Hume's stated goal is a system that can run without manual override, producing thesis-driven signals he can act on at first-touch sizing (5% per `user_position_sizing_discipline.md`) and scale up on confirmation. AXON, taken at 5% on 2026-05-09, will be the first calibration point — its T+30/T+90/T+180 outcomes are the first real evidence the protocol is working. As of this report (T+1) we have no return data; the AXON signal is evidence the protocol was *executed*, not that the protocol is *correct*. If V3.4.3 ships and the AXON-class signal proves accurate at T+90, the next signal can be taken at first-touch sizing without a 30-minute manual cross-check. If V3.4.3 produces false BROKENs on accelerating-secular names, Hume will have to override the system regularly, which defeats the autonomous-trader goal. The architectural decision and the autonomous-trader goal are tightly coupled, but the coupling runs through outcome data we do not yet have.

The second is the complexity-ratchet risk. The May 1 memory note documented that 17 engine fixes doubled error and produced an 86% miss rate on LITE. The structural lesson was that complexity is not free; each rule has to earn its keep against a falsifiable test, and many rules turned out to be wrong-direction. The thesis prompt is now at 12 steps with sub-steps. If V3.4.3 + V3.4.4 ship together, it is at 13+ steps. The right reflex is suspicion: are these patches actually catching real failures, or are they ratcheting complexity for diminishing returns?

The defense for V3.4.3 specifically: the 8-ticker cohort showed a 5/8 leak rate on the AXON-pattern, the patch is mechanically equivalent to V4's win, the cost is one numerical comparison the LLM is already computing, and there is a falsifiable validation re-run gated to it. The defense for V3.4.4 is much weaker: N=1 (AMD), the engine already does the work, and a prompt-feed architecture (Option 2 above) might be the right answer rather than a prompt-only fix.

---

## Section 7 — Decision and open questions

The recommendation, in order of confidence:

**Ship V3.4.3 immediately, validate before next watchlist refresh.** The patch is committed. The validation cost is ~$32 (8 tickers × $4 per V3.4.3 Sonnet run per the experiment runner's cost estimate; the V4 outputs from 2026-05-10 are re-used, no V4 re-run needed). The downside of shipping without validation is one watchlist refresh of potentially incorrect output; the upside of shipping is closing the AXON-pattern leak before the next user-facing decision.

**Defer V3.4.4 pending V3.4.3 validation results.** If V3.4.3 catches AXON correctly and produces false BROKENs only on N=0 or N=1 of the 8 cohort tickers, the V3.4.4 scenario triple is not load-bearing yet. If V3.4.3 produces false BROKENs on multiple accelerating-secular names, V3.4.4 becomes a real candidate.

**Move on Option 2 (engine-feed) as a parallel investigation.** Independent of V3.4.4 prompt-side, surface the engine's three forward-EPS scenarios on the dashboard alongside the thesis output. The engine emits `_tres.low`, `_tres.base`, `_tres.high` at `target_engine.py` (verified at lines 1049, 3386–3394, 3426–3430). However, `analyst.py:1189` currently consumes only `_tres.base`; the low and high fields are fetched and dropped. So Option 2 is **not** a one-day frontend change — it requires `analyst.py` extraction of the three scenarios, a Supabase schema addition (three new columns or a JSON sub-object on the `targets` table), and frontend display logic. Realistic estimate is approximately three days of focused work. The architectural claim ("engine already does this") remains correct; the plumbing-to-the-thesis-layer is the work.

**A methodological caveat that applies to all three recommendations.** The validation re-run criterion ("V3.4.3 within one bucket of V4 on 7/8 tickers") tests *convergence with V4*, not *correctness against realized outcomes*. V4 itself has never been calibrated against 12-month realized returns. If V4 is systematically overcautious — for example, it called LITE BROKEN at $283 with a buy_below of $96, requiring a 66% drawdown before entry, on the same name Hume is treating as his reference 10x candidate — then "passing the validation" proves V3.4.3 has replicated V4's bias, not that V3.4.3 is correct. Convergence with V4 is a necessary but not sufficient validation condition. The sufficient condition is outcome-tracking through the deferred Session 6 calibration work (task #45), at minimum N≥20 thesis rows with realized return data. We are at N≈14 and at least a month away. Every recommendation in this report is provisional on that calibration.

Open questions the report cannot answer:

- Is N=8 enough to draw architectural conclusions? Probably not for absolute confidence, but the 5/8 leak rate is large enough that the direction of the conclusion is robust to noise. The specific cutoffs (0.95, 1.00, etc.) are not robust to noise.
- Will V3.4.3 prompt-game the kill rule? Empirical question for the validation re-run. The mitigation path is V3.4.3.1 — a Python post-processor that recomputes `risk_adj_ev_ratio` from the closing JSON's `risk_adj_target` and `current_price` fields and deterministically clamps `position_size_pct` and `conviction` to the table's row independent of what the LLM emitted. **This is a named follow-up commitment, not a contingent open question.** Concretely: if the V3.4.3 validation re-run shows any case where the LLM emitted a `risk_adj_ev_ratio` below 0.95 paired with a `position_size_pct` above 10%, V3.4.3.1 ships before the next watchlist refresh. The post-processor is roughly 30 lines of Python around the existing thesis-output parser — half a day of work. The red-team identified concrete gaming math (a 6 percentage point shift on one catalyst probability lifts ratio from 0.939 to 0.954, clearing the gate); this attack surface closes only when the gate moves out of the prompt and into deterministic code.
- What does V3.4.4 do when conservative / central / bull paths disagree about whether the trade is BROKEN? The kill rule operates on probability-weighted EV. If conservative says BROKEN, central says LOW, bull says MEDIUM, the weighted answer depends on the path probabilities. We have no calibration on those probabilities yet.
- Should we be running the engine and the prompt as two independent estimators and surfacing the disagreement as a signal in itself? This is a different system architecture than either V3.4.3 or V3.4.4 and is worth a separate report.

---

## Appendix A — Per-ticker raw outputs

| Ticker | Spot | V3.4.2 strategic | V3.4.2 trade conv | V3.4.2 size | V3.4.2 target | V4 state | V4 conv | V4 size | V4 target | V4 buy_below |
|---|---|---|---|---|---|---|---|---|---|---|
| MU | (varies) | HIGH | BROKEN | 0% | $910 | — | BROKEN | 0% | — | — |
| LITE | $283 | HIGH | HIGH | 25% | $1139 | AGREED | BROKEN | 0% | $96 | — |
| AXON | ~$403 | HIGH | HIGH | 25% | ~$680 | AGREED | BROKEN | 0% | $590 | — |
| AMD | $455.19 | HIGH | BROKEN | 0% | $440 | (skipped) | — | — | — | — |
| COHR | $335.26 | HIGH | MEDIUM | 25% | $476 | AGREED | BROKEN | 0% | $310 | $280 |
| ALAB | $403.54 | HIGH | HIGH | 25% | $345 | AGREED | BROKEN | 0% | $185 | $165 |
| AMAT | $435.44 | HIGH | LOW | 0% | $490 | AGREED | BROKEN | 0% | $394 | $370 |
| U | $28.16 | HIGH | MEDIUM | 20% | $38 | PROPOSING | WEAK | 10% | $29 | $22 |

Per-ticker comparison files: `data/architecture_experiments/20260510_181017/per_ticker/*.md`.

---

## Appendix B — V3.4.3 patch summary

Step 9 (rewrite): adds explicit `risk_adj_ev_ratio = risk_adj_target / current_price` calculation; names the AXON / COHR / ALAB pattern; requires defensive math rather than strategic conviction to override.

Step 12 (extension): adds clamp table mapping risk_adj_ev_ratio → max conviction, max position_size_pct. Cutoffs 0.95 / 1.00 / 1.10 / 1.25. Table OVERRIDES strategic_conviction. Cutoffs anchored on V4 outputs (COHR 0.871, AMAT 0.816, U 0.952).

Closing JSON: `risk_adj_ev_ratio` added as first-class field.

Full diff in `scripts/prompts/thesis_v3.md` git history at commits between 2026-05-10 18:30 and 2026-05-10 21:30.

---

## Appendix C — The AXON-pattern, formal definition

A stock exhibits the AXON-pattern if and only if all of the following structural conditions hold simultaneously:

1. Strategic thesis is verifiable and structural (named contracts, named market structure changes, named regulatory shifts — not generic AI narrative).
2. All five Step 1 filters pass.
3. Stock has rallied >100% in the trailing 12 months.
4. Forward multiple at current price equals or exceeds the prompt's derived thesis multiple at the prompt's modeled NTM EPS.

These four conditions define the *setup*. They are independent of any kill-rule metric.

The kill-rule metric — `risk_adj_ev_ratio ≤ 0.95` — is the *gate* applied to the setup. The earlier draft of this report folded the gate metric into the pattern definition (as a fifth condition), which made the proof "V3.4.3 catches the AXON-pattern" tautological by construction. That conflation has been removed. The honest framing is: the pattern is the structural setup; the gate is the action V3.4.3 takes on stocks matching the setup; whether the gate is the right action at the right threshold is the empirical question the validation re-run is designed to answer.

Cohort hits on conditions 1–4: AXON (May 2026), COHR (May 2026), ALAB (May 2026), LITE (May 2026), AMAT (May 2026 — borderline; conviction LOW already). Of these, all five had `risk_adj_ev_ratio ≤ 1.0` when measured: V3.4.3 would have gated all of them.

Cohort misses on conditions 1–4:
- **AMD**: V3.4.2 self-caught not via a "loss-scenario rule" but via target-derivation math at Step 5 / Step 7. The prompt computed NTM EPS $11.01 at May 2027, derived thesis target $440 ($11.01 × 40x stretch multiple), and observed spot $455.19 sat *above* the stretch-case target. The thesis target was self-refusing on price; conviction collapsed to BROKEN at the target-derivation step before the kill rule would have engaged. Step 9 then confirmed with `risk_adj_target = $393` (ratio 0.864), but BROKEN was already locked.
- **MU**: V3.4.2 produced BROKEN with target $910 vs spot in the comparison cohort. The mechanism here is unverifiable from the artifacts available at report time (no MU thesis file at the V3.4.2-comparison snapshot path). Earlier sessions credited Step 5b's cycle-position check; that attribution should be confirmed by reading the actual MU thesis output before it is treated as load-bearing evidence.
- **U**: partial pattern match — same direction (V4 throttled sizing relative to V3.4.2) but smaller magnitude (WEAK 10% vs MEDIUM 20%, not BROKEN 0% vs HIGH 25%).

The pattern is most likely to mislead V3.4.2 when filter 1 is unambiguously verifiable (visible structural change, named partnerships) and filter 5 is supportive (macro tailwind), because those filter outputs anchor the persona-split's strategic mode strongly. AXON's "Counterstrike + Lucy + AI Era platform shift," LITE's "1.6T optical transceiver ramp + NVIDIA partnership," ALAB's "PCIe 7.0 + AI server interconnect" — all three are real, verifiable, and structural. The thesis is right; the price has captured it.
