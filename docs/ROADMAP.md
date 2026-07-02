# ROADMAP — reconciling the dual-system 2×2 and the 10× framework

**Status: DRAFT for owner decision** · 2026-07-02 (sprint 4.3)
This file did not exist despite being referenced by CLAUDE.md/README since
April; the backlog was fragmented across four partially-superseded documents.
One page, one decision: **which framework governs, and what is the next build
step.**

## The two frameworks overlap almost entirely

| Concept | DUAL_SYSTEM (06-27) | TEN_X (06-28) | Same thing? |
|---|---|---|---|
| Structural truth (what to own) | Type A / `strategic_conviction` | A1 activity record → A2 fuel/bottleneck → A3 prize | Yes — TEN_X decomposes Type A into three measurable pieces |
| Market response (what to do now) | Type B trade gate | B1 ignition/phase → B2 attention → B3 entry/size | Yes — B3 is the engine (built); B1 ≙ the "phase modulator"; B2 ≙ "attention factor" (Step 2) |
| Combination | 2×2 grid (strategic × attention) | **Gated cascade**: structural → confirmation → runway → value → size | **No — this is the real difference** |
| New in TEN_X only | — | 0→1 vs 1→100 modes; **confirmation gate = deal flow** (leading, factual); vision-as-funnel sourcing | — |

## Recommendation (decide and delete the other option)

**TEN_X governs the target architecture; DUAL_SYSTEM survives as the build
sequence for its first two pieces.** Rationale: TEN_X is newer, is a strict
superset (the 2×2 is the cascade with the confirmation and runway gates
collapsed away), and its gated-cascade combination rule is the direct fix for
the 6/6-BROKEN failure mode (axes must combine conditionally, never averaged —
the 2×2 alone would still let a momentum-trap quadrant read as "just timing").

Concretely, relabel the dual-system steps as TEN_X pieces:
- ~~Step 1~~ **done** (structural axis persisted; UI surfacing still open).
- Step 2 (attention factor) **= B2**. Unchanged scope; still timing-only, capped.
- Step 3 (Model B structural lens) **= A2/A3-lite**. Same prompt work; add the
  0→1 vs 1→100 branch to the framework decision-tree while the calibration
  clock is still empty (cheapest moment — cohort key resets on prompt change).
- Step 4 (2×2 verdict) **becomes the gated cascade**, with the 2×2 kept as its
  *display projection* (the grid is a great UI; it's just not the combiner).
- New, first: **A1 activity record** is the foundation TEN_X says everything
  judges, and nothing implements it today.

## Before building anything: the hand validation TEN_X itself prescribes

Run the cascade **by hand** on memory/HBM (MU/SNDK): does structural-gate →
deal-flow confirmation → runway → value produce a sharper verdict than the
engine's raw BROKEN did? One sheet of paper, zero code. If it does not beat
the engine's answer, the frameworks need rework before any of Steps 2–4 are
worth building. (Owner task — the operator's edge is the input here.)

## Sequenced next steps (post-consolidation-sprint)

1. **Owner:** hand-validate on memory/HBM (above). Confirm archetype tags
   (`docs/decisions/ARCHETYPE_PROPOSALS_2026-07-02.md`) and the target
   source-of-truth decision (`docs/decisions/TARGET_SOURCE_OF_TRUTH_2026-07-02.md`).
2. Surface the persisted structural axis in the UI (THESIS_FIELDS + StockRow
   dual-pill: "strategic HIGH / trade BROKEN / buy below $X") — completes the
   original Step-1 acceptance criterion.
3. A1 activity record (thin slice: per-ticker dated deal-flow log — design
   wins, LTAs, capacity reservations; doing-not-announcing filter).
4. B2 attention factor (env-gated, timing-only, capped) — unblocked once 2
   ships a place to show it.
5. A2/A3 Model B lens + 0→1/1→100 branch (accept the cohort reset now).
6. Gated cascade as the verdict combiner; 2×2 as its display; discovery
   candidates placed in the grid (revive or retire discovery explicitly then).

Superseded by this file: the step list in DUAL_SYSTEM_ARCHITECTURE.md §3
(kept for design rationale), HANDOFF_PRD_2026-06-24 P4/P5 (P4 kill-routing
folds into the cascade's value gate; P5 run_macro stays open ops debt),
data/todo_master_2026_05_26.md (historical).
