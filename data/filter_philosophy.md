# Filter Philosophy — Hard Gates vs Contextual Routing vs Informational Signals

**Date:** 2026-05-26
**Author:** Hume (design intent), preserved verbatim
**Companion to:** `filter_audit_2026_05_26.md`, `session2_engine_implications.md`
**Purpose:** Establish the permanent design principle for when a filter should be hard, contextual, or informational. Prevent the recurring mistake of turning judgment calls into binary gates.

**Status:** Canonical. Every future filter addition must cite this document and classify into Category 1/2/3 with explicit reasoning. Claude raised two pushbacks (the new hard gates for max single-name exposure and max portfolio leverage; the arbitrary "under 10" hard-gate count); those remain open questions to address when we tackle position-sizing or leverage rework. The framework itself is accepted as canonical.

---

## The Recurring Mistake

The system has a gravitational pull: every useful observation gets turned into a hard filter.

```
"High-consensus stocks have less discovery alpha"
  → System builds: block analysis when analyst_count > 20
  → Result: misses LITE, which was high-consensus but had 
    regime-shift upside the consensus didn't price

"DCF undershoots regime-shift candidates"  
  → System keeps: DCF as primary valuation for ALL stocks
  → Result: kill rule fires on LITE at $283, user enters at $70
    and rides to $946. The engine blocked its own best trade.

"SaaS is dying from AI disruption"
  → Temptation: auto-short stocks with ai_threatens > 70
  → Reality: APP has ai_threatens = 5 but gets sold in the 
    "SaaS is dead" narrative. The observation is right but 
    the gate would miss the nuance.

"Revenue jumped 50x quarter-over-quarter"
  → System builds: flag as suspicious, block analysis
  → Reality: ASTS commercial launch. The 50x ramp IS the 
    asset class. Blocking it blocks the opportunity.
```

Every one of these started as a correct observation. Every one became a harmful filter by hardening what should have been context into a binary gate.

---

## The Principle

**Ask one question: is this filter catching a FACT ERROR or making a JUDGMENT CALL?**

- Fact error → HARD GATE. Always enforce. No override.
- Judgment call that depends on context → CONTEXTUAL ROUTING. Same tools, different application based on archetype/timing/macro.
- Useful observation for human decision-making → INFORMATIONAL SIGNAL. Surface it. Never block.

---

## Category 1: Hard Gates

**Definition:** Binary, always enforced, no override possible. These catch things that are OBJECTIVELY WRONG or PHYSICALLY DANGEROUS regardless of context.

**When to use:** The filtered thing is never acceptable in any scenario. The downside of not filtering is catastrophic. No human judgment is needed — the answer is always "block this."

### Current hard gates (keep)

| Filter | What it catches | Why it's always wrong |
|--------|----------------|----------------------|
| EDGAR cross-validation halt (10% divergence) | Provider data disagrees with SEC filing | One number is factually wrong. No context makes wrong data acceptable. |
| Anti-sycophancy (5% convergence trigger) | Model output matching operator input | Anchoring to external expectations is never valid analysis. No context makes sycophancy acceptable. |
| Anti-contamination (cite validated_corrections) | Using previously-corrected wrong data | Known-wrong data should never flow into analysis. |
| SEC EDGAR rate limit (120ms) | Exceeding SEC API limits | Legal compliance. Always enforced. |
| strict-fill guard | Integration bugs in Socratic pipeline | Garbage output is never useful. |
| Cost runaway prevention (--no-thesis cron flag) | Uncontrolled API spend | $2,160/month runaway is always bad. |

### Hard gates to add

| Filter | What it catches | Why |
|--------|----------------|-----|
| Max single-name exposure (30% including leveraged equivalents) | Concentration risk | A 40% drawdown on a 30% position costs 12% of total portfolio. Physics of risk management. No thesis justifies this level of concentration. |
| Max portfolio leverage ratio | Aggregate leveraged ETF exposure | 67% in leveraged ETFs during a macro you predict will correct is physical danger to capital. |

### Properties of hard gates

- No archetype bypass. No timing-category exception. No operator override.
- If a hard gate fires, analysis STOPS or data is REJECTED.
- Hard gates are RARE. The system should have fewer than 10.
- Every proposed hard gate must answer: "is there ANY context where the filtered thing is acceptable?" If yes → not a hard gate.

---

## Category 2: Contextual Routing

**Definition:** The filter applies the SAME analytical tools but with DIFFERENT parameters based on what kind of stock you're analyzing. The routing key is the stock's archetype, timing category, and/or macro regime.

**When to use:** The right answer genuinely depends on context. A cyclical stock and a pre-revenue moonshot need different analytical frameworks applied to them — but neither should be blocked from analysis.

### Current filters that should be contextual (fix these)

| Filter | Current state (WRONG) | Correct state | Routing key |
|--------|----------------------|---------------|-------------|
| **DCF role** | Hard: DCF is always primary in target_engine.py | Contextual: primary for cyclicals, downside-floor for growth, reference-only for pre-revenue | Archetype: `cyclical` → primary, `secular_growth` → floor, `pre_revenue/early_revenue_ramp` → reference |
| **Kill rule threshold** | Hard: fires at risk_adj_ev_ratio < 0.90 for ALL stocks | Contextual: tighter for cyclicals (< 0.90), wider for regime-shift (< 0.60), disabled for pre-revenue (Model D handles this) | Archetype + DCF role |
| **Module 1 data validation** | Hard: trajectory smoothness check blocks on anomaly | Split: EDGAR cross-check stays hard (fact error). Trajectory smoothness becomes informational warning (judgment call). | Archetype: `early_revenue_ramp` → warn but don't block |
| **Analysis routing** | Hard: operator manually invokes Auto vs Socratic | Contextual: 收获期+not_held → Auto, 收获期+held → Socratic+future-pricing, 半步领先 → Socratic, 远见期 → Model D | Timing category × held/not-held |
| **Non-US discovery minimum** | Hard: 4 quarters or skip | Contextual: 4 for mature, 2 for `early_revenue_ramp` | Archetype + geography |
| **Valuation emphasis** | Hard: same framework for all stocks | Contextual: EV for 半步領先, ceiling for 远见期, priced-years gap for 收获期+held | Timing category |
| **Position sizing** | Hard: MAX_POSITION = 10% | Contextual: 5% first-touch → 10% after T+30 → 15-20% after T+60 with thesis intact | Signal maturity |

### Properties of contextual routing

- Same tools, different parameters. Not "skip this stock" but "analyze this stock differently."
- The routing key must be EXPLICIT — archetype, timing category, or macro regime. Not implicit.
- Default route should be the most conservative option. Explicit archetype tagging unlocks the alternative routes.
- Contextual routing is where the system's intelligence lives. Hard gates are safety. Informational signals are awareness. Contextual routing is the analytical engine adapting to different situations.

### The DCF example in detail

This is the single most important contextual routing fix:

```
Stock enters analysis
  ↓
Harness reads archetype from config
  ↓
┌─ cyclical_tech / compounder ──────────────────┐
│ DCF role: PRIMARY                              │
│ Kill rule: fires at ratio < 0.90               │
│ Target: DCF-derived with multiples cross-check │
│ This is what target_engine.py does today.       │
│ CORRECT for this archetype.                    │
└────────────────────────────────────────────────┘

┌─ secular_growth / regime_shift ───────────────┐
│ DCF role: DOWNSIDE FLOOR                       │
│ Kill rule: fires at ratio < 0.60 (wider)       │
│ Target: scout-blended forward signals +        │
│   thesis-derived multiples. DCF is the BEAR    │
│   scenario floor, not the primary output.      │
│ Future-pricing §7b: priced-years vs actual gap │
│ This is what Socratic does but Auto doesn't.   │
│ FIX NEEDED: make Auto do this too.             │
└────────────────────────────────────────────────┘

┌─ early_revenue_ramp / pre_revenue ────────────┐
│ DCF role: REFERENCE ONLY (too unreliable)      │
│ Kill rule: DISABLED (Model D handles this)     │
│ Target: Model D scenario-weighted EV +         │
│   ceiling + asymmetric entry price             │
│ DCF appears as "for reference: $X" footnote    │
│ This mode doesn't exist yet. Model D build.    │
└────────────────────────────────────────────────┘
```

After this fix, Auto mode and Socratic mode AGREE on how to use DCF for each archetype. The architectural divergence (Finding 1 in the filter audit) is resolved.

---

## Category 3: Informational Signals

**Definition:** Observations that are surfaced to the human but NEVER block analysis, alter targets, or force decisions. The human decides what to do with them.

**When to use:** The signal is genuinely useful but the right response depends on judgment that the system can't make. Different investors would reasonably react differently to the same signal.

### Current informational signals (keep as-is)

| Signal | What it tells you | Why it's not a gate |
|--------|------------------|---------------------|
| Analyst coverage / consensus level | Discovery alpha is lower for high-coverage stocks | KLA at 20 analysts is consensus — but analyzing it confirmed "pass," which is useful. Blocking analysis would have skipped the confirmation. |
| Macro regime (CPI, Fed, oil) | Affects timing and sizing for ALL positions | Macro is a frame for human judgment, not a binary signal. Two investors in the same macro can reasonably make different timing calls. |
| AI helps/threatens scores | Where a company sits on the disruption spectrum | APP at 95/5 is very different from ZI at 5/85. But the scores are shades of gray. Hard-gating at any threshold misses the nuance. |
| Wave health (momentum, crowding, beta) | Sector-level dynamics that affect all stocks in a wave | "This wave is overheated" is useful context. But contracted-backlog names in an overheated wave (LITE, SNDK) may outperform the wave average. The human decides. |
| Insider selling patterns | Bears are active / management is cashing out | 397 insider sells on APP is bearish. But insiders sell for many reasons (taxes, diversification, estate planning). The signal is real but the interpretation requires judgment. |
| Options flow / tactical signals | Short-term momentum dynamics | High call OI at $100-105 predicted a gamma squeeze. But tactical signals never override thesis signals. The human decides whether to trade tactically. |
| Future-pricing gap (priced-years vs actual-years) | How much of the monopoly is already in the stock price | A positive gap means alpha remains. But HOW positive, and whether to act on it, is judgment. |
| Timing categorization (收获期/半步领先/etc) | Where the discovery opportunity sits on the timeline | 收获期 means discovery alpha is exhausted. But future-pricing alpha may remain for chokepoints. The human decides. |
| Social sentiment / influencer positions | Momentum from retail crowd behavior | An influencer going all-in on ASTS is a momentum signal. It's NOT a thesis validation. The human separates tactical sentiment from fundamental analysis. |
| Storage cycle turn signals | Whether a specific sector cycle is peaking | "DRAM inventory at 2-3 weeks, none of 6 turn signals firing" is information. The human decides whether to hold SNDK through the cycle or take profits. |

### Properties of informational signals

- NEVER block analysis. NEVER alter targets. NEVER force a buy/sell.
- Always SURFACE prominently. Hidden information is useless information.
- Present alongside the analysis, not as a pre-filter. The Socratic output should include: "Note: this stock has 41 analysts (high consensus), insider selling at 397 transactions (unusually high), wave health is OVERHEATED (momentum +350%)."
- The human integrates these signals with the Socratic analysis to make a decision. The system presents. The human decides.

### The gravitational pull to watch for

Every informational signal is one bad day away from becoming a hard gate:

```
Signal: "insider selling is high"
  → Bad day: you hold APP, insiders sell 397 times, stock drops 20%
  → Temptation: add filter "block buy when insider_sells > 100"
  → Correct response: keep as informational, learn from the loss,
    adjust POSITION SIZING on high-insider-selling names, 
    don't add a gate

Signal: "wave is overheated"
  → Bad day: wave corrects 35%, your position drops with it
  → Temptation: add filter "don't buy stocks in overheated waves"
  → Correct response: keep as informational, factor into ENTRY
    TIMING (wait for macro correction), don't add a gate

Signal: "AI threatens score is rising"
  → Bad day: NOW drops 25% because AI agents bypass ServiceNow
  → Temptation: add filter "sell when ai_threatens > 40"
  → Correct response: keep as informational, fire a NOTIFICATION
    when score shifts >10 points, let human decide
```

The pattern: bad outcomes create emotional pressure to add hard filters. But the filter wouldn't have been appropriate BEFORE the bad outcome — the signal was genuinely ambiguous and required human judgment. Adding the gate after the fact is hindsight bias encoded in code.

**The discipline: after every loss, ask "would a hard gate have been correct IN ADVANCE, or am I reacting to a specific outcome?" If the former, add the gate. If the latter, keep the signal informational and improve how prominently it's surfaced.**

---

## How to use this framework going forward

### When adding ANY new filter to the codebase:

```
Step 1: What does this filter catch?
  → Fact error (data wrong, system bug, compliance violation)?
     → Category 1: Hard Gate. Always enforce.
  → Context-dependent analytical choice?
     → Category 2: Contextual Routing. Route by archetype/timing/macro.
  → Useful observation for human judgment?
     → Category 3: Informational Signal. Surface, never block.

Step 2: What's the false-positive cost?
  → If blocking a good stock costs more than passing bad data:
     → Probably Category 2 or 3, not Category 1.
  → If passing bad data could corrupt all downstream analysis:
     → Category 1.

Step 3: Would two reasonable investors disagree about this?
  → Yes → Category 3 (informational). 
     Different people, different risk appetites, different judgments.
  → No, but the right action depends on the stock type → Category 2.
  → No, it's always wrong → Category 1.
```

### Audit schedule

Re-run the filter audit quarterly. Filters accumulate like barnacles. New gates get added during feature work. Each audit should:

1. Inventory all filters
2. Classify each as Category 1/2/3
3. Check for Category 1 filters that are actually making judgment calls (demote to 2 or 3)
4. Check for Category 3 signals that should be harder (rare — only when a fact-error pattern is discovered)
5. Check for orphaned filters (kill or revive, no dead code)
6. Verify hard gate count stays under 10

---

## Current filter inventory by category

### Category 1: Hard Gates (8 total — keep under 10)

1. EDGAR cross-validation halt (10%)
2. Anti-sycophancy (5% convergence)
3. Anti-contamination (validated_corrections)
4. SEC rate limit (120ms)
5. strict-fill guard
6. Cost runaway prevention
7. Max single-name exposure (30%) — TO ADD
8. Max portfolio leverage ratio — TO ADD

### Category 2: Contextual Routing (7 — all need fixing)

1. DCF role → route by archetype (URGENT)
2. Kill rule threshold → route by archetype (after DCF)
3. Module 1 data validation → split: EDGAR=hard, trajectory=informational
4. Analysis routing → route by timing category × held
5. Non-US discovery minimum → route by archetype
6. Valuation emphasis → route by timing category
7. Position sizing → route by signal maturity

### Category 3: Informational Signals (11 — never gate)

1. Analyst coverage / consensus
2. Macro regime
3. AI helps/threatens scores
4. Wave health (momentum, crowding, beta)
5. Insider selling
6. Options flow / tactical signals
7. Future-pricing gap
8. Timing categorization
9. Social sentiment
10. Cycle turn signals
11. Competitive signals (patent lawsuits, customer overlap)

### Dead (kill)

~~1. Adversarial filter prepass v3 (orphaned prompt, no caller)~~
~~2. Convergence detector (orphaned code, no caller)~~

**Correction (2026-05-26):** both "kill" items were misclassified by the audit. Verification before deletion found:
- `convergence_detector.py` is ACTIVE — `app/api/convergence/route.ts` (Next.js API route) mirrors its logic; classes "must stay in sync." Python-only grep missed the TypeScript caller. Reclassify: KEEP.
- `adversarial_filter_prepass_v3.md` is DORMANT BY DESIGN — its own INTEGRATION NOTES say it's awaiting Module 8 ≥20 closed outcomes before being wired in. Reclassify: DORMANT (re-entry trigger documented in the file itself).

Lesson: the 7-step workflow's verify-before-destruction step caught this. No deletions executed. The "Dead (kill)" category is empty for now.

---

## Open Questions (raised in conversation, not yet resolved)

These are pushbacks Claude raised during the discussion of this document on 2026-05-26. The framework itself is canonical; these specific items remain open and should be revisited when the relevant rework happens.

1. **Are the two new hard gates (Max 30% single-name, Max portfolio leverage) mis-categorized as Category 1?** The argument for Category 2 (Contextual Routing): position sizing should route by signal maturity per `user_position_sizing_discipline` (5% first-touch → 10% T+30 → 15-20% T+60 with thesis intact). Leverage exposure depends on macro regime. A 30% position in a verified chokepoint with explicit stops may be defensible; a 30% position in a pre-revenue moonshot is not. The counter-argument that preserves Category 1 status: if Hume specifically wants a self-imposed hard ceiling as a "Ulysses contract" — binding his future self against emotional pressure in the moment — that IS a legitimate hard gate, but should be framed honestly as such ("I am binding my future self") rather than as a derivation that no thesis justifies the concentration. To resolve when position-sizing rework happens.

2. **Is the "fewer than 10 hard gates" complexity budget arbitrary?** Useful as discipline but the limit at 10 is not derived. The right limit is "as few as actually catch fact errors, no more." Suggested reframe: "Hard gates are added only when they catch fact errors. Audit count quarterly. If the audit reveals more than 10, the burden of proof shifts: existing gates must be re-justified or demoted." Cosmetic but worth deciding.

3. **Insider selling signal surfacing.** The current framing ("397 transactions, interpretation requires judgment") is correct as a Category 3 signal. But the surfacing should make DEVIATION explicit: "397 sells vs 5yr average 20/year = 20x normal" gives the human a sharper signal than raw counts. Implementation detail — but the philosophy doc's example would be more useful with the deviation framing.
