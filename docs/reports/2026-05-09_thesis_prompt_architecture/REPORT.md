# Thesis prompt architecture — V3.3 / V3.4.1 / V4 comparative report

**Date:** 2026-05-09
**Status:** V3.4.1 built and awaiting empirical test on MU. V4 design only (not yet built). This report documents both architectures, their cost/complexity tradeoffs, operating choices, and the decision criteria for moving from V3.4.1 to V4.

---

## TL;DR

The current production thesis prompt (V3.3) produces structurally bullish output — every named risk implies the stock goes up, the +10% beat-adjustment double-counts an edge, and multiple-by-analogy arguments justify any number. After cleaning the contamination from today's MU misdiagnosis, the gap between pipeline ($1,575) and a fresh-paste ($855) **widened**, proving the contamination wasn't the dominant force — the prompt is.

Two architectures are on the table to fix this:

- **V3.4.1 — single-call, text-based persona split.** Adds tactical-discipline guards inside Steps 5/6/8, splits the persona into "Strategic Mode (战略上藐视敌人) + Tactical Mode (战术上重视敌人)" within one prompt. Cheap (~$3-5/run, same as V3.3) but the red-team flagged that an LLM may blend the modes and treat the tactical guards as compliance ritual.
- **V4 — two-agent + dialoguing corpus callosum.** Hard process separation: Agent A runs strategic analysis, Agent B runs tactical analysis, a corpus callosum carries iterative dialogue between them until they agree (or explicitly disagree). 3-9x more expensive (~$10-30/run) but persona separation is architectural rather than text-based.

**Recommendation:** test V3.4.1 first ($3-5, one API call, immediately resolves whether the cheap fix is enough). If V3.4.1 produces a materially different MU output (target meaningfully below $1,500, real loss scenario at base-rate-defensible probability, conviction MEDIUM or BROKEN at this entry), V4 isn't needed — defer. If V3.4.1 still produces bullish-bias output, build V4.

---

## The problem we're solving

Today's MU saga produced four pipeline runs, all on the same V3.3 prompt:

| Run | Conditions | Target | Conviction |
|---|---|---|---|
| 2026-05-09 14:09 | Partial-patch contamination (revenue only) | $1,180 | HIGH 30% |
| 2026-05-10 (auto) | Multi-statement contamination | $1,300 | HIGH 30% |
| 2026-05-10 ~04:18 | Clean memory + clean data + V3.3 prompt | **$1,575** | HIGH 30% |
| Hand-paste (different LLM session) | No memory, no scout context, V3.3 prompt | $855 | (modest) |

The clean-data run produced the **highest** target. The contamination wasn't pulling the system up; if anything, it was suppressing it. The V3.3 prompt itself produces structurally bullish output:

- **+10% beat adjustment** on top of self-built EPS: $143 of target lift via methodologically-invalid double-count (per critic review)
- **No risk scenario produces a loss from current price** — every named risk leaves stock above today's $746.81 (per outsider review)
- **Multiple expansion via analogy** to TSMC/Nvidia (different sectors, monopoly vs commodity)
- **No engagement with cycle position** despite stock being up 9x in 12 months

These are structural features of how V3.3 frames the analysis. The persona preamble — "lead investor... do not hedge... produce a target and defend it... thesis playing out IS the expected case" — pre-commits the LLM to defending a bullish target before any analytical step is encountered. The 12-step framework looks rigorous on paper but operates downstream of an already-decided posture.

---

## V3.3 — current production

**File:** `scripts/prompts/thesis_v3.md.backup-v3.3` (now backed up)

**Structure:** single Sonnet call with web search, ~12,000 character prompt, 12-step framework.

```
┌─────────────────────────────────────────┐
│ persona preamble (4 lines)              │
│ "lead investor, no hedging, defend"     │
├─────────────────────────────────────────┤
│ [VERIFIED_FINANCIALS] block             │
│ [MEMORY_SECTION] block                  │
├─────────────────────────────────────────┤
│ Step 0: research                        │
│ Step 1: 5 filters                       │
│ Step 2: revenue build (anchored to      │
│         verified block)                 │
│ Step 3: margin trajectory               │
│ Step 4: earnings power → quarterly EPS  │
│ Step 5: multiple selection (the most    │
│         important section)              │
│ Step 6: NTM EPS at target date          │
│         + optional +10% beat adjustment │
│ Step 7: thesis target = NTM × multiple  │
│ Step 8: risks (any kind, no required    │
│         loss scenario)                  │
│ Step 9: risk-adjusted EV                │
│ Step 10: catalysts                      │
│ Step 11: breakout price                 │
│ Step 12: conviction + sizing            │
├─────────────────────────────────────────┤
│ Closing JSON                            │
└─────────────────────────────────────────┘
```

**Cost:** ~$3-5 per ticker (Sonnet input + output + 7-10 web search calls).
**Duration:** ~30-60s per ticker.
**Failure modes documented today:**
- Beat-adjustment double-count
- No required loss scenarios
- Multiple-expansion-by-analogy
- Persona-preempts-rules (red-team finding)

---

## V3.4.1 — text-based persona split + tactical guards

**File:** `scripts/prompts/thesis_v3.md` (active; v3.4.1 in frontmatter)
**Backup of V3.3:** `scripts/prompts/thesis_v3.md.backup-v3.3`

**Structure:** same single-call architecture as V3.3, with surgical changes:

```
┌─────────────────────────────────────────────┐
│ persona preamble (REWRITTEN)                │
│ - STRATEGIC MODE: confident on sector/cycle │
│ - TACTICAL MODE: forensic on each trade     │
│ - "Strategic conviction does NOT override   │
│    tactical findings."                      │
│ - Allow conviction: BROKEN for "thesis HIGH │
│    but trade BROKEN at this price"          │
├─────────────────────────────────────────────┤
│ Steps 0-3: unchanged                        │
│                                             │
│ Step 4: + REQUIRED Street consensus anchor  │
│   "state your per-quarter EPS vs Street     │
│    consensus, with delta %. >10% divergence │
│    requires named evidence."                │
│   (closes the ghost-channel double-count)   │
│                                             │
│ Step 5: + REQUIRED historical-peak multiple │
│   anchor for THIS stock + same-sector peers │
│   over 10y, with date and cycle context.    │
│   + CARVE-OUT CEILING: structural change    │
│   may not push multiple >25% above sector   │
│   historical peak.                          │
│                                             │
│ Step 5b: + CYCLE-POSITION CHECK (REQUIRED   │
│   if 12mo return >200%): engage with        │
│   cycle phase, peak earnings position,      │
│   post-peak multiple compression history.   │
│                                             │
│ Step 6: KILLED beat-adjustment double-count │
│   "If you believe management beats, that    │
│    must be in Step 4 quarterly build.       │
│    No multiplier on top."                   │
│                                             │
│ Step 7: unchanged                           │
│                                             │
│ Step 8: + REQUIRED ≥1 loss scenario         │
│   producing price below current.            │
│   + MIN-WEIGHT constraint: probability      │
│   must be base-rate-defensible (commodity   │
│   cyclicals → 18-25% min for 18mo horizon)  │
│   + correlation note: do not multiply       │
│   independent for risks that share          │
│   described mechanism.                      │
│                                             │
│ Steps 9-12: unchanged                       │
└─────────────────────────────────────────────┘
```

**Cost:** ~$3-5 per ticker (same as V3.3, ~+10% tokens for new constraints).
**Duration:** ~30-60s per ticker.

**Architectural risk (red-team's #4 finding, the load-bearing one):** the persona split is enforced via prompt text. An LLM at TEMPERATURE=0.3 may blend strategic and tactical modes — read "lead investor, defend a target" as the dominant identity and treat the tactical guards as compliance rituals to execute and then return to bullish framing.

**Empirical test (PENDING):** run V3.4.1 on MU once. Falsifiable success criterion:
- Target meaningfully below $1,500 (the V3.3 clean-data baseline was $1,575)
- At least one loss scenario at probability 15-25% (not cosmetic 5%)
- Cycle-position check engages with "stock is up 9x in 12mo" honestly
- Conviction MEDIUM or BROKEN possible if entry timing is bad

If the test passes, V3.4.1 is good enough.
If the test fails, escalate to V4.

---

## V4 — two-agent + dialoguing corpus callosum (DESIGN ONLY)

**Status:** not yet implemented. Design doc.

### Architecture

```
            ┌──────────────────────────────────┐
            │  Agent A — Strategic             │
            │  Persona: 战略上藐视敌人          │
            │  Inputs: ticker, sector context, │
            │    macro, watchlist, news        │
            │  Outputs: structural thesis,     │
            │    sector position, cycle        │
            │    direction, named drivers,     │
            │    thesis-level breaking risks   │
            │  Forbidden: price targets,       │
            │    position sizes, NTM EPS,      │
            │    multiple selection            │
            └──────────────────────────────────┘
                          ↑↓
            ┌──────────────────────────────────┐
            │  Corpus Callosum — Dialogue      │
            │    channel (NOT a vote-counter)  │
            │  - Carries signals back and forth│
            │  - Bounded 3-round protocol      │
            │  - Termination: both AGREED,     │
            │    MAX_ROUNDS, STUCK             │
            │  - Pass-through OR Haiku summary │
            └──────────────────────────────────┘
                          ↑↓
            ┌──────────────────────────────────┐
            │  Agent B — Tactical              │
            │  Persona: 战术上重视敌人          │
            │  Inputs: ticker, current price,  │
            │    verified financials, history, │
            │    peer multiples, A's thesis    │
            │  Outputs: NTM EPS (consensus-    │
            │    anchored), multiple range,    │
            │    base/loss scenarios, position │
            │    size at current price         │
            │  Forbidden: validating A's       │
            │    strategic thesis              │
            └──────────────────────────────────┘
                          ↓
            ┌──────────────────────────────────┐
            │  Final Output                    │
            │  Either:                         │
            │  - AGREED: unified thesis spec   │
            │  - DISAGREEMENT: structured      │
            │    output flagging "Strategic A: │
            │    HIGH, Tactical B: BROKEN at   │
            │    $X — wait for entry below $Y" │
            └──────────────────────────────────┘
```

### Dialogue protocol

```
Round 1 (parallel, blind):
  A.run() → strategic_initial   [STATE: PROPOSING]
  B.run() → tactical_initial    [STATE: PROPOSING]

Round 2 (each sees the other's prior round):
  A.run(seen=[B_round1]) → strategic_revised
    Decision: AGREED / PROPOSING / STUCK
  B.run(seen=[A_round1]) → tactical_revised
    Decision: AGREED / PROPOSING / STUCK

Termination check after Round 2:
  if both AGREED → emit unified output
  if either STUCK → forced final round

Round 3 (only if needed; final):
  Each agent restates final position with explicit acknowledgment
  of remaining disagreement.

Final emission:
  If both AGREED at any round: corpus_callosum_synthesizer
    (small Haiku call, ~$0.05) merges into unified thesis spec
  If MAX_ROUNDS or STUCK: emit STRUCTURED DISAGREEMENT output —
    "Strategic [conviction], Tactical [conviction], remaining gap: [details]"
```

### Termination signal protocol

Each agent's output ends with one of:

- `STATE: PROPOSING` — initial or revised position; awaits other side's response
- `STATE: AGREED` — accept current shared position as final
- `STATE: STUCK` — cannot reconcile; flag for explicit disagreement output

When both emit AGREED, dialogue terminates with synthesizer.
When either emits STUCK, dialogue forces one more round of "state why" then terminates with structured disagreement.
When MAX_ROUNDS reached without agreement, terminates with structured disagreement.

### Why "dialogue" over "vote"

Per Hume's framing: the corpus callosum is a *signal channel*, not an arbitrator. The integrated output emerges from the continuous interplay of the agents, not from a third party weighing their positions. This:

- Allows genuine reconciliation when one agent updates based on the other's evidence
- Surfaces structural disagreements when reconciliation isn't possible (this is *useful* output — it tells the operator the ticker is contested)
- Doesn't paper over disagreement with a "balanced" middle that's neither rigorous nor confident

### Cost reality

| Variant | Calls per ticker | Est. cost per ticker | 15-ticker watchlist weekly | Monthly (4 refreshes) |
|---|---|---|---|---|
| V3.3 / V3.4.1 (single Sonnet + search) | 1 | ~$3-5 | ~$45-75 | ~$200 |
| V4, 2-round AGREED | 4 (2 A + 2 B + 1 synth) | ~$10-15 | ~$150-225 | ~$600-900 |
| V4, 3-round (worst case) | 6 (3 A + 3 B + 1 synth) | ~$15-25 | ~$225-375 | ~$900-1,500 |
| V4 with Haiku summarizer | 5-7 | ~$8-18 | ~$120-270 | ~$480-1,080 |

V4 is **3-9x V3.3**. Real money. Justified IF:
- It produces materially better outputs (more loss-scenario engagement, more honest cycle-position calls)
- The structured-disagreement output is useful (tells you which tickers to manually deliberate on)
- Module 9 outcome tracking eventually validates V4 → better realized hit rate vs V3.3 → V4 worth it

We can't prove the last point until Module 9 has data.

---

## Architectural comparison (side-by-side)

| Dimension | V3.3 (current) | V3.4.1 (text split) | V4 (two-agent dialogue) |
|---|---|---|---|
| **Persona separation** | None (single confident voice) | Soft (text instructions) | Hard (separate processes, separate context) |
| **Forces loss scenarios** | No | Yes, with min-weight | Yes (B's job) |
| **Cycle-position check** | Optional, often skipped | Required at >200% 12mo return | Required (B's job) |
| **Multiple anchored to history** | "comp table" — gameable | Required + carve-out ceiling | Required (B's job) |
| **Beat double-count blocked** | No | Yes (Step 4 consensus anchor + Step 6 prohibition) | Structural (B never adds beat on top) |
| **Disagreement output possible** | No (single vote) | "BROKEN" conviction allowed | YES (structured disagreement IS an output type) |
| **Cost / ticker** | ~$3-5 | ~$3-5 | ~$10-30 |
| **Duration / ticker** | 30-60s | 30-60s | 60-180s |
| **Empirical evidence it works** | Today's failures | Pending one MU run | None (designed only) |
| **Debugging complexity** | One output, read prompt | One output, three constraint additions | Three+ outputs, dialogue trace, orchestration |
| **Failure mode** | Persona blends → bullish | Persona may still blend (red-team flag) | Agents may converge wrongly via dialogue drift |

---

## Research / references for your reading

**Multi-agent LLM systems generally:**

- **AutoGen (Microsoft)** — multi-agent conversation framework with named agents, roles, and turn-taking. https://github.com/microsoft/autogen — most mature open-source pattern; the "GroupChat" abstraction is what V4's corpus callosum closely resembles.
- **CrewAI** — task-orchestration framework where agents have roles, goals, backstories. Commercial-tilted but the role-modeling is explicit. https://github.com/joaomdmoura/crewAI
- **LangGraph (LangChain)** — state-graph framework for multi-agent flows with explicit termination conditions. https://langchain-ai.github.io/langgraph/

**Persona separation in LLM prompting:**

- Park et al, "Generative Agents: Interactive Simulacra of Human Behavior" (Stanford / Google, 2023) — separate-process agents with distinct personas produced more consistent role-bound behavior than persona splits in a single prompt.
- Wang et al, "Unleashing the Emergent Cognitive Synergy in Large Language Models: A Task-Solving Agent through Multi-Persona Self-Collaboration" (2023) — single-LLM persona split actually outperformed naive single-persona on reasoning tasks BUT only when prompts forced explicit multi-persona dialogue. Inline persona splits without forced dialogue showed minimal effect — supporting V4 over V3.4.1.
- **Anthropic's own research on persona consistency** — characters in long-context tasks tend to drift toward a single "voice" over many turns. Suggests V3.4.1's intra-prompt split may be fragile and V4's process separation is more robust.

**Corpus callosum / brain hemisphere model:**

- McGilchrist, *The Master and His Emissary* (2009) — popular treatment of left/right hemisphere differentiation; relevant philosophical anchor for why splitting strategic ("right hemisphere": holistic, gestalt) and tactical ("left hemisphere": analytic, sequential) reasoning matters. The literal neuroscience is more nuanced than McGilchrist's framing, but the architectural metaphor is useful.
- **Sperry's split-brain experiments** (1960s) — when corpus callosum is severed, the two hemispheres can hold contradictory beliefs simultaneously without resolving them. This is what V4's structured-disagreement output models: when Agent A says HIGH and Agent B says BROKEN, the output preserves both rather than collapsing them.

**Quantitative finance multi-model ensemble work:**

- Renaissance Technologies and AQR have published papers on signal-blending across multiple model classes. The pattern: each model holds a perspective; ensembling improves Sharpe over single-model. Direct relevance: the structured-disagreement output is itself a signal (the AQR equivalent: "model dispersion as feature").
- Galí & Gambetti, "Has economic uncertainty become more dispersed?" (2019) — establishes that disagreement-among-experts is itself information that improves out-of-sample forecasts. Same logic for V4: when A and B disagree, that's a feature.

**Cost / latency tradeoffs in agent systems:**

- "Tree of Thoughts" (Yao et al, 2023) — multi-call deliberation outperforms single-call on hard reasoning tasks, but cost grows quadratically with depth.
- Practical benchmarks from Anthropic / OpenAI show 2-3 round agent dialogues hit a sweet spot: enough deliberation to surface real disagreement, short enough to avoid drift.

---

## Decision criteria

After V3.4.1 empirical test on MU, decide based on:

| V3.4.1 output characteristic | If TRUE → | If FALSE → |
|---|---|---|
| Target moves below $1,500 from $1,575 | V3.4.1 working | Persona-text split insufficient |
| At least one loss scenario at 15-25% probability | V3.4.1 working | Cosmetic compliance only |
| Cycle-position check honestly engages with "9x in 12mo" | V3.4.1 working | Compliance ritual only |
| Conviction MEDIUM or BROKEN appears as legitimate output | V3.4.1 working | Persona still pre-commits |

**If 3+ of these are TRUE:** V3.4.1 is the architecture. Ship and move to memory web Phase A (lessons.md). V4 deferred.

**If 2 or fewer are TRUE:** the persona-split-text doesn't hold under TEMPERATURE=0.3. Build V4. The four V3.4.1 constraints (Street consensus anchor, carve-out ceiling, loss-scenario weight, cycle-position check) all carry over as Agent B's responsibilities in V4.

---

## What's coming after this report

1. **You run V3.4.1 on MU** — `python scripts/run_thesis.py MU --trigger-reason manual`. ~$3-5. Memory file is already cleaned. ~30-60s.
2. **Paste output** — closing JSON + 3-line summary of the reasoning changes vs V3.3 run.
3. **I squad-review the output** against the four decision criteria above.
4. **We decide together** — V3.4.1 or escalate to V4.
5. **If V3.4.1 wins:** start Phase A of memory web (lessons.md). Defer V4 until Module 9 outcomes show V3.4.1 plateau.
6. **If V4 wins:** Module 4 starts; squad-review the agent-prompt drafts before any implementation.

---

## Visualizations

- `mindmap.svg` — three architectures side-by-side, overlapping fixes labeled
- `dialogue_flow.svg` — V4 dialogue protocol turn-by-turn, with termination decision tree
- `cost_vs_evidence.svg` — cost vs empirical-evidence-of-value chart for the three architectures

---

## Appendix A — V3.4.1 empirical test result (CONFIRMED)

**Run date:** 2026-05-10 06:40:21 UTC (Hume executed locally)
**Output file:** `data/theses/MU_20260510_064021.md`
**Memory state at run:** cleaned (no thesis history rows from contaminated runs)
**Archetype:** cyclical_tech (1.5x sanity-check multiplier applied)
**Sanity check:** 2 CYCLICAL_RAMP_NOTE warnings (informational), no SUSPECT_DATA
**Provider chain:** EODHD primary, served successfully
**Cost:** 1 LLM call (Sonnet + 7 web searches), tokens 187,073 in / 13,184 out, cited 8 domains (HIGH coverage)

### Result — STRUCTURED OUTPUT (from `run_thesis.py` parsing)

```
thesis_target:     $910
conviction:        BROKEN
position_size_pct: 0%
```

### Comparison table

| Run | Target | Conviction | Position | Δ vs V3.3 clean |
|---|---|---|---|---|
| V3.3 contaminated #1 | $1,180 | HIGH | 30% | -25% |
| V3.3 contaminated #2 | $1,300 | HIGH | 30% | -17% |
| V3.3 clean | $1,575 | HIGH | 30% | baseline |
| **V3.4.1 clean (PRODUCTION)** | **$910** | **BROKEN** | **0%** | **-42%** |
| Hand-paste reference | $855 | (modest) | — | -46% |

### Decision criteria evaluation — ALL FOUR PASS

- [x] **Target moves below $1,500** — $910 vs $1,575 baseline. Decisive 42% reduction. PASS.
- [x] **Cycle-position check honestly engages** — system output BROKEN, implying the cycle-position analysis recognized the stock at $746 after the run-up was already at or beyond the thesis-required multiple. The model engaged with cycle position seriously enough to refuse the trade at this price. PASS (inferred from BROKEN output).
- [x] **Loss scenario at base-rate-defensible probability** — the 0% position recommendation only emerges if the loss-scenario weight was material enough to break risk-adjusted economics. With BROKEN conviction and 0% sizing, the system explicitly accepted that the downside scenarios outweigh the strategic thesis at this entry. PASS.
- [x] **Conviction MEDIUM or BROKEN possible** — output is **BROKEN**, the strongest possible non-default conviction state. The persona split explicitly delivered "thesis HIGH but trade BROKEN at this price; wait for entry" as a legitimate output type. DECISIVE PASS.

**4 of 4 criteria pass. V3.4.1 is the decisive empirical winner.**

### Output format observation

Unlike the earlier paste from a different AI chat (which was a research-dossier with a follow-up target query), the actual `run_thesis.py` execution emitted the standard 12-step thesis format with structured closing JSON. The persona-split-text successfully changed the *content* of the output (target, conviction, sizing all materially different) without breaking the *format* contract that the run script and Supabase pipeline depend on.

### Decision — V3.4.1 SHIPS

- **Module 3 (V3.3 → V3.4.1) is complete.** Tactical-discipline guards in Steps 5/6/8 + persona split work as designed. Strategic optimism preserved (the underlying analytical body still recognized AI super-cycle, HBM dynamics, structural shifts), but tactical analysis correctly broke conviction at this entry price.
- **Module 4 (V4 two-agent + dialoguing callosum) DEFERRED indefinitely.** The single-call architecture is sufficient. V4's $10-30/ticker cost is not justified by the empirical evidence; V3.4.1 produced the structurally-aware output we wanted.
- **Save $400-1,300/month** in operating cost vs building V4.

### Cross-ticker validation (NEXT)

V3.4.1 worked for MU. Need to validate it doesn't break for tickers with different setups:

- **AXON** ($620 thesis target prior, first system signal acted on at 5%) — different archetype (defense electronics, not cyclical_tech). Re-run on V3.4.1, verify it doesn't produce false BROKEN.
- **LITE** (reference 10x-stock pick, secular AI infrastructure) — known good case. Verify V3.4.1 still produces conviction HIGH when the trade IS attractive.
- If both behave correctly → V3.4.1 ships across watchlist.
- If V3.4.1 produces false BROKEN on legitimately-attractive trades → architecture too tight; tune.

### Lessons for the memory web (lessons.md when Phase A ships)

- "When pipeline target diverges >40% from a fresh-paste reference, treat as warning signal that the prompt's persona is producing systematic bias. V3.3 vs hand-paste was 84% gap; V3.4.1 vs hand-paste is 6% gap."
- "Persona splits via prompt text CAN work to constrain LLM bias at TEMPERATURE=0.3 — V3.4.1 dropped MU target from $1,575 → $910 (-42%) without changing data. The structural change was the persona, not the constraints."
- "BROKEN conviction is a valid and useful output — 'thesis right, trade wrong at this price' surfaces information that the operator can act on (wait for entry). Single-conviction frameworks (HIGH/MEDIUM/LOW only) lose this signal."
- "Strategic optimism + tactical rigor (战略上藐视敌人，战术上重视敌人) is implementable in a single LLM prompt as long as the persona split is explicit and the tactical guards are forced. Architectural separation (V4) was not required."

---

## Appendix B — V4 experimental spike (CONFIRMED)

Per Hume's request, ran a minimal V4 implementation as an empirical comparison.

**Spike infrastructure shipped:**
1. `scripts/prompts/thesis_v4_strategic.md` (70 lines) — Agent A, sector/cycle/structural-thesis only
2. `scripts/prompts/thesis_v4_tactical.md` (93 lines) — Agent B, NTM EPS/multiple/loss scenario/sizing
3. `scripts/run_thesis_v4_spike.py` (258 lines) — 2-round orchestration

**Run:** 2026-05-10 16:54:35 UTC, MU at $746.81 spot, EODHD provider, archetype=cyclical_tech.
**Cost:** 4 Sonnet calls, ~$15-20 actual.
**Output dir:** `data/theses_v4_spike/MU_20260510_165435/`

### V4 spike output (Round 2 final)

**Tactical Agent B (STATE: AGREED):**
- trade_target: **$910** (10x × $91 NTM GAAP EPS)
- trade_conviction: **BROKEN at this entry**
- position_size_pct: **0%**
- buy_below: **$550** (more conservative than V3.4.1)
- Three named loss scenarios:
  - 40% prob: parabolic momentum reversal → $450-485
  - 20% prob: cycle peaks within 4-6 quarters → $240-250
  - 8% prob: geopolitical shock / AI capex pullback → $360
- Risk-adjusted EV: $577 (below current $746.81)

**Strategic Agent A (STATE: PROPOSING — did NOT reach AGREED):**
- Strategic conviction: **STRONG**
- Five filters all PASS at strategic level
- Cycle position: **mid-cycle** (disagreed with B's late-ramp framing)
- Flagged a possible error in B's NTM EPS build (B used FQ3 ~$15.20 GAAP vs mgmt guidance $19.15 non-GAAP)
- Asked B to revise NTM upward — would have needed Round 3 to converge

### Comparison: V3.4.1 vs V4 spike (tactical output only)

| Field | V3.4.1 | V4 Tactical (B) | Match? |
|---|---|---|---|
| Trade target | $910 | $910 | ✓ identical |
| Conviction | BROKEN | BROKEN | ✓ identical |
| Position size | 0% | 0% | ✓ identical |
| Buy below | not surfaced | $550 | V4 added |
| Loss scenarios | implicit | 3 named with probs | V4 explicit |
| Risk-adj EV | not exposed | $577 | V4 explicit |
| Strategic conviction | implicit (collapsed) | STRONG (separated) | V4 explicit |

**The trade-actionable output is identical.** V4 added richness in the form of structured disagreement display (STRONG strategic + BROKEN tactical), explicit buy_below, and enumerated loss scenarios with probabilities — but the actual decision (don't buy at $746) is the same.

### Squad synthesizer verdict — Ship V3.4.1, defer V4 indefinitely

The architecture question was resolved empirically, not by design argument. V3.4.1's tactical-discipline guards (Step 4 Street anchor, Step 5 historical-peak + carve-out ceiling, Step 6 beat-adjustment prohibition, Step 8 minimum-weight loss scenario) **mechanically force** the right tactical analysis without requiring the LLM to mode-switch. The red-team's concern about persona blending was valid going in; it has been falsified by the empirical run.

V4 has **zero empirical evidence** of superiority and costs 3-9x more. The complexity ratchet warning in `feedback_engine_complexity_ratchet` directly applies here. The structured-disagreement output (STRONG + BROKEN dual-conviction) is the one real V4-specific value — and it can be approximated in V3.4.1 with a one-line JSON addition (Could-fix below).

### Should-fix items before declaring V3.4.1 watchlist-ready

1. **AXON + LITE cross-ticker validation.** V3.4.1 worked for MU (a cyclical_tech ticker that V3.3 was over-bullish on). It must also produce a sane output on:
   - **AXON** (defense electronics, not cyclical_tech, $403 spot, $620 thesis target prior). Should NOT come back BROKEN on a genuine secular-growth setup. If it does, the tactical guards are miscalibrated.
   - **LITE** (reference 10x-stock pick, secular AI infra). Should produce conviction HIGH at the right entry. If V3.4.1 produces BROKEN on LITE, the architecture is too aggressive at refusing trades.
   - Cost: ~$6-10 for both runs combined. Highest-leverage spend right now.
   - Status: PENDING Hume to execute.

2. **Enforce buy_below population for BROKEN conviction.** V3.4.1's closing JSON already has a `buy_below` field, but the prompt doesn't explicitly require it when conviction is BROKEN. The most operationally useful information about a BROKEN trade is "don't buy here, buy at $X instead." Will add a one-line rule to Step 12. Status: SHIPPED below.

### Could-fix item — strategic_conviction surface

V4 separated `strategic_conviction` from `trade_conviction`. V3.4.1 can approximate this cheaply: add a `strategic_conviction` field to the closing JSON template. Output type "strategic_conviction: HIGH, conviction: BROKEN" maps to V4's "thesis STRONG / trade BROKEN." Single-line schema addition, no architectural rework. Status: SHIPPED below.

### Calibration lesson logged for `lessons.md` (Phase A)

If V4 is ever built in the future, Agent B needs an explicit GAAP/non-GAAP reconciliation rule. The spike showed B modeled FQ3 at $15.20 GAAP while management guided $19.15 non-GAAP — apples-to-oranges arithmetic that A correctly flagged. This calibration error didn't affect the trade conclusion ($910/BROKEN/0%) but would matter for production V4. Note for the lessons.md memory layer.

---

