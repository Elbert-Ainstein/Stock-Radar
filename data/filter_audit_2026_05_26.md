# Filter / Gate / Criteria Audit — Stock Radar v3

**Date:** 2026-05-26
**Scope:** Every filter or threshold-gated decision in the codebase that includes or excludes data, stocks, or recommendations.
**Method:** Direct file reads + Explore-agent depth scan + cross-reference with memory and prior CHANGELOG entries.
**Companion to:** `CHANGELOG.md` (validated_corrections.md ship, §7b future-pricing validation), `filter_philosophy.md`.

---

## CORRECTION (added 2026-05-26 after publication)

The original audit categorized two files as orphaned and recommended killing them:
1. `scripts/prompts/adversarial_filter_prepass_v3.md`
2. `scripts/convergence_detector.py`

**Both calls were wrong.** Subsequent verification found:

- **`convergence_detector.py` is ACTIVE in production.** Caller: `app/api/convergence/route.ts` (Next.js API route at `/api/convergence`). The TypeScript file explicitly mirrors the Python module's logic to render dashboard panels and notes "Class taxonomy must stay in sync with scripts/convergence_detector.py — update both together." Also referenced as a CLI hint in `scripts/feed_news_to_universe.py:218`. The Python-only grep used by the Explore agent missed the TypeScript caller entirely.

- **`adversarial_filter_prepass_v3.md` is DORMANT BY DESIGN, not abandoned.** The prompt's INTEGRATION NOTES section (lines 7-16) explicitly state it is awaiting Module 8 (outcome tracker) maturity — specifically "≥20+ closed outcomes" — before being wired in as an automated gate. Until then, "treat PROCEED verdicts as preliminary research signals, not as automated buy gates." Deleting it destroys design thinking with an explicit re-entry condition.

**Lesson:** "kill" recommendations in audits require (a) cross-LANGUAGE grep, not just Python, and (b) reading the candidate file before deletion. The Explore agent's Python-only filter was insufficient. The 7-step workflow Hume specified (apply → self-review → fix/debug → review-squad → squad passes/proposes → loop → cycle report) is the discipline that catches this class of error — Cycle Report Step 7 would document the orphan-call as a "surprise" caught before destruction.

**Net effect on the audit:** the "Dead (kill)" category is empty for now. Both items should be reclassified:
- `convergence_detector.py` → KEEP (active, used by frontend convergence panel)
- `adversarial_filter_prepass_v3.md` → DORMANT (re-entry trigger: Module 8 ≥20 closed outcomes; currently 0-1, AXON T+30 is the first)

---

---

## Executive summary

The codebase contains **~25 named filters** across data, discovery, analysis, routing, and output layers. Of these:

- **15 are working correctly and should be kept** — cross-validation, EDGAR rate limit, event caps, anti-sycophancy 5%-convergence, chokepoint conditional in §7b, anti-contamination (just shipped), and similar.
- **3 are problematic and need fixes** — Module 1 recent-quarter sanity check (over-fit to mature-co bugs), forward DCF as primary signal (architecturally wrong per 2026-05-01 call), V3.4.3 kill rule (calibration uncertain).
- **2 are orphaned and should be killed or revived** — adversarial filter prepass (prompt exists, no Python caller), convergence_detector.py (utility exists, no production callers found).
- **3 are duct-tape that work for now but need replacement** — `--override-suspect-recent` flag, file-based `validated_corrections.md`, current 13F-only discovery source pool.
- **2 are calibration-uncertain (low evidence, can't yet judge)** — MIN_QUARTERLY_ROWS_NON_US = 4 (may block early-stage non-US), MIN_SIGNALS_FOR_ADJUSTMENT = 10 (feedback loop is Bayesian-shrinkage so not dead, but signal accumulation rate unknown).

**Most urgent fix:** forward DCF repositioning in `target_engine.py`. Hume's 2026-05-01 architectural decision (`user_dcf_is_wrong_primary` memory) is now 25 days old and still not reflected in code. DCF continues to drive the primary target via Gordon Growth → blended scenarios. Until repositioned, the engine systematically undershoots 10x setups — the exact asset class Hume is hunting.

**Second urgent:** kill the orphan filters. The adversarial filter prepass and convergence_detector.py both exist as code/prompts but have no production callers. Either revive them with explicit wiring + a falsifiable use case, or delete them. Dead code in a filter audit is technical debt that hides real intent.

**Third urgent:** Module 1 EDGAR validation rewrite. The current size-aware + archetype-aware tiers help but still over-fire on early-stage names where the asset class IS the volatility. The architectural fix (spot-check provider data against the most recent 10-Q from SEC EDGAR) addresses both data-bug AND early-stage cases.

---

## Complete inventory

Organized by layer. Each entry: location, what it filters, verdict.

### Data layer

| # | Filter | Location | Verdict |
|---|---|---|---|
| 1 | Module 1 recent-quarter sanity check (size-aware × archetype-aware) | `finance_data.py:287-427` | **FIX** — over-fits early-stage |
| 2 | `--override-suspect-recent` flag (escape from #1) | `run_thesis.py`, `run_socratic.py` | KEEP (as duct tape until #1 replaced) |
| 3 | `_ARCHETYPE_THRESHOLD_MULTIPLIER` (relaxes #1 per archetype) | `finance_data.py:262` | KEEP — correct design pattern |
| 4 | `CROSS_VALIDATION_WARN_THRESHOLD` = 3% | `finance_data.py:1742` | KEEP |
| 5 | `CROSS_VALIDATION_HALT_THRESHOLD` = 10% | `finance_data.py:1743` | KEEP — catches MU-style provider bugs |
| 6 | `_MIN_REQUEST_INTERVAL` = 120ms (EDGAR rate limit) | `edgar_xbrl.py:45` | KEEP — SEC compliance |

### Discovery layer

| # | Filter | Location | Verdict |
|---|---|---|---|
| 7 | `MIN_QUARTERLY_ROWS_NON_US` = 4 | `discovery_scan.py:85` | **INVESTIGATE** — blocks early-stage non-US |
| 8 | `MAX_QUARTER_GAP_DAYS` = 100 | `discovery_scan.py:86` | KEEP — detects semi-annual reporting |
| 9 | `PROMOTE_SCORE` = 7.0 (Haiku cheap-scan promotion) | `discovery_scan.py:62` | KEEP |
| 10 | `DROP_SCORE` = 4.0 + 3-consecutive-low rule | `discovery_scan.py:63-64` | KEEP |
| 11 | `MAX_MARKET_CAP_USD` = $50B (13F filter) | `discovery_13f.py:65,394` | KEEP — replaces Yahoo most-active failure |
| 12 | Discovery source pool (13F-only currently) | `discovery_13f.py` whole | **KEEP (duct tape)** — needs sector ETF + news additions per `project_discovery_source_pool_replacement` |

### Analysis / engine layer

| # | Filter | Location | Verdict |
|---|---|---|---|
| 13 | **Forward DCF as PRIMARY signal** (Gordon Growth → blended target) | `target_engine.py:84-138, 914-926, 1033-1034` | **FIX (URGENT)** — architectural call from 2026-05-01 not implemented |
| 14 | DCF multiples fallback (only when `terminal_fcf_sbc ≤ 0`) | `target_engine.py:117-121` | Symptom of #13 — fix once #13 addressed |
| 15 | `MIN_SCOUTS_HIGH_CONFIDENCE` = 4 | `registries.py:192` → `analyst.py:1034` | KEEP — flags only, no block |
| 16 | `MIN_SIGNALS_FOR_ADJUSTMENT` = 10 (Bayesian shrinkage) | `feedback_loop.py:60,416-419` | **INVESTIGATE** — non-blocking but signal-count unknown |
| 17 | `MAX_SINGLE_EVENT_PCT` = 10%, `MAX_TOTAL_EVENT_PCT` = 15% | `event_reasoner.py:47-48` | KEEP |
| 18 | `RECENCY_HALF_LIFE_DAYS` = 62 (event impact decay) | `event_reasoner.py:44` | KEEP |
| 19 | `_TAKE_MAX_KEYS` vs latest-wins partitioning | `forward_drivers.py:539-553` | KEEP — sensible partition |

### Decision / routing layer

| # | Filter | Location | Verdict |
|---|---|---|---|
| 20 | V3.4.3 kill rule (`conviction = BROKEN` when `risk_adj_ev_ratio < 0.90`) | `prompts/thesis_v3.md:170-171`, `run_thesis.py:451` | **INVESTIGATE** — calibration uncertain, prompt-driven not code |
| 21 | Auto vs Socratic routing | none (operator-invoked only) | KEEP — but worth making explicit |
| 22 | Smart routing (archetype-aware scout selection, default) vs `--full` | `run_pipeline.py:300-453` | KEEP |
| 23 | `--no-thesis` cron flag (cost runaway prevention) | scheduled job | KEEP — caught $2,160/mo runaway |
| 24 | `MAX_POSITION` = 10%, `MIN_SCORE` = 6.0, `MIN_EXPECTED_RETURN` = 2%, `MAX_POSITIONS` = 15 | `position_sizing.py:64-68` | KEEP (subject to first-time-signal 5% override per `user_position_sizing_discipline`) |

### Prompt-level filters

| # | Filter | Location | Verdict |
|---|---|---|---|
| 25 | Chokepoint conditional in §7b (gates future-pricing math) | `prompts/socratic/model_b_regime.md:45-75` | KEEP — just validated across 3 stocks |
| 26 | Anti-sycophancy 5% convergence trigger | `model_b/c_*.md` operator-notes hard rules | KEEP — validated LITE id=19, id=21 |
| 27 | Anti-contamination rule (cites validated_corrections) | all 5 socratic prompts | KEEP — just shipped 2026-05-26 |
| 28 | strict-fill guard (`fill(strict=True)`) | `run_socratic.py:91` | KEEP — catches integration bugs |
| 29 | Adversarial filter prepass | `prompts/adversarial_filter_prepass_v3.md` | **KILL or REVIVE** — orphaned (no Python caller) |
| 30 | `convergence_detector.py` cross-source scoring | `convergence_detector.py:124-260` | **KILL or REVIVE** — orphaned (no production callers found) |

---

## Per-filter findings (depth)

### 1. Module 1 recent-quarter sanity check — FIX

**Location:** `finance_data.py:287-427` (`_validate_quarterly_revenue` and `_validate_and_build` around line 660-705).

**Actual thresholds (more sophisticated than I knew):**

| Quarterly revenue scale | Trailing-4Q multiplier | YoY multiplier |
|---|---|---|
| Large-cap (≥$500M/Q) | 2.0x | 2.5x |
| Mid-cap ($100M-$500M/Q) | 3.0x | 4.0x |
| Micro/small-cap (<$100M/Q) | 5.0x | 6.0x |

PLUS archetype multiplier: `cyclical_tech` 1.5x, `cyclical_industrial` 1.4x, `cyclical_normalized` 1.5x, `secular_growth` / `compounder` 1.0x.

**What happens when triggered:** if suspect quarter is in TTM_QUARTERS (last 4), `_validate_and_build` raises `EarningsFetchError` unless `override_suspect_recent=True`. Soft warnings emitted on older suspect quarters but don't block.

**Why this is over-fit for early-stage:** consider ASTS post-BlueBird launch with revenue going $1M → $50M. That's a 50x quarter-over-quarter ramp from a near-zero baseline. Even with the 5.0x small-cap threshold + 1.5x cyclical multiplier (would need archetype tag, ASTS doesn't have one) = 7.5x — still trips on a 50x ramp. The size-aware tiers help on mature small-caps but **the actual asset class Hume is hunting (commercial-launch ramps) routinely trips the guard**. Override flag is the duct tape.

**Architectural fix:** Replace the trajectory-smoothness heuristic with provider-vs-EDGAR cross-check. The real question is "does the provider's number match the 10-Q?" not "is the trajectory smooth?" Memory `feedback_data_guardrail_over_fit` is the design doc.

**Effort estimate:** ~1-2 days. Need EDGAR client (already exists in `edgar_xbrl.py`), need sampling strategy (check most recent quarter only? or all 8?), need fallback for stocks without EDGAR filings (Israeli, Taiwanese, Korean listings).

---

### 13. Forward DCF as primary signal — FIX (URGENT)

**Location:** `target_engine.py:84-138` (Gordon Growth terminal value), `914-926` (multiples computed in addition, not instead), `1033-1034` (`terminal_ev_blended` weighted blend).

**Current state:** DCF is the primary path. Multiples are computed alongside but contribute to a blended terminal EV. Exit multiples are used as the SOLE source only when `terminal_fcf_sbc ≤ 0` — i.e., the rare case where FCF is non-positive.

**Memory `user_dcf_is_wrong_primary` (2026-05-01):** "forward DCF structurally undershoots 10x setups (trough/regime/compression/re-rating); reposition as downside floor only; thesis + scouts are likely real primary signal."

**Where the gap shows up:** the §7b future-pricing analysis Model B just shipped does the right thing — it treats DCF as a fair-value reference and primarily evaluates priced-years vs actual-years gap. But `target_engine.py` (which feeds the Auto mode in `run_thesis.py`) still produces DCF as the primary output. So Auto mode and Socratic mode disagree architecturally on how to use DCF.

**Concrete consequence:** when Auto mode runs (overnight cron, scheduled scans), it produces DCF-based targets that systematically undershoot regime-shift candidates. Per `user_auto_vs_socratic_division`, Auto is supposed to be mean-revert-only — but if the only mode for surfacing 10x candidates is Socratic, and Socratic is manually invoked, then the system has no automated path for spotting them. The 10x candidates only get found if Hume manually triggers Socratic, which means the engine isn't actually doing the job Hume built it for.

**Architectural fix proposal:**
1. Add a `dcf_role` field to `ScenarioResult` with values `"primary"` | `"downside_floor"` | `"reference_only"`.
2. Default `"downside_floor"` for `early_revenue_ramp` and `pre_revenue` archetypes.
3. Default `"reference_only"` for `secular_growth` with high momentum (r12mo > 2.0).
4. Keep `"primary"` for `cyclical_tech`, `compounder`, and stable margin businesses.
5. When `dcf_role` ≠ `"primary"`, the final target comes from scenario-weighted blend of scouts' forward signals + thesis-derived multiples, with DCF used as the BEAR floor only.

**Effort estimate:** 2-3 days. Risk: this is a load-bearing refactor that affects every Auto mode run. Per `feedback_engine_complexity_ratchet`, the prior 17-fix doubled error rate on LITE. The right discipline is to ship it as a flag-gated path first (`--dcf-as-floor` flag), validate against 3+ stocks where we have prior reads (LITE, CAMT, COHR), and only then switch the default.

**Pass criterion for the fix:** re-run Auto mode on LITE with `--dcf-as-floor`. Expected: target output references "fair-value floor: $X (from DCF, used as downside)" alongside the primary target from scout-blended forward signals. The primary target should be materially higher than the prior DCF-primary number on regime-shift names.

---

### 20. V3.4.3 kill rule — INVESTIGATE

**Location:** PROMPT-driven, not Python code. `prompts/thesis_v3.md:170-171` defines the trigger; `run_thesis.py:451` handles the downstream effect.

**Trigger:** `conviction = BROKEN` when `risk_adj_ev_ratio < 0.90` (probability-weighted target less than 10% above entry).

**Action:** Sets `position_size_pct = 0%`. Soft skip — doesn't raise an error, just emits a recommendation of "do not buy." Does NOT block analysis from running.

**Calibration uncertainty:** Memory `project_lite_canary` says V4 called LITE BROKEN at $283 with buy_below $96 (66% drawdown required) — and we now know from id=21 §7b math that LITE's pure-DCF fair value at moat-closure is $290-$350. So V4 was directionally right that LITE is overpriced relative to a strict DCF lens — but the implied buy_below of $96 was way off (Hume entered at $70, was up to $946.90 at time of LITE id=21 analysis). The "kill rule fires" event and "next 90 days outcome" both happened; the kill rule prevented buying LITE at $283 but said NOTHING about the actual upside path (entry $70 → $946.90 = +1,253%).

**This is the DCF-as-primary problem expressed as a kill rule.** When `risk_adj_ev_ratio` is computed using DCF-derived targets, the kill rule fires on every regime-shift candidate before the thesis is allowed to play out. Per memory `feedback_foundation_vs_calibration_test`: if the kill rule fires and refused stocks go up 50%+, foundation is wrong not calibration.

**Recommended action:** Don't touch the kill rule until DCF repositioning (filter #13) is done. Once DCF is moved to "downside floor" role for regime-shift archetypes, re-evaluate the kill rule with the new target computation. If it still fires on regime-shift candidates, the trigger logic needs widening.

**Cross-check available now:** compare LITE id=21 §7b math (pure DCF fair value $290-$350, practical floor $570, conditional ceiling $1,280) against the V3.4.3 kill rule output on LITE. If V3.4.3 still says BROKEN, the kill rule is using a narrower fair-value definition than Socratic does — that's the smoking gun.

---

### 29. Adversarial filter prepass — KILL or REVIVE

**Location:** `prompts/adversarial_filter_prepass_v3.md` exists. Grep for Python callers returns zero hits.

**State:** Orphaned. The file is in the repo, the prompt is fully written, but nothing in production code loads it.

**History (from memory `project_methodology_pre_session_1`):** This was listed as one of 4 prerequisites before the run_thesis.py methodology build. It was a pre-Session-1 work item. Either it was never wired in, or it was disconnected during refactoring.

**Two options:**
1. **KILL:** Delete the file. Note in CHANGELOG that the prepass was deprecated.
2. **REVIVE:** Wire it in with explicit purpose. Where would it fit? Logically: as a Phase 0 step in `run_thesis.py` that pre-filters tickers via adversarial review BEFORE the full thesis run, saving Sonnet spend on tickers that obviously fail.

My read: KILL unless Hume has a specific intent. Dead prompts that look authoritative are worse than no prompt — they create the impression that the system does something it doesn't.

---

### 30. convergence_detector.py — KILL or REVIVE

**Location:** `convergence_detector.py` (the whole file, ~261 lines). Public API `detect_convergence()` at line 124-192. `main()` CLI entry at line 213-260.

**Purpose:** Cross-source convergence scoring — ranks discovery_universe candidates by how many independent signal classes (not raw tags) flagged them.

**State:** CLI-invokable (`python convergence_detector.py`) but no callers in `run_pipeline.py` or other production scripts. The function exists as a utility but isn't on any automated path.

**Recommendation:** KILL or REVIVE. If multi-source convergence is part of the discovery ranking, it should be wired into `run_pipeline.py`. If it isn't, delete. Same logic as the adversarial prepass.

---

### 7. MIN_QUARTERLY_ROWS_NON_US = 4 — INVESTIGATE

**Location:** `discovery_scan.py:85,153-164`.

**Logic:** For non-US tickers (`.HK`, `.T`, `.TW`, etc.), if fewer than 4 quarterly rows exist OR any consecutive gap > 100 days, the ticker is SKIPPED with a 24-hour retry cooldown.

**Concern:** A recently-IPO'd Taiwanese / Korean / Israeli / Hong-Kong-listed name with 2-3 quarters of post-IPO data would be EXCLUDED. No archetype-aware bypass.

**Specific risk:** Tower Semiconductor (TSEM) was found by user not engine per memory `user_lite_2026_05_23_thesis` lateral-trace observation. If similar early-stage non-US discovery candidates are being silently excluded by this filter, the discovery layer is doing its own equivalent of Module 1's over-fit problem.

**Pass criterion:** count how many non-US tickers got skipped with reason "fiscal-calendar guard tripped" in the last 30 days of runs. If that count is >5 and any of them are interesting (small-cap, fast-growing, in a wave), the filter needs to be relaxed for non-US early-stage names — e.g., bypass to 2 quarters when archetype is `early_revenue_ramp`.

**Effort estimate:** few hours to add an archetype bypass + count the skipped-tickers retroactively from logs.

---

### 16. MIN_SIGNALS_FOR_ADJUSTMENT = 10 — INVESTIGATE

**Location:** `feedback_loop.py:60,416-419`.

**Behavior:** Bayesian shrinkage with `PRIOR_STRENGTH=50` (line 54). Below 10 signals, prior probability dominates and scout weights stay near defaults. Above 10, scouts get adjusted.

**Concern:** The feedback loop is supposed to learn which scouts are accurate over time. If the system has fewer than 10 outcome-settled signals per scout, the learning loop is effectively dormant.

**Per memory `project_axon_first_signal` (2026-05-09):** AXON was the first end-to-end system signal acted on at 5%. T+30 is ~2026-06-08. We're still pre-outcome on AXON. LITE has prior outcomes from id=15 → id=19 → id=21 but those are within-engine refinements, not closed bets. So **the signal store likely has very few settled outcomes**, meaning every scout is currently at prior probability.

**Action:** Run a one-liner count against the signals table (`signal_outcomes` if it exists). If signals per scout < 5, the feedback loop is effectively prior-only and there's no calibration happening. That's fine as a starting state but means the "system learns from outcomes" claim is currently aspirational.

**Not a fix needed** — Bayesian shrinkage with low signal is the right behavior. But Hume should know the feedback loop isn't doing anything yet.

---

## Critical findings (surprises)

### Finding 1: Auto mode and Socratic mode use DIFFERENT valuation frameworks

Auto (`run_thesis.py` → `target_engine.py`) uses DCF as primary. Socratic (`run_socratic.py` → §7b future-pricing) uses priced-years vs actual-years gap with DCF as a fair-value REFERENCE.

**These can disagree by 2-3x** on the same stock. LITE id=21 §7b said: pure DCF fair value $290-$350, practical target_low $570, conditional target_high $1,280. Auto mode on LITE would produce something near the $290-$350 figure as PRIMARY — and then the V3.4.3 kill rule fires on it as BROKEN.

**This is the core architectural divergence.** Two engine modes producing two different answers to "what is this stock worth," with no clear ownership of which is canonical.

### Finding 2: The kill rule is DCF-locked, not engine-locked

V3.4.3 kill rule fires on `risk_adj_ev_ratio` which is computed from DCF-derived targets. If DCF is structurally biased (per `user_dcf_is_wrong_primary`), the kill rule inherits that bias. Fixing the kill rule independently of DCF repositioning is whack-a-mole.

### Finding 3: Two orphan filters exist as code/prompts but have no callers

`adversarial_filter_prepass_v3.md` and `convergence_detector.py`. These look authoritative if you grep the repo but they don't run. Cleanup is needed.

### Finding 4: The feedback loop is effectively prior-only

`MIN_SIGNALS_FOR_ADJUSTMENT = 10` means scouts need 10 settled outcomes before adjusting. With AXON as the first signal (T+30 ~2026-06-08), the system is months away from having ANY scout adjusted by outcomes. The "system learns" claim is aspirational, not current.

### Finding 5: Module 1's size-aware tiers are MORE sophisticated than I knew, but still miss the asset class

I knew Module 1 had 5x/6x thresholds. The actual logic is size-aware (2.0/2.5 large-cap, 5.0/6.0 small) × archetype-aware (1.4-1.5x for cyclicals). That's a sensible tiered design for mature companies of varying sizes. But early-stage commercial-launch ramps (ASTS, RKLB, PL, IONQ pre-revenue) DO trip the small-cap threshold even with archetype multiplier (which they may not even have). The right fix is provider-vs-EDGAR cross-check, not more relaxed thresholds.

---

## Prioritized recommendations

Ordered by leverage × scope, with explicit re-entry conditions:

### Tier 1: Build now

1. **Reposition forward DCF (filter #13).** Add `dcf_role` field to `ScenarioResult`. Default to `"downside_floor"` for `early_revenue_ramp` / `pre_revenue` archetypes, `"reference_only"` for high-momentum secular_growth, `"primary"` for cyclical/compounder. Ship as `--dcf-as-floor` flag first; default-switch only after validation. **Pass criterion:** re-run Auto mode on LITE — primary target should be materially above the prior DCF-primary number; DCF should appear as "downside floor: $X" in output. **Why it matters:** unblocks Auto mode from being a 10x-blind engine, eliminates the architectural divergence with Socratic. **Effort:** 2-3 days, real risk of regression per `feedback_engine_complexity_ratchet` — ship behind flag.

### Tier 2: Build next (1-2 weeks)

2. **EDGAR validation rewrite (filter #1 replacement).** Replace Module 1's trajectory-smoothness heuristic with provider-vs-10-Q cross-check using existing `edgar_xbrl.py` client. **Pass criterion:** ASTS at commercial launch (Q-over-Q ramp from near-zero) passes without override flag. **Effort:** 1-2 days.

3. **Kill orphan filters (#29, #30).** Delete `prompts/adversarial_filter_prepass_v3.md` and `scripts/convergence_detector.py` unless they have a defined purpose in current pipeline. **Effort:** 30 minutes. **Pass criterion:** repo grep for these names returns zero hits in active code paths.

4. **Investigate kill rule against Socratic (filter #20).** Run V3.4.3 kill rule against current LITE inputs and compare to LITE id=21 Socratic output. If kill rule says BROKEN while Socratic shows a real path to upside, the rule needs widening. **Effort:** 1 hour.

### Tier 3: Investigate and decide later

5. **Non-US discovery bypass (filter #7).** Add archetype-aware bypass to `MIN_QUARTERLY_ROWS_NON_US`. Defer until you have a specific non-US early-stage name you want to track that's being blocked. **Effort:** 2 hours. **Trigger condition:** any non-US ticker with <4 quarters shows up in lateral-trace discovery and gets blocked.

6. **Signal-store census (filter #16).** Count current settled outcomes per scout. If < 5 per scout, document that the feedback loop is dormant until AXON / LITE T+30/90 outcomes settle. Not a fix; a status check. **Effort:** 30 minutes.

### Tier 4: Don't touch

All filters marked KEEP are currently working as designed. Don't ratchet (per `feedback_engine_complexity_ratchet`).

---

## Open questions for Hume

1. **DCF repositioning:** is the flag-gated rollout acceptable, or do you want it to be a direct switch? Direct switch is faster but riskier given prior 17-fix doubled-error episode.

2. **Orphan filters:** do `adversarial_filter_prepass_v3` or `convergence_detector` have a use case you're holding for them, or are they really dead? If dead, ship the delete commit.

3. **Kill rule:** if V3.4.3 calls LITE BROKEN at $283 (so refusing to buy) and Socratic at $946 produced REGIME_DOWNSIDE but also said target_high $1,280 conditionally — does the kill rule's "do not buy" output match what you'd have done at $283? If yes, the rule is working. If you would have bought LITE at $283 and the rule blocked you, the rule is over-firing.

4. **Tactical signals (§10b):** the ASTS gamma squeeze is a real example. Should I open this as a Tier 2 item once the DCF repositioning ships? The architecture is designed; the question is whether your $70 cost basis on ASTS came from a tactical-then-thesis transition or pure thesis entry.

5. **Position sizing constants (filter #24):** `MAX_POSITION = 10%`, `MIN_SCORE = 6`, `MAX_POSITIONS = 15`. These look reasonable. Per `user_position_sizing_discipline`, you size first-time system signals at 5% (tracking) not the engine-recommended 20-35%. Should the engine's position sizing be lowered to 5% default for first-time signals, with 10% only available after T+30 confirming events?

---

## Status of the 3-item agreed queue + this audit

| Item | Status |
|---|---|
| §7 anti-sycophancy (Model B) | SHIPPED + VALIDATED (LITE id=19) |
| §6 macro injection | ALREADY SHIPPED (id=19 stdout) |
| §7b future-pricing | SHIPPED + VALIDATED (LITE id=21, CAMT id=22, COHR id=23) |
| Contamination fix (validated_corrections.md) | SHIPPED, awaiting COHR re-run |
| Filter audit (this report) | DELIVERED |

The deferred items from session 2 doc (Model D, lateral trace, expectations decomposition §7c, tactical/thesis split §10b, revolution impact spectrum §10, 灵感 mode, 影响图谱 frontend) remain deferred unless explicitly triggered.

**Net new from this audit:** 3 Tier 1/2 items added to the queue (DCF reposition, EDGAR rewrite, orphan kill) — but these are observation-driven, not speculation-driven. They address real findings, not architectural wishlist.
