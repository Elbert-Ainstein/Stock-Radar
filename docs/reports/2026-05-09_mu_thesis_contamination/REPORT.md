# MU thesis pipeline contamination — diagnostic report

**Date:** 2026-05-09
**Author:** Claude (with Hume verification)
**Status:** Diagnosis corrected after review-squad pass. Action plan pending Hume sign-off.
**Severity:** High — affects LLM thesis output for any watchlist ticker that survived the contamination window. Likely also affects similar bugs in any other ticker (not just MU).

---

## TL;DR

The MU model in Stock Radar shows a thesis target of **$1,180** (HIGH conviction, 30% position, +58% upside). Pasting the same V3.3 thesis prompt into a clean Claude session produces **$855** (+14.5%, "thesis has largely played out"). The 38% gap is real evidence of pipeline contamination, not stale data.

**My initial diagnosis was wrong.** I told Hume the contamination was a forward-driver scout signal carrying an impossible "guided op margin 77%" into the thesis prompt. Three independent reviewers (critic, red-team, outsider) shredded that diagnosis. The actual primary contamination path is `data/memory/MU.md` line 19, which has the prior $1,180 thesis baked into the memory document that gets injected into every future thesis prompt as `[MEMORY_SECTION]`.

There are at least three contamination paths layered on top of each other. Fixing one without the others will not close the gap.

**Decision pending:** execute the corrected three-step plan (clear memory anchor, tighten regex bound, add sector-aware op-margin cap), or escalate to a wider audit before acting.

---


## Revisions log

**v2 — 2026-05-09 (post-pushback):** Original v1 had three errors that surfaced when Hume pressure-tested the plan. Material changes in this revision:

- **Dropped "$855 as convergence target" framing.** v1 implicitly anchored success on closing toward the fresh-paste output. Pushback was correct: the fresh paste is one LLM output with its own biases (recency / mean-reversion). The right success criterion is **a controlled before/after on the pipeline itself**. Fresh-paste is a tripwire, not a benchmark.
- **Reordered the action plan from 6 steps to 8.** Added Step 0 (verify diagnosis is complete by printing actual prompt content) and Step 1 (architectural memory-write hygiene fix), and moved the watchlist audit BEFORE the MU re-run so contamination doesn't compound across tickers.
- **Dropped Question 4 (rerating-already-happened heuristic).** That heuristic would have killed every 10x position in the portfolio (LITE up 1600%, NVDA up 300%+, SNDK up 3200%). Mean-reversion encoded as a scoring rule is the wrong prior for a 10x-discovery system. The fresh-paste's "thesis has played out" framing was MU-specific (commodity cyclical near peak), not a general truth.
- **Tightened the regex fix.** v1 proposed flat 60% cap. Better: layered fix — tighter regex pattern (require contiguous `\boperating\s+margin\b`) + sector-aware cap in the engine + eventual move to structured guidance fields instead of narrative-extraction.
- **Reframed "system grades its own homework."** The memory system *logs* — it doesn't grade. The pathology is at the LLM-anchoring step where a low-temperature model treats logged history as trusted prior context. Fix is "don't feed contaminated logs into prompt context," not "stop logging."

The diagnostic itself (three contamination paths, squad findings, file:line evidence) stands unchanged. Only the success criterion, ordering, and regex-fix detail were revised.

---

## What Hume saw (the observation)

Two screenshots, side by side:

**Screenshot 1 — Stock Radar model page for MU:**

| Field | Value |
|---|---|
| Thesis Target | **$1,180** |
| Conviction | HIGH · 30% |
| Breakout | $1,600 |
| Risk-adj | $1,085 |
| Upside vs current | +58% |
| Run timestamp | 2026-05-09 14:09:54 |
| Data source | EODHD Fundamentals API |
| Warnings panel | Manual override, provider override, EBITDA margin warning, **forward driver "guided op margin 77%"** |

**Screenshot 2 — Same V3.3 thesis prompt pasted into a clean Claude session:**

```
Step 7 — Thesis Target

Target = $90 NTM EPS × 9.5x multiple = $855
Derivation integrity check: Target $855 vs. derived math $855 — match.

Vs. current price $746.81: +14.5% upside over 12 months.

This is admittedly modest upside. The reason is that the thesis has
largely already played out. The stock 9x'd in 12 months. It moved
15% on May 8 alone. Most of the rerating has happened.
```

The two outputs are using the same prompt, the same underlying market data, the same ticker. The 38% gap is the bug.

---

## My initial (incorrect) diagnosis — for the record

Original claim:

> The contamination is the forward-driver scout signal "guided op margin 77%" in the warnings panel. The pipeline injects it into the thesis prompt as a forward-driver signal, biasing the LLM toward an aggressive scenario. Fix path (a): find the Supabase scout signal record where guided_op_margin = 0.77, delete or recompute it, re-run thesis on MU, compare to the $855 hand-paste reference.

I also told Hume *"trust the fresh one"* — meaning, when the pipeline disagrees with a fresh-paste session, default to the fresh paste's output.

**Both claims were wrong.**

---

## What the review squad found

I sent the diagnosis to three reviewers. All three independently pointed at problems I missed.

### Critic — load-bearing finding

The causal chain I described is broken. `run_thesis.py` does NOT call `forward_drivers.py` or `target_engine.py` in its prompt-construction path. The "guided op margin 77%" warning shown on the model page is a **`target_engine` UI display artifact** for the DCF panel — it never reaches the LLM thesis prompt.

What `run_thesis.py` actually injects into the LLM thesis prompt:
- `[VERIFIED_FINANCIALS]` block — produced by `_build_verified_financials_block(fin)` from the (now-patched) financials
- `[MEMORY_SECTION]` block — full contents of `data/memory/{TICKER}.md` if it exists

Verified by reading `data/memory/MU.md` directly:

```
Line 19: | 2026-05-09 | v3.3 | DCF/EPS×Multiple | $680 | $1,180 | $1,600 | HIGH | 30% | $700 | $1,300 |
Line 25: First run on this ticker; no multi-run trajectory to report. Single
         data point: thesis target $1,180 (58% upside from $746.81),
         risk-adjusted target $1,085 (45% upside), at 13x NTM EPS of ~$90.92...
```

The previous (contaminated) thesis is now part of the memory document that anchors every future MU thesis run. At TEMPERATURE=0.3 the LLM will gravitationally drift toward the prior conclusion.

**Verdict: do not ship the original diagnosis. The fix proposed wouldn't actually close the gap.**

### Red-team — three failure modes + one nobody noticed

**Failure mode 1.** The "77%" forward-driver value is most likely a regex misfire, not a genuine guidance number. `forward_drivers.py:441` uses pattern `(?:operating|op)\s+margin` with upper bound `< 100`. MU's *gross* margins legitimately run 70%+ at cycle peak. Earnings call narrative like "DRAM operating margins of 77%" or even "DRAM segment operating with 77% gross margin" pattern-matches the regex and gets stored as op-margin guidance. Deleting the Supabase row destroys the audit trail; the next scout cycle re-ingests the same news → same misfire. Need to tighten the regex (or add a sector-aware cap), not delete records.

Concrete: **change `forward_drivers.py:441` upper bound from 100 to ~60.** Memory chips with 20%+ capex intensity cannot sustain 70%+ op margins structurally.

**Failure mode 2.** Even after a perfect data fix, **re-running thesis on MU produces a contaminated re-run** because the memory file still has the $1,180 history table. The LLM sees its own prior conclusion as "prior context" at TEMPERATURE=0.3 and drifts toward it. The post-fix re-run is not a clean control.

Mitigation: surgically edit `data/memory/MU.md` to remove the contaminated history row + Trajectory paragraph BEFORE re-running. (Or run with --no-memory if such a flag exists; check `run_thesis.py` argparse.)

**Failure mode 3.** `target_engine.py:833-840` margin blend accepts any `0 < guided_op < 0.85`. For MU at cycle peak, blending a 77% guided value with the 40-45% historical produces ~73% blended — directly multiplied into terminal cash flows. At ~$40B TTM revenue and 20x EBITDA multiple, that's ~$11.5B phantom EBITDA → ~$230/share phantom value. Right ballpark to explain the gap from the engine side too.

Mitigation: add a sector-aware plausibility gate. If archetype is `cyclical` OR (D&A / revenue) > 15%, cap `guided_op_margin` at ~55% before it enters the blend.

**The one nobody's thinking about:** the `latest-timestamp-wins` merge at `forward_drivers.py:549-553` is non-idempotent. Re-running the scout to regenerate a clean signal could produce a third different value depending on which order news sentences appear in the retrieved context that day. Three runs → three targets in $1,000–$1,200 range, all wrong, no falsification mechanism until the stock moves enough to verify.

### Outsider — the punch

> *"You built a pipeline to outperform your own intuition, but the moment the pipeline disagrees with a fresh chat session, you're asking whether to trust the fresh chat — which means you're back to trusting intuition, just one step removed."*

The "trust the fresh one" framing was wrong. Both pipeline output and fresh-paste output are LLM completions with different priors and contexts. Neither is a ground-truth oracle. The actionable comparison is between **(pipeline pre-fix on prompt P)** and **(pipeline post-fix on the same prompt P)** — that's controlled. **(Fresh-paste on P)** vs **(pipeline on P)** is two different models with different inputs and tells us nothing definitive.

Reframe: *the pipeline is currently un-auditable enough that a fresh-paste can produce wildly different output, which is itself the problem to solve.* Fix the pipeline's grounding inspectability; do not bypass it for vibes.

---

## The corrected diagnosis — three contamination paths

The $1,180 vs $855 gap has at least three contributors. Listed in order of likely impact on the LLM thesis prompt:

### Path 1 — Memory file anchor (proximate cause, biggest LLM-prompt impact)

**Location:** `data/memory/MU.md` lines 19, 25, and the surrounding Thesis History table and Trajectory paragraph.

**Mechanism:**
1. `run_thesis.py:656-659` reads `data/memory/MU.md` if it exists.
2. The contents are injected verbatim at the `[MEMORY_SECTION]` placeholder in the prompt.
3. The injected memory includes the prior $1,180 thesis row plus the Trajectory paragraph anchoring the model to "$1,180 (58% upside)" and "13x NTM EPS of ~$90.92".
4. At TEMPERATURE=0.3, the LLM treats its own prior conclusion as prior-context evidence and outputs something close to it.

**Evidence:**
- Confirmed by direct file inspection — line 19 has `$1,180 | $1,600 | HIGH | 30%`.
- The memory file also lists "Single data point: thesis target $1,180 (58% upside)..." in the Trajectory section.
- The fresh-paste hand-test had no memory injection and produced $855 — entirely different framing.

**Fix:** surgically edit the memory file. Remove the contaminated history row and the Trajectory paragraph that quotes the bad target. Keep useful context (e.g. "ticker exists in watchlist", confirmed catalysts that are factual). Re-write so the next thesis run starts from a clean slate without losing all prior knowledge.

### Path 2 — Forward-driver regex misfire (UI artifact, contributes to engine-side bullishness)

**Location:** `scripts/forward_drivers.py:441` regex bound `0 < mid < 100`.

**Mechanism:**
1. Scouts retrieve narrative news / earnings-call text via Perplexity.
2. The regex `(?:operating|op)\s+margin\s*(?:of|at|to|target)\s*(?:approximately|around|~)?\s*(\d+(?:\.\d+)?)%` scans the text.
3. MU's earnings call language like "DRAM operating margins of 77%" or "consumer-grade gross operating margin of 77%" pattern-matches.
4. The matched 77 is stored in Supabase as `guided_op_margin_pct = 77` for MU.
5. The structured-path validator at `forward_drivers.py:338-340` would reject 77 (its cap is 0.85), but the narrative-path validator at line 441 accepts anything 0–100.
6. The signal is later read by `target_engine.py:833-840` and blended into the margin target.

**Evidence:**
- 77% appears as "guided op margin" in the warnings panel — exact value of MU's typical DRAM gross margin at cycle peak.
- No memory company sustainably operates at 77% op margin; the 0.85 cap is the right shape but the upstream regex bound contradicts it.

**Fix:** tighten the narrative regex bound from 100 to 60 for op_margin. Plus add a sector-aware plausibility gate downstream in `target_engine.py:833`: if archetype is cyclical or `D&A / revenue > 0.15`, cap `guided_op_margin` at 0.55.

**Affects:** the model UI's DCF target and engine-side calculations. Does NOT directly contaminate the LLM thesis prompt (per critic finding).

### Path 3 — Partial-patch at run time (historical, not recurring)

**Location:** the prior thesis run at 2026-05-09 14:09:54 ran before the multi-statement override shipped (which happened mid-afternoon).

**Mechanism:**
1. At the time the thesis ran, only revenue was patched ($23.86B → $13.64B). Operating income, D&A, EBITDA, FCF were still inflated.
2. The `[VERIFIED_FINANCIALS]` block in the thesis prompt showed correct revenue but inflated income/cash-flow rows.
3. The LLM saw "TTM op margin = 77.5%" inside the verified-financials block (impossible, but presented as verified).
4. The thesis output anchored to that fake-high margin → high target.

**Evidence:**
- Run timestamp 14:09:54 precedes the multi-statement override commit.
- Memory file Trajectory paragraph says "13x NTM EPS of ~$90.92" — that EPS is inflated relative to what real $5.24B Q1 net income annualized at ~$26 NTM EPS, so 13x → ~$338, not $90.92. The model was quoting real-world multiple but applying it to inflated EPS.

**Fix:** automatic — the multi-statement patch is now in place. Any re-run from this point uses correct margins. But the OUTPUT of that bad run is now the contaminant in Path 1.

---

## On the size of the gap

A v1 version of this section attempted a back-of-envelope decomposition of the $325 gap into specific contamination contributions — including an "inflated NTM EPS used (~$90.92 vs real ~$26 annualized)" row and a closing claim that "the right answer is closer to $855 than $1,180."

**That math was wrong, and the framing was wrong.**

- The "$26 annualized" baseline came from naively annualizing Q1 net income ($5.24B × 4 ÷ ~1.1B diluted shares). That's a TTM proxy, not an NTM estimate. Forward analyst consensus for MU incorporates HBM ramp, AI capex, and cycle progression through FY27 H1; real NTM EPS estimates are likely in the $60–$90 range (operator should verify against actual sell-side / fundamentals data before relying on any specific number). The $90.92 in the contaminated run may not have been the contamination — it might have been a reasonable forward estimate that happened to coincide with the inflated pipeline output.
- The "$855 is closer to the right answer" framing reverts to using fresh-paste as a benchmark — exactly the error v2 was supposed to fix.

What we can say with confidence:
- **Three contamination paths exist**, identified by file:line evidence above.
- **At least one of them (Path 1, memory anchor) verifiably affects the LLM thesis prompt** at TEMPERATURE=0.3.
- **The size of the contamination's contribution to the gap is not knowable from the diagnostic alone.** Only Step 6 of the action plan (controlled pre-fix vs post-fix pipeline comparison on the same prompt) can quantify it.

The honest expectation: post-fix pipeline output could land anywhere from $700 to $1,100 depending on what the actual analyst forward estimates and updated memory context produce. Treat the $1,180 as suspect and the $855 as one external data point — neither is a target.

---

## Hume's hand-paste output is NOT canonical

Important nuance, from outsider's review: do not treat the $855 fresh-paste output as ground truth either. It just happens to NOT have the contamination paths above. It might have its own biases:
- It lacks the scout-signal context (forward drivers, convergence signals across multiple sources).
- It lacks the multi-run history that the memory document is supposed to provide *when uncontaminated*.
- It's anchored to "stock 9x'd in 12 months" which is a mean-reversion prior — could be too pessimistic.

The right comparison is **pipeline-pre-fix vs pipeline-post-fix on the same prompt and same underlying data** — that's a controlled experiment. Fresh-paste is a useful sanity check but not a benchmark.

---

## Action plan (v2, post-pushback)

Execute in this order. Each step has a check before proceeding.

### Step 0 — Verify the diagnosis is complete

Dry-run `python scripts/run_thesis.py MU` capturing the literal text sent to the LLM (add a `--print-prompt-only` flag if it doesn't exist). Manually inspect every section: `[ANALYST_PROMPT]`, `[VERIFIED_FINANCIALS]`, `[MEMORY_SECTION]`, any other injected blocks.

**Why first:** the report identifies three contamination paths by reasoning about the architecture. A fourth could be hiding in the literal prompt content — a templating bug, a dangling reference, an unexpected context injection. Don't fix what you haven't verified is wrong.

**Check:** confirm the contamination is contained to the three identified paths. If a fourth surfaces, stop and re-diagnose.

**Also during Step 0:** capture the actual NTM EPS estimate the contaminated run used (the "$90.92" from the memory file's Trajectory paragraph). Verify against current analyst consensus / forward fundamentals — do NOT treat naive Q1 annualization as the baseline. If the $90.92 is close to consensus, the contamination is concentrated in the multiple, the margin assumptions, and the memory anchor; if $90.92 is materially above consensus, there's a fourth contamination path in the EPS-projection step that needs separate investigation.

### Step 1 — Architectural memory-write hygiene fix

Modify the memory write-back logic in `run_thesis.py:755-794`: thesis runs with active warnings (sanity check fired, override applied, provider fallback triggered, EarningsFetchError caught earlier in chain) do not append to the canonical Thesis History table. Either skip the write entirely OR append to a "quarantined" section that the next run's prompt does NOT include in `[MEMORY_SECTION]`.

**Why architectural, not per-ticker:** every ticker has the same first-run anchor problem. If the first thesis run is wrong (bad data, regex misfire, stale web search), that wrong target becomes prior-context for all future runs at TEMPERATURE=0.3. Per-ticker cleanup is Whac-A-Mole; the write-time gate is the structural fix.

**Check:** simulate a thesis run with override_suspect_recent active → verify it does NOT append to Thesis History. Simulate a clean run → verify it DOES append.

### Step 2 — Audit all watchlist tickers for memory contamination

For each ticker with a `data/memory/{TICKER}.md` file:
- Check if any Thesis History row was written during a contamination window (any run before today's multi-statement override patch shipped, or any run where active warnings existed).
- Run a fresh-paste comparison on the V3.3 prompt for the ticker — use solely as a tripwire: if pipeline diverges from fresh paste by >25%, flag for cleanup. Do NOT use the fresh-paste output as the target.

**Why before re-running:** if N tickers have memory contamination and we re-run all of them with contaminated memory, we get N new contaminated rows written back. Audit-then-batch-fix prevents the cascade.

**Check:** produce a flagged list. Likely candidates: anything run during the period when MU's bad data was active in the engine (which may have polluted shared sector_stats or cross-ticker priors).

### Step 3 — Surgically clean all flagged memory files in one batch

For each flagged ticker, edit `data/memory/{TICKER}.md`:
- Remove contaminated Thesis History rows (rows from runs with active warnings).
- Remove Trajectory paragraphs that quote contaminated dollar targets verbatim.
- Keep ticker metadata, factual catalysts, watchlist join date, kill triggers, anything not derived from the contaminated thesis output.

**Check:** open each cleaned file. Confirm no contaminated targets remain. Diff against backup so the cleanup is auditable.

### Step 4 — Code fixes: tighter regex + sector-aware cap

- **`scripts/forward_drivers.py:441`** — change pattern to require contiguous `\boperating\s+margin\b` (not the looser `(?:operating|op)\s+margin`). Lower the upper bound from 100 to a sector-conditional value, kept consistent with the engine-side cap: **35% for software / fintech, 30% for semis / hardware, 25% for industrials, 55% for memory / cyclical at peak**. Default to 35% when sector unknown.
- **`scripts/target_engine.py:833`** — add a sector-aware plausibility gate: if archetype is `cyclical` OR `D&A / revenue > 0.15`, cap `guided_op_margin` at **0.55** before blending. Same number as the regex cap for memory / cyclical (defense in depth — both layers reject the same value, neither layer alone is load-bearing).

**Check:** unit test on fixture text "DRAM operating margins of 77%" → regex no longer matches as op_margin (or matches but is rejected by sector cap). Existing tests still pass.

### Step 5 — Re-run thesis for all flagged tickers in one clean pass

After Steps 1-4 are in place, run `python scripts/run_thesis.py {TICKER}` for each flagged ticker. Each run now sees: clean memory, tightened regex, sector-aware engine cap, and the multi-statement-patched financials.

**Check:** all runs complete without errors. Capture each output for Step 6.

### Step 6 — Controlled comparison: pipeline pre-fix vs pipeline post-fix

For each re-run ticker, compare:
- Old thesis target (pre-fix, from contaminated run)
- New thesis target (post-fix, from clean run)

This is the canonical success criterion. **Do not use fresh-paste output as benchmark** — that's an LLM with different priors, not ground truth.

**Check:** for MU specifically, the new target should differ materially from $1,180. If not, undiscovered contamination remains. Investigate before declaring victory.

### Step 7 — Squad review of MU and AXON specifically

These are the highest-stakes positions (MU = 30% recommended, AXON = first system signal acted on at 5%). Run critic + outsider on each new thesis output to validate the reasoning is no longer artifact-driven.

**Check:** at least one reviewer flagged "no anchoring artifacts visible" before trusting the new target. If still flagged, escalate.

---

**Question 4 (rerating-already-happened check) — DROPPED in v2.**

The proposed heuristic ("if stock is up >200% in 12mo, downweight upside scenarios") would have killed every 10x position in the portfolio: LITE up 1600%, NVDA up 300%+, SNDK up 3200%. Mean-reversion encoded as a general rule is the wrong prior for a 10x-discovery system. The fresh-paste's "thesis has played out" framing for MU was specific to MU's situation (commodity cyclical near peak earnings power), not a transferable rule.

The right archetype-aware question to add to the thesis prompt — if any — is: **"is the thesis target's required forward EPS achievable from current operating run-rate, or does it require further fundamental improvement that the model hasn't justified?"** That's a derivation-integrity check, not a returns check, and it doesn't penalize stocks that have already moved.

---

## What does NOT need fixing

- The provider chain (`config/data_provider_overrides.json`) — working correctly.
- The manual quarterly override layer (`config/manual_quarterly_overrides.json`) — working correctly, now patches all 11 line items.
- The sanity check in `_validate_and_build` — working correctly; with patched data it returns 0 warnings.
- The model's UI rendering — the warnings panel correctly surfaces the override and the contaminated forward-driver signal so the operator can see them.

---

## Open questions

1. **Are there other tickers with the same memory-anchor problem?** Any ticker whose first thesis ran during the contamination window has a similarly-baked memory file. Audit needed (covered by Step 2 of the action plan).
2. **How often does the regex misfire on cyclical/commodity tickers?** Worth scanning Supabase `signals` for any `guided_op_margin_pct` value > 0.55 in cyclical sectors and flagging.
3. **Is the memory document's "Trajectory" pattern a recurring contamination source?** The memory format includes self-quoting of prior thesis output. That's useful for stable tickers (gives the LLM context on whether thesis is converging) but pathological when the prior run was wrong. Worth thinking about a "memory hygiene" pass — e.g., scrub Trajectory entries that quote specific dollar targets and replace with qualitative direction.
4. **Does the same pattern affect AXON ($620 thesis target, first system signal)?** Run the same diagnostic — fresh-paste comparison as tripwire, then if flagged, clean memory and re-run. AXON is the first system signal acted on at 5%; the contamination risk is non-zero and worth checking before the position size grows.
5. **Should the V3.3 thesis prompt include a derivation-integrity reminder for cycle-position checks?** Not a "rerating already happened" rule (which would be wrong-direction for 10x-discovery), but a step that asks the LLM to check whether the thesis target's required forward EPS is achievable from current operating run-rate, or requires further fundamental improvement the model hasn't justified. Archetype-aware, not returns-based.

---

## Files referenced

- `data/memory/MU.md` — the smoking gun. Lines 19, 25, full Trajectory paragraph.
- `scripts/run_thesis.py:656-659` — memory injection.
- `scripts/forward_drivers.py:441` — regex upper bound bug.
- `scripts/forward_drivers.py:338-340` — structured path (correctly gates at 0.85).
- `scripts/forward_drivers.py:549-553` — non-idempotent latest-timestamp-wins merge.
- `scripts/target_engine.py:833-840` — margin blend amplifier (no sector-aware cap).
- `config/manual_quarterly_overrides.json` — multi-statement patch (working correctly).
- `config/data_provider_overrides.json` — provider chain (working correctly).

---

## Visualizations

- `mindmap.svg` — overview of the three contamination paths and squad findings
- `data_flow.svg` — pipeline data flow showing where each bug enters
- `gap_breakdown.svg` — pipeline target vs hand-paste vs post-fix unknown range (v2: post-fix bar shows "?" since fresh-paste is not a benchmark)

