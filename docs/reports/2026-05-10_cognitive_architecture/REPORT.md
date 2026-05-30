# Cognitive Architecture — Frame-Flexible Humans vs Frame-Locked LLM

**A working note on why the system refuses trades a credible human will take, what that reveals about the cognitive gap, and what minimum change closes it without recapitulating architectures we've already killed.**

Date: 2026-05-10
Author: Stock Radar working notes
Status: v3 — post-squad-review-of-recommendation. Squad review of Hume's 2026-05-11 recommendation produced five must-fix and three should-fix items; all eight applied in this revision. Most consequential change: the "add `regime_shift` archetype" framing has been replaced with "leverage existing `transformational` archetype + Step 5 prompt block" after a code inspection confirmed `transformational` is already substantively wired through the engine. Cost-of-fix estimate dropped from "100 lines / half day" (claimed) or "300-500 lines / multi-day" (squad worst-case) to ~30-50 lines of prompt language plus a tagging step.

Other v3 fixes: Section 7 vs Section 10 Proposal D contradiction resolved (record-only is canonical, post-JSON-comparison design retracted); NVDA P/E anchor corrected from "60x sustained 2023-2024" to "peak NTM forward ~59x mid-2025"; memory chip P/E phrasing clarified (peak earnings = compressed P/E denominator, so peak-cycle P/E is LOW 6-12x and trough P/E is HIGH); archetype taxonomy actual count surfaced (5 in ticker_archetypes.json README + 5 in registries.py ALL_ARCHETYPES); N=14 corrected to N=17; "replaces the ratchet" weakened to "reduces ratchet pressure"; disconfirming-case + outcome-status-tag required for any future lessons.md entry; calibration trigger fallback "whichever comes first: N≥20 OR 2026-10-01" added.

v2 changelog preserved below.

Status: v2 — post-evidence-update. Same-day addition of two new data points materially strengthens the null hypothesis (Section 4.5) and reshapes Section 10's recommendation. v1 changelog preserved below.

**v2 evidence additions:**
- AMD-vs-Evercore disagreement (`project_amd_evercore_disagreement.md`): Evercore ISI projects AMD revenue 60-77% above the system's V3.4.3 build for 2026-2027. Indicts Step 4 (revenue trajectory) where the LITE case indicted Step 5 (multiple anchor). Two cases now, two different parts of the prompt, same conservative-by-design failure mode.
- Sector taxonomy spec (`project_sector_mapping_scout_spec.md`): Hume's hand-curated 14-theme map with tier-1/tier-2 constituents and explicit position-risk callouts is exactly the shape a sector-mapping scout should produce — concrete evidence that the scout layer's frame-flexibility extends beyond what current scouts produce.
- Result: Section 10 now names a **regime-shift archetype carve-out** as the cheapest available pre-built fix, with explicit triggers tied to AMD/LITE/AXON outcomes.

**v1 changelog (preserved):** Four must-fix items applied (Proposal B cut for structural contradiction with Section 8; null hypothesis named explicitly in Section 4.5; frame count corrected from "at least seven" to eight with non-exhaustive caveat; LITE $960 derivation corrected from "apparent" to explicit $19.20 × 50x). Three should-fix items applied (defined "credible" trust-relationship framing; resolved "same underlying facts" contradiction; added structural safeguards on Proposal D against sycophancy/bias-absorption).

**What survived squad scrutiny + v2 update:** the three-regime taxonomy (where the gap matters); the diagnosis that the scout layer's frame-flexibility is bottlenecked at the prompt; Proposals A/C/D as deferred candidates pending outcome data; the discipline of not modifying the prompt before outcomes resolve.

**The hypothesis that strengthened most:** the null hypothesis from Section 4.5 went from "supported by one case" to "supported by two cases attacking two different prompt steps." That tilts the priority ordering: the regime-shift archetype fix is now the standby intervention to have pre-spec'd, with cognitive-architecture work (Proposals A/C/D) as the second-line response if the archetype fix proves insufficient.

Trigger: Hume's LITE-vs-dad disagreement on 2026-05-10, after the V3.4.3 validation matrix produced BROKEN on LITE at $903.80 while a human investor whose judgment Hume trusts based on prior track record (his father) views the same stock as a 2x next year. The word "credible" in subsequent references is shorthand for that trust relationship; it is not a claim about absolute prediction accuracy — the father may turn out to be right or wrong, and that resolution is the diagnostic test, not a premise of this report.

---

## Executive summary

The Stock Radar thesis prompt processes a stock through a **linear, sequential, 12-step procedural pipeline**: research → filters → revenue build → margin build → EPS → multiple → cycle check → NTM EPS → target → risks → catalysts → conviction. Each step's output is the next step's input. The pipeline is deterministic in its frame: the LLM is asked to wear one analytical hat at a time and proceed in order.

A human investor evaluating the same stock does not work this way. The credible human investor in the LITE case is almost certainly running something closer to **multi-frame integration**: pattern-recognition against prior similar setups, intuitive sentiment-reading, integration of management credibility cues, cross-domain analogy to other regime-shifts (NVDA 2023, ASML pre-EUV, etc.), positioning awareness (what credible peers are doing), and narrative-momentum sensing — *all happening more or less in parallel, with the human able to switch frames mid-evaluation when something doesn't fit.*

The gap is not "humans use intuition, LLMs use logic." Both can be rigorous. The gap is **frame-flexibility**: the human can pull from many distinct cognitive modules and switch between them adaptively; the LLM, as currently prompted, can only pull from the modules the prompt names, in the order the prompt specifies.

This matters for Stock Radar specifically because the system's stated purpose is finding 10x candidates — by definition, candidates where the conventional 12-step framework will either fail to surface them (Tier 1: filters partial, evidence early) or will undervalue them (Tier 2: the system computes a conservative-by-design EPS path and applies a mean-reverting multiple, missing regime shifts). The LITE case is the second pattern in real time.

Two things should be read before the rest of this note:

1. **The killed-architectures memory is load-bearing here.** On 2026-05-01 we killed a proposed multi-agent council architecture (`feedback_council_architecture_killed.md`) after squad review. The default for ensemble architectures is "no" until the existing system has been used on a real decision. This note is *not* arguing for resurrecting council. It is arguing for something narrower.

2. **The complexity-ratchet memory is also load-bearing.** Per `feedback_engine_complexity_ratchet.md`, 17 engine fixes once doubled error. Adding cognitive-architecture machinery to an already 12-step prompt needs a clear leverage argument. The minimum-change proposal at the end of this note is designed against that constraint.

---

## Section 1 — The triggering case

On 2026-05-10 at 22:37 UTC, the V3.4.3 thesis prompt produced this output for LITE at $903.80:

- thesis_target: $960
- risk_adj_target: $753
- risk_adj_ev_ratio: 0.833 → BROKEN bucket
- strategic_conviction: HIGH (the structural thesis is real)
- conviction (trade-level): BROKEN
- position_size_pct: 0
- buy_below: $750

The same evening, Hume reported that his father — described as a very credible investor — views LITE as a 2x next year (implied target ~$1,800).

Both judgments start from the same public financial data — LITE's FQ3 FY26 revenue $808M (+90% YoY), FY27 guidance, $42B backlog through 2028, NVIDIA partnerships, AI-optical-interconnect positioning. The father almost certainly supplements that data with inputs the system does not have (management credibility from prior cycles, peer-positioning awareness, cross-domain analogies to other regime shifts, narrative-stage sensing). So "same underlying facts" is true in the narrow sense of audited financials and public guidance; it is false in the broader sense of total information set. The disagreement is partially about cognitive processing and partially about input asymmetry. Both are real.

The system's $960 is derived transparently in the thesis file: forward NTM EPS at May 2027 = $19.20 (built up quarter-by-quarter through FY27) × 50x (the +25% carve-out ceiling above the 40x mid-historical anchor) = $960. The $13.30 figure cited above is the *current-date* NTM EPS used for the Step 5b cycle-position check ("the stock is ALREADY trading at 1.5x my thesis multiple"), not the forward NTM EPS at target date. The system's reasoning is internally consistent end-to-end: it builds forward EPS quarterly, applies a carve-out-ceiling multiple, and produces a target. The math says LITE is fairly valued at the carve-out ceiling and overvalued above it.

The father's $1,800 requires *some combination* of higher NTM EPS, higher sustained multiple, or both. Specifically: NTM EPS $20-26 × multiple 70-90x. Both inputs would need to land meaningfully above the system's central estimates.

The question this report exists to engage with is *not* "who is right" — outcome data settles that at T+90. The question is **what cognitive differences produce that 88% gap on identical inputs, and what does the gap tell us about the system's architecture.**

---

## Section 2 — What "frames" humans actually use

The cognitive-science literature on expert intuition is not vague hand-waving. Gary Klein's recognition-primed decision (RPD) model documents that domain experts — firefighters, military commanders, chess masters, ICU nurses — do not enumerate options and weigh probabilities in time-pressured situations. They pattern-match the current situation against a library of prior situations and select an action by recognition, then mentally simulate it to check for failures. Tetlock's superforecasting work shows the same trait in a different domain: the best forecasters are characterized by *cognitive flexibility* — switching frames, considering many angles, the "dragonfly eye" of multiple parallel perspectives. Munger's lattice-of-mental-models advocates explicit multi-frame thinking as a deliberate practice.

The implication: skilled investment judgment is not a single procedure with substitutable inputs. It is the dynamic integration of multiple distinct cognitive frames.

In the LITE case, the father is almost certainly running some combination of:

**Pattern-recognition frame.** This setup looks like X prior setup. Optical 1.6T ramp + NVIDIA partnership + sold-out backlog looks like NVDA 2023 (regime shift, multiple sustained at 60x for two years), not like LITE 2017 (3D sensing cycle that compressed from 80x to 35x). The frame pulls from memory of similar pattern-instances and asks: which historical analog is closer?

**Sentiment / positioning frame.** Where are the smart-money investors positioned? What is the institutional vs retail split? Are credible peers (other dad-class investors) long, neutral, or short? This frame integrates social signal in a way the system has no input for.

**Management-credibility frame.** Lumentum's CEO and CFO have or haven't earned credibility through prior cycles. Guidance has or hasn't been conservative historically. This frame is qualitative and human-readable; the system can ingest analyst quotes but not the meta-judgment "this CEO consistently under-promises."

**Narrative-momentum frame.** Is AI optical interconnect becoming the consensus narrative, or has consensus already formed and now we're in the late-narrative phase? Narratives drive multiples; the system measures multiples but doesn't model narrative state.

**Cross-domain analogy frame.** Has anything analogous happened in adjacent industries? Memory chips during the 2020-2021 supercycle? ASML pre-EUV-acceptance? The frame pulls from non-LITE knowledge and tests "does the same dynamics apply here?"

**Adversarial frame.** What would a credible bear say? What's the strongest case I'm wrong? Run that case through and check whether it lands. This is the steel-man frame; humans switch into it deliberately as a check.

**Mental-simulation frame.** Imagine it's 12 months from now and LITE is at $1,800. What had to be true to get there? Run that backward. Does the path feel achievable or does it require multiple unlikely things to compound?

**Quick-math frame.** Sometimes the answer is "$42B backlog ÷ 4 years ÷ current shares = X earnings power, multiply by Y multiple = price ≈ Z." Back-of-envelope, fast.

That's eight distinct cognitive frames in the list above, and the list is not exhaustive — Section 9 names four additional candidates (regulatory, supply-chain, customer-concentration, technical-chart). The specific enumeration is not load-bearing; the structural claim is that skilled investors run *several* of these in parallel during a 5-minute consideration of a stock and integrate the outputs. When two frames disagree, that disagreement *is the signal* — it tells the human where to dig deeper. The taxonomy is illustrative, not derived; squad review correctly flagged that Klein/Tetlock/Munger support the meta-claim (experts switch frames) but do not validate this specific list, and that caveat applies throughout the rest of the report.

---

## Section 3 — What the 12-step prompt does

The thesis prompt at `scripts/prompts/thesis_v3.md` runs essentially one frame: **the analytical-fundamental frame**. Within that frame it is rigorous. Step 5's multiple selection has historical-peak anchoring, carve-out ceilings, comp tables, and explicit structural-headwind incorporation. Step 8's risk enumeration has minimum-weight rules for required loss scenarios and probability-base-rate defenses. Step 9 now computes risk-adjusted EV and gates conviction on the ratio (V3.4.3).

But the prompt does *not* run:

- *Pattern-recognition frame* in any structured way. The memory section at Step 0 contains prior thesis runs on the same ticker, but it does not contain a library of analogous setups across tickers. The LLM might reach for analogies in its general training but it has no curated "this looks like NVDA 2023" reference set.
- *Sentiment / positioning frame.* No 13F holder list, no options skew, no short-interest delta in the input. (Short interest as a static number is in the research output but not as a dynamic frame.)
- *Management-credibility frame.* The prompt asks for management's beat/miss track record at Step 2 but does not maintain a per-CEO credibility scorecard or qualitative read.
- *Narrative-momentum frame.* No measure of where in the narrative-cycle a name sits. The cycle-position check at Step 5b is a quantitative momentum check (12-month return), not a narrative-stage check.
- *Cross-domain analogy frame.* The historical-peak anchor uses *same-sector* peers explicitly and forbids different-sector analogies. This is the right defense against weak analogies but it also closes off legitimate regime-shift framings (NVDA's CUDA moat was different-sector but analogically informative for ASML's EUV).
- *Adversarial frame.* Step 8's loss scenarios partially serve this but they are framed as risks to enumerate, not as a steel-man counter-thesis to take seriously.
- *Mental-simulation frame.* The catalyst list at Step 10 names upside events as probabilistic deltas, not as alternate forward paths to fully simulate.
- *Quick-math frame.* Done within the prompt but only in the framing the prompt prescribes.

So the system runs one frame (analytical-fundamental) with several internal checks. Humans run multiple frames in parallel with cross-frame integration. The asymmetry is structural, not just a matter of the prompt being too short.

---

## Section 4 — Where the gap matters most

The gap doesn't matter everywhere. For mean-reverting setups — commodity cyclicals at peak, secular names with verified theses already priced in (the AXON-pattern) — the analytical-fundamental frame is sufficient. The kill rule in V3.4.3 is well-calibrated for these. The 5/8 BROKEN signals in today's validation cohort (MU, LITE-arguably, AMD, COHR, AMAT) are all in this regime, and the analytical frame correctly produces BROKEN.

The gap matters in three specific regimes:

**Regime 1: Tier 1 early-stage candidates** (per `project_tier1_tier2_architectural_gap.md`). The prompt requires all five filters to pass with structural evidence. A Tier 1 candidate fails Step 1 by construction. The frames a human uses to identify Tier 1 — pattern-recognition against prior 10x's at similar stages, narrative-emergence sensing, positioning awareness ("smart money is starting to nibble") — are not available to the system. The 13F / insider / news scouts produce the *data* for these frames but the prompt has no frame to consume them.

**Regime 2: Regime shifts** (per `user_dcf_is_wrong_primary.md`). When a sector or company is transitioning from one valuation regime to another (3D sensing → AI optical, traditional foundries → AI accelerator-driven foundries, etc.), the historical-peak anchor at Step 5 is anchored to the wrong regime. The cross-domain analogy frame is the one that catches this. The prompt explicitly forbids that frame ("Analogies to different-sector monopolies ... are NOT valid justification for commodity / cyclical / multi-vendor companies"). The forbid-rule is correct as a guard against weak analogies but it also rules out legitimate regime-shift framings.

**Regime 3: Live human-system disagreement** (the LITE-vs-dad case). When a credible human disagrees materially with the system's output, the disagreement itself is high-information. The system has no mechanism to incorporate that disagreement as data — to ask "what frame is the human using that I don't have access to?" — and produce an updated answer that reflects the disagreement.

The LITE case sits at the intersection of Regime 2 (potential regime shift from optical-cyclical to AI-infrastructure-component) and Regime 3 (credible human disagreement). The system is doing what it's designed to do; the design has known blind spots in these regimes.

### The uncomfortable null hypothesis (strengthened in v2 by a second case)

Three independent squad reviewers landed on the same reading of this report, and it has to be named directly rather than routed around: **the simplest explanation for the LITE-vs-dad disagreement is that V3.4.3 is systematically conservative on regime-shift names, not that the system has a sophisticated multi-frame cognitive gap.** As of v2 there are now two cases supporting this hypothesis, each attacking a different step of the prompt:

**Case 1 — LITE-vs-dad: Step 5 (multiple anchor) failure.** The Step 5 multiple anchor uses same-sector historical peaks with a +25% carve-out ceiling. For LITE, that anchor is the optical-component cycle (LITE 2017: 80x → 35x compression; JDSU 2000: 80-90% decline) plus a 25% carve-out, capping the multiple at ~50x. The thesis target $960 is computed with $19.20 NTM EPS × 50x (exactly the carve-out ceiling). If the regime has genuinely shifted from optical-component-cyclical to AI-infrastructure-component, the right anchor is not optical 2017 but a regime-shift comp set — NVDA's NTM forward P/E peaked near 59x in mid-2025 (trailing P/E ran 80-138x in 2023-2024 because earnings were catching up rapidly to price); ASML pre-EUV-acceptance ran 35-45x; ARM-architecture transition tickers ran similar. Under a 55x anchor, $19.20 × 55x = $1,056. Under the more aggressive "this is no longer the same business" framing the carve-out rule explicitly forbids without a structural-change defense, $19.20 × 65x = $1,248, approaching the father's $1,800 range — though even that gap suggests Step 4 (revenue) is undershooting too, not just Step 5.

**Case 2 — AMD-vs-Evercore: Step 4 (revenue build) failure.** The Step 4 quarterly revenue build anchors to AMD's historical sequential growth and lets growth decay smoothly through FY27. The system produced FY26 = $47.45B and FY27 = $62B. Evercore ISI's same-week projection is FY26 = $77B (+62%) and FY27 = $110B (+77%). If Evercore's trajectory is even directionally right, system FY27 NTM EPS undershoots by 40-80%. Applied through the system's other assumptions held constant: AMD target moves from $440 to somewhere in the $700-1,000 range, and the BROKEN call at $455 flips to MEDIUM or HIGH. The Step 4 failure mode is structurally identical to the Step 5 failure mode — both rules anchor to historical patterns and apply mean-reverting decay, which is right for mean-reverting setups and wrong for regime shifts.

**The cumulative diagnosis:** the system has *conservative-by-design assumptions at both the EPS-build layer and the multiple-anchor layer*, and they compound on regime-shift names. The kill rule mechanism is fine; the inputs feeding the ratio are systematically too pessimistic. This is the foundation-vs-calibration question (`feedback_foundation_vs_calibration_test.md`) at its sharpest.

**If this null hypothesis is true, Proposals A/C/D in Section 7 are correct but insufficient.** They route existing scout/engine outputs to the prompt better, but they do not touch the rules that produce conservative revenue and multiple assumptions. **And — critically, surfaced after the v2 draft via code inspection — the fix does not require adding a new archetype.** The existing `transformational` archetype in `registries.py` ALL_ARCHETYPES is already substantively wired through the engine: 7-year forecast horizon (vs garp's 5), Year 4 valuation/exit point (vs Y3), scenario probabilities tilted toward the bull tail ({bear 20, base 40, bull 40}), and a 3.5% terminal-growth cap when growth signals are above 30%. The MRVL post-Inphi-acquisition case is named explicitly in `_is_cyclical_compression` comments at target_engine.py:1647-1649 as the canonical regime-transition test case the engine already handles correctly. **The engine machinery for regime-shifters exists. The thesis prompt just doesn't consume it.**

Note: the architecture has TWO independent archetype taxonomies — `ticker_archetypes.json` (cyclical_tech, cyclical_industrial, secular_growth, compounder) drives sanity-check thresholds in `_validate_quarterly_revenue()`; `registries.py` ALL_ARCHETYPES (garp, cyclical, transformational, compounder, special_situation) drives engine math routing. Originally I described the gap as needing a new `regime_shift` archetype; the inspection found that `transformational` already does 70-80% of what's needed on the engine side, and the actual gap is at the prompt-engine interface.

The right minimum-change fix is therefore:
1. **Tag LITE, AMD, similar candidates as `transformational`** in the engine archetype assignment (via the classifier or operator override path; not via ticker_archetypes.json which uses a different vocabulary).
2. **Add prompt language at Step 5** saying: *"If the input archetype is `transformational`, the multiple anchor should reference regime-shift comps (NVDA peak NTM forward P/E ~59x in mid-2025; ASML pre-EUV-acceptance 35-45x; ARM-architecture transition) rather than same-sector historical peaks. The +25% carve-out ceiling does not apply — the entire regime-shift framing IS the structural-change defense."*
3. Optionally: add `LITE: cyclical_tech` or similar to `ticker_archetypes.json` if sanity-check thresholds need loosening for ramp data; not strictly required.

Estimated work: ~30-50 lines of prompt language plus the tagging step. Half-day is achievable because the engine already has the machinery. The earlier "100 lines" estimate was directionally right on time but wrong on what was being built; the earlier "300-500 lines, multi-day" worst case applies only if we tried to add `regime_shift` as a new archetype rather than leveraging `transformational`.

The report's deferral discipline (Section 8: wait for outcomes) still applies. The null hypothesis becomes load-bearing if **either** AMD T+30 **or** LITE T+90 lands materially above the system's target. At that point the architectural priority order is:
1. Tag affected names as `transformational` + add Step 5 prompt block. ~50 lines, half-day.
2. Iterate against AMD/LITE/AXON realized data.
3. *Only if the transformational-tagging fix is insufficient*, escalate to cognitive-architecture Proposals A/C/D.

The cheaper fix may be sufficient on its own. We should pre-spec it now so it's ready to deploy on the outcome data, not built reactively after the fact.

---

## Section 5 — What's already frame-flexible in the system

Before proposing new architecture, audit what's already frame-capable but underutilized.

**The memory layer is frame-flexible.** Per-ticker memory documents at `data/memory/<TICKER>.md` persist across runs and carry qualitative judgment that doesn't fit cleanly in the closing JSON — Hume Notes, multi-run thesis trajectories, prior-cycle analogies. This is a frame-flexible substrate. It is loaded into Step 0 but the prompt processes it as context, not as a frame to *run*.

**The scout layer is frame-specific.** Insider scout produces a sentiment-via-officer-trades frame. News scout produces a narrative-attention frame. Financial scout produces an analytical-fundamental frame. The 13F ingester (deferred per task #59-related work) produces a smart-money-positioning frame. Each scout is essentially one cognitive frame's worth of data, expressed as structured signal.

This is the under-recognized fact: **Stock Radar's scout architecture already mirrors the multi-frame structure of human cognition.** The frames-as-scouts pattern is in place. What is missing is frame-integration at the thesis layer — the prompt does not consume scout outputs as alternate analytical frames; it consumes them as evidence inputs to its own single frame.

**The engine layer is partially frame-flexible.** The engine emits conservative / central / bull forward-EPS scenarios with archetype tilts. This is a quantitative version of the mental-simulation frame (three alternate forward paths, weighted). But — as noted in the V3.4.2→V3.4.3 architectural report — the thesis prompt ignores the engine's scenarios and reconstructs its own single path. So the engine's frame-flexibility is dropped at the prompt boundary.

The diagnosis: **the system has frame-flexible inputs (scouts, engine, memory) feeding a frame-locked processor (thesis prompt).** The bottleneck is at the prompt, not at the data layer.

**A caveat on the "replaces the ratchet" framing** (raised by squad review of Hume's 2026-05-11 recommendation): an earlier draft of this note described accumulated knowledge (lessons.md + Proposal D annotations + sector_radar.md) as something that would *replace* the per-pattern archetype-fix ratchet. The squad correctly pushed back: unstructured prose with no schema, no triggers, no expiry, and no conflict-resolution rule is *relocated* complexity, not *eliminated* complexity. The defensible claim is weaker: accumulated knowledge can *reduce ratchet pressure* by externalizing judgment so future fixes can reference prior cases rather than reinventing reasoning — but it does not replace the need for occasional structural fixes (like the transformational-tagging fix in Section 10), and it introduces its own auditing burden that the archetype JSON does not have.

---

## Section 6 — Why "just add more frames to the prompt" is the wrong answer

The obvious move is to extend the prompt with new sections — Step 13 narrative-stage check, Step 14 cross-domain-analogy check, Step 15 management-credibility scorecard. This is wrong for three reasons.

First, the complexity ratchet. The prompt is already at 12 steps with sub-steps and a kill-rule table. Adding three more sequential procedural sections does not give the LLM frame-flexibility — it gives the LLM *more procedural steps in the same frame*. The frame-flexibility comes from being able to switch between frames adaptively, which is the opposite of adding sequential steps.

Second, the LLM context-window cost compounds. Each frame's instructions, evidence requirements, and output format adds tokens. A frame-flexible system should be able to invoke a frame only when relevant, not pay the token cost of all frames on every run.

Third, the council-architecture memory. The killed proposal was essentially "run multiple LLMs as different agents, each running a different frame, then reconcile." That was rejected after squad review on grounds of being premature ensemble architecture before the single-system was validated on a real decision. The same argument applies to a multi-step single-prompt frame proliferation. We are not yet at the threshold where ensemble or multi-frame proliferation is justified.

---

## Section 7 — The minimum-change proposals

The leverage point is not the prompt. The leverage point is **the integration layer between scouts/engine and the prompt** — specifically, a structured way for the prompt to consume frame-specific signals AS frames rather than as undifferentiated context.

Three concrete proposals (a fourth, Proposal B, was cut after squad review — see end of section):

**Proposal A — Frame-tagged scout output.** Each scout already produces structured signals. Tag those signals with the cognitive frame they represent: `frame=positioning` (13F, insider), `frame=narrative` (news), `frame=management` (earnings call transcript scoring), `frame=analytical` (financials). At the thesis prompt's Step 0, present scout signals grouped by frame rather than as a flat evidence dump. The LLM then has structured access to "here is what the positioning frame says" vs "here is what the narrative frame says." This is the smallest possible change that surfaces the multi-frame structure to the prompt. **Open governance question** (raised by squad review): when a signal plausibly fits two frames — a CEO-departure news headline is both `management` and `narrative` — the resolution rule must be decided centrally, not by individual scout authors, or tagging becomes taxonomy-by-fiat. A controlled frame vocabulary with `primary_frame` and optional `secondary_frame` fields is the minimum schema.

**Proposal C — Engine-feed for forward EPS scenarios** (Option 2 from the V3.4.2→V3.4.3 report). The engine already runs three forward-EPS paths. Plumb those into the thesis prompt at Step 6 instead of having the prompt reconstruct one path. This adds the mental-simulation frame to the system at zero LLM-call cost (the engine runs deterministically in Python). Realistic effort: ~3 days.

**Proposal D — Human-disagreement annotation (record-only).** When Hume disagrees with a system output, capture the disagreement in the per-ticker memory document with structured fields: `human_target`, `human_conviction`, `human_reasoning`, `disagreement_frame` (which frame is the human using that the system isn't). **The annotation is record-only.** It lives in the memory file but OUTSIDE the PRIOR CONTEXT block that the prompt reads during analysis. The prompt does not see it during reasoning. The annotation exists for outcome-tracking and for human-readable comparison after the thesis run, not for influencing the system's own analysis.

(An earlier draft of this report described a stronger version of Proposal D in which the annotation was shown to the prompt as a post-JSON comparison input. That design was retracted after squad review identified the sycophancy-drift risk it would create: presenting Hume's bullish annotations to the prompt — even "after" the JSON — would establish them as an evaluation rubric and bias subsequent runs. The record-only design preserves the falsifiable bet between system and human without creating the loop. If outcome data eventually validates the human-annotation pattern as more accurate than the system, the design can be revisited; until then, record-only is canonical.)

This is the most operationally honest version of the proposal: the system can't generate the cross-domain-analogy frame de novo, but it can preserve a falsifiable record of when a human applied one and what they predicted. The record itself does not change the system's behavior. Outcomes resolve the disagreement, not the annotation.

**Bias-source safeguard.** Even record-only annotations are curated by the same operator whose bias they're meant to capture. Hume's manual trading baseline is documented as more aggressive than V3.4.3 (`user_autonomous_trader_goal.md`); his annotations will skew bullish for the same reason. Two safeguards apply: (a) each annotation must include a brief disconfirming-case ("under what conditions would my view be wrong?"), and (b) annotations are tagged with outcome status when T+30/T+60/T+90 resolves. The annotation is a falsifiable bet, not a recorded opinion.

(An earlier draft of this report included a **Proposal B — Cross-frame disagreement as first-class signal** instructing the LLM to identify and arbitrate frame disagreements at a new Step 0.5. The squad review correctly identified that this directly contradicts Section 8's prohibition on having the LLM perform meta-cognitive frame-arbitration. Asking the LLM to judge which frame's evidence is "more load-bearing for this specific setup" is exactly the operation Section 8 prohibits. Proposal B has been cut. Its potential value — surfacing frame disagreements visibly — is preserved by Proposal D, which is human-driven, not LLM-driven.)

None of the remaining proposals are council-architecture. None of them add LLM calls. None of them ratchet prompt complexity meaningfully. They route the existing frame-flexible inputs into the existing frame-locked processor more intelligently.

---

## Section 8 — What we should NOT do

For symmetry with the must-do list:

- **Don't build a multi-agent council** (killed 2026-05-01).
- **Don't add three more procedural steps to the prompt** in service of "more frames." That is frame-stuffing, not frame-flexibility.
- **Don't build a frame-recognition LLM that classifies which cognitive frame is most relevant** for a given stock. That is meta-architecture and would add a new failure mode (mis-classification of frames).
- **Don't try to make the LLM behave like a human.** The asymmetry is structural. The right move is to design the *system* — prompt plus scouts plus engine plus memory plus human input — to do what humans do, not to make the LLM internally simulate human cognition.
- **Don't ship Proposals A-D before V3.4.3 outcome data arrives.** The same discipline that applies to V3.4.4 applies here: AXON T+30 and LITE T+90 are the load-bearing evidence. If V3.4.3 turns out well-calibrated, frame-flexibility is a nice-to-have. If V3.4.3 produces false BROKENs on regime-shift names, frame-flexibility (specifically Proposal D, the human-disagreement annotation) becomes the next architectural priority.

---

## Section 9 — Open questions

- How does Proposal D handle the case where Hume's frame turns out to be wrong? The system shouldn't auto-update to match human intuition that misfires. Annotation should be a *record of disagreement* with explicit outcome-tracking at T+30/T+60/T+90, not a recalibration trigger. The annotation creates a falsifiable bet between system and human, not a sycophancy mechanism.

- Is the right granularity per-stock or per-pattern? If Hume disagrees with the system on LITE because of cross-domain-analogy framing, does that disagreement only update the LITE memory, or does it update a cross-stock pattern memory that affects future regime-shift candidates? The latter is more powerful but harder to design correctly.

- What's the cost of frame-integration at the scout layer? The Tier 1/Tier 2 architectural gap memory says scouts are the right home for new mechanisms. But scout development has its own complexity ratchet — the deferred insider Form-4 parsing fix, the 13F ingester work, etc. Adding frame-tagging on top of an incompletely-built scout layer may not be the right ordering.

- Are we missing a frame the analysis above doesn't name? The seven frames listed in Section 2 are not exhaustive. Other plausible candidates: regulatory/legal frame (FDA approval timelines, antitrust), supply-chain frame (key supplier risk), customer-concentration frame, technical-chart frame. The point is not that the list is complete; it's that humans use multiple distinct frames and the system uses one.

- Does the dashboard already do some of this implicitly? The watchlist row + stock detail page surface scout signals, engine scenarios, thesis outputs, and memory notes side-by-side. Hume reading the dashboard *is* doing frame-integration in his head. Maybe the right answer is to do less inside the prompt and more in the dashboard's surfacing layer.

---

## Section 10 — Decision and next steps (updated in v2)

The recommended order, revised after the AMD/Evercore evidence and the sector taxonomy:

1. **No prompt changes now.** V3.4.3 just shipped. Adding frame-integration layers on top is the complexity-ratchet pattern.

2. **Capture the LITE-vs-dad disagreement as a record-only annotation** in the LITE memory document (not in the PRIOR CONTEXT block consumed by the prompt). The annotation format should include `human_target: $1800`, `human_conviction: HIGH`, `human_reasoning: regime-shift framing — AI infra component, not optical cyclical`, `disagreement_frame: cross-domain-analogy`. This costs nothing, creates a falsifiable record, does not feed the prompt's analytical loop, and tests whether human-disagreement-annotation is a useful primitive without exposing the system to sycophancy drift. **Per the structural safeguards in Section 7, this annotation must not be promoted into prompt-consumed context until outcome data validates it.**

3. **At AXON T+30 (~2026-06-08) and LITE T+90 (~2026-08-08), revisit with two distinct hypotheses on the table.** If outcomes show the system was right (LITE stays at $960 or drops), neither the cognitive-architecture proposals nor the null-hypothesis multiple-anchor reform are needed. If outcomes show the father was right (LITE rallies to $1,500+), the priority decision is between Proposal D (architectural addition that converts human judgment into system input) and a Step 5 regime-shift carve-out (null hypothesis fix that mechanically corrects the multiple anchor). Both could end up being needed; the null-hypothesis fix is materially cheaper and should be tried first.

4. **In parallel, the engine-feed work (Proposal C / Option 2 from the V3.4.2→V3.4.3 report) is still the right architectural answer for forward-EPS scenarios.** It is unblocked by the framing in this note; the cognitive-architecture framing actually strengthens the case for it.

5. **Pre-spec the Path A fix: leverage existing `transformational` archetype + Step 5 prompt block.** This is new in v2 and is the most important change to the recommendation order. With two cases now indicting Step 4 and Step 5 of the prompt for the same underlying reason (conservative-by-design assumptions misfiring on regime shifts), the cheapest available intervention is — per the post-v2 code inspection — *not* to add a new archetype. The engine's `transformational` archetype already provides 7-year forecast horizon, Y4 exit, bull-tail-tilted scenarios, and a 3.5% terminal-growth cap when growth signals are high. The MRVL regime-transition case is named explicitly in the existing code as the canonical handled-correctly example. The fix:
   - Tag LITE, AMD, and similar candidates as `transformational` via the engine's archetype assignment path (classifier output or operator override; not the sanity-check `ticker_archetypes.json` which uses a different vocabulary).
   - Add prompt language at Step 5: *"If input archetype is `transformational`, anchor the multiple to regime-shift comps (NVDA peak NTM forward P/E ~59x in mid-2025; ASML pre-EUV-acceptance 35-45x; ARM-architecture transition) rather than same-sector historical peaks. The +25% carve-out ceiling does not apply — regime-shift framing IS the structural-change defense."*
   - Estimated work: ~30-50 lines of prompt language plus the tagging step. Half-day. The engine work is already done.
   - The deployment trigger is: if AMD T+30 or LITE T+90 lands materially above system target, ship the prompt patch + tagging that day. Don't deploy preemptively.
   - The falsifiable smoke test before deployment: run V3.4.3-with-prompt-patch on (LITE tagged transformational, COHR untagged). LITE's `risk_adj_ev_ratio` should move from 0.833 to ≥1.10 (MEDIUM/25% bucket). COHR's ratio should stay below 0.95 (still BROKEN). If both move correctly, Path A is calibrated. If COHR also flips out of BROKEN, the prompt language is leaking the regime-shift carve-out into untagged cases and needs tightening.

6. **Capture sector taxonomy as static reference now** (per `project_sector_mapping_scout_spec.md`). Zero-cost: add a `theme` annotation to each watchlist ticker's memory document using Hume's 14-theme taxonomy. LITE = optical tier 1, AMD = CPU chips, MU = storage tier 1, etc. When the sector-mapping scout eventually gets built, these annotations bootstrap its theme assignments. When the next thesis runs, the theme tag is in the memory context and the LLM can reason about theme-level dynamics without any prompt change.

7. **Defense-in-depth deferrals stay deferred.** Hype monitor, Tier 1 mechanism, scout sector-map, full cognitive Proposals A/C/D. None of these are urgent. All of them potentially become priority-1 after AMD/LITE/AXON outcomes resolve, in a sequence determined by which intervention earns its keep first.

8. **lessons.md discipline (when it eventually gets built).** Each entry must include: (a) the lesson stated cleanly with a worked example, (b) **a named disconfirming-case** — under what conditions would this lesson be wrong, and what would falsify it; (c) an outcome-status tag that gets updated when T+30/T+60/T+90 data resolves. Without these three fields, lessons.md becomes Hume's bias preserved as authoritative-looking text. With them, each lesson is a falsifiable bet. The format Hume articulated as the operational pattern: *"Memory chips at peak earnings compress to 6-12x P/E because the market prices in the coming downturn. Disconfirming case: if the cycle is structurally different (e.g., AI-driven structural demand rather than cyclical restocking), peak multiples could sustain longer. Validation: pending MU T+90 outcome."*

9. **Calibration trigger fallback.** The "N≥20 thesis rows with T+90 outcomes" criterion for Session 6 calibration will not fire automatically — at 17 distinct tickers in `data/theses/`, no outcome-tracking infrastructure built yet, and earliest T+90 resolving 2026-08-01, the original September target slips. Use the explicit fallback: **whichever comes first, N≥20 with T+90 OR 2026-10-01.** If October arrives with N=17 and T+90 data on only 8-12 tickers, run the calibration on what exists rather than waiting for a threshold that may never trigger.

The bigger principle the report is trying to surface remains: **the system is closer to a frame-flexible architecture than it appears.** The scout layer is already frame-structured. The engine already produces alternate scenarios. The memory already persists qualitative judgment. The thesis prompt is the bottleneck. But v2's revised diagnosis is sharper: before adding frame-integration plumbing, the cheapest available fix may be to correct the rules that produce systematically pessimistic inputs to the kill rule. Both could end up being needed; the regime-shift archetype is the lower-cost-first try.
