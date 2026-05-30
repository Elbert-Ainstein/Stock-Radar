# Master To-Do — Stock Radar (Big Picture)

**Date:** 2026-05-26 (end of session)
**Purpose:** Single canonical synthesis of every work item across all open documents — session 2 doc (19 items), filter audit recommendations, filter philosophy categorizations, accumulated memory, and operational decisions awaiting Hume.

**How to use this:** the priority queue at the top is the actionable plan. Everything below documents context — what's already shipped (so we don't redo it), what's deferred (and what triggers re-entry), and what open questions block specific items.

---

## BASELINE — preserved foundation for future before/after diffs

**Git tag:** `v3.5-foundation` (commit hash TBD when pushed)
**Baseline captures:**
- `data/baselines/2026-05-26_v3.5_dcf_floor_basket.txt` — LITE + CAMT + COHR + SIMO with `--dcf-as-floor`
- `data/baselines/2026-05-26_v3.5_primary_basket.txt` — same 4 stocks with default `dcf_role=primary`

**Purpose:** preserve current engine behavior so future changes (comp-selection audit, D1 kill rule, D-v2 archetype heuristic) have unambiguous before/after comparison. Without baseline, we'd be guessing whether a downstream change improves or regresses. The 17-fix-episode failure mode was changes shipping without baseline evidence; this fixes that pattern.

**Re-run trigger:** any engine code change. Compare new outputs against this baseline. Diff should match the stated intent of the change. If unrelated stocks move unexpectedly, that's a regression signal.

---

## A. SHIPPED THIS SESSION (2026-05-25/26)

Validated and committed. Reference for what NOT to redo.

| Item | Where | Validated by |
|---|---|---|
| §7 Model B anti-sycophancy hard rules | `prompts/socratic/model_b_regime.md` | LITE id=19: target_low $850 → $620, independent macro-beta math |
| §7b Future-pricing analysis (chokepoint conditional) | `prompts/socratic/model_b_regime.md` | LITE id=21: verdict flipped UPSIDE → DOWNSIDE via real PV math ($929 calc ≈ $947 spot) |
| §6 Macro context injection (already operational) | `run_socratic.py` build_context | id=19 stdout shows `[macro] regime=stagflation_risk (id=1)` + `[wave_health]` |
| `validated_corrections.md` cross-ticker fact layer | `data/validated_corrections.md`, `run_socratic.py`, all 5 socratic prompts | COHR id=25: verdict flipped UPSIDE → NO_REGIME_SHIFT once `$42B` contamination removed |
| LITE.md operator notes updated with id=21 findings | `data/operator_notes/LITE.md` | File now annotated; future runs see corrected facts |
| Filter audit | `data/filter_audit_2026_05_26.md` | Delivered with correction addendum after orphan-call mistake |
| Filter philosophy doc (canonical) | `data/filter_philosophy.md` | Saved verbatim + open questions appendix |
| 7-step change workflow (canonical) | Memory `feedback_change_workflow.md` | Saved + indexed in MEMORY.md |
| Audit-verification lesson | Memory `feedback_audit_verification.md` | Saved + indexed (orphan-call near-miss documented) |

**Validation runs this session:** LITE id=19, id=21 / CAMT id=22 / COHR id=23 (contaminated), id=25 (fixed) / SIMO id=20 (negative-case smoke).

---

## B. READY TO SHIP — light loop (no preconditions, single-file or smaller scope)

These pass the trivial-vs-non-trivial test in `feedback_change_workflow`. Falsifiable, single-file, low blast radius. Light loop (apply + falsifiable test) is sufficient — no full review-squad cycle needed.

| # | Item | Where | Pass criterion |
|---|---|---|---|
| B1 | Single milestone git commit covering this session's work | repo | `git push` succeeds; HEAD includes all files in section A |
| B2 | Consolidated CHANGELOG entry for the session | `CHANGELOG.md` | Single entry at top covering anti-sycophancy + future-pricing + validated_corrections + audit + philosophy + workflow |
| B3 | Update audit "Dead (kill)" category to empty (already done in addendum) | `filter_audit_2026_05_26.md` | Done — addendum landed |
| B4 | Update philosophy doc "Dead" category to reflect correction (already done) | `filter_philosophy.md` | Done — strike-through + correction note landed |
| B5 | Add insider-selling deviation surfacing (informational, no gate) | TBD scout / prompt | Informational signal shows "N sells vs Xyr-avg M" not just raw N |

---

## C. TIER 1 — build now (highest leverage, full 7-step workflow)

The single most urgent fix from the audit + philosophy doc.

### C1. DCF role contextual routing (`target_engine.py`) — **CLOSED 2026-05-26**

**Status:** SHIPPED + VALIDATED. Full 7-step workflow executed. Squad cycle found 3 sound fixes, all applied in one iteration. Validation iter 1 FAILED informatively (LITE auto-promoted to cyclical, exposed a separate routing bug). Iter 2 with `--archetype=secular_growth` override PASSED all 5 path-dependent checks. **D-v1 follow-on** in same cycle: built the missing `_load_archetype_override()` loader for `config/ticker_archetype_overrides.json` (config had existed since 2026-05-11 with LITE tagged "transformational" but no engine-side consumer). D-v1 validation PASSED without needing the manual `--archetype` flag. LITE Auto target band now $508/$1,127/$1,501.

**Cycle report:** `data/change_cycles/2026-05-26_dcf_reposition_v1.md` (includes D-v1 addendum).

**Outcomes:**
- Auto-vs-Socratic divergence on LITE closed (both engines now agree directionally on the bear floor and upside ceiling).
- 25-day debt from `user_dcf_is_wrong_primary` settled.
- New memory: `feedback_regime_shift_vs_historical_math` — unifying observation across DCF, V3.4.3 kill rule, archetype auto-promote.
- Open numerical question: transformational archetype produces target_high $1,501 vs secular_growth's $1,121 — meaningfully different. Worth a sanity-check on which archetype tilts are calibrated correctly before V2 deployment.

---

## D. TIER 2 — build after C1 lands (C1 now CLOSED 2026-05-26)

C1 + D-v1 unblocked these. D-v2 (archetype auto-promote audit) was added during C1 iter 1 when the LITE-as-cyclical mis-routing surfaced.

### D1. Kill rule threshold contextual routing (UNBLOCKED, ready)

After DCF role is routed by archetype, the V3.4.3 kill rule (currently fires uniformly at `risk_adj_ev_ratio < 0.90` per `prompts/thesis_v3.md:170-171`) gets routed too: cyclicals < 0.90 (current), regime-shift < 0.60 (wider), pre-revenue disabled (Model D handles when built). Pass criterion: re-run V3.4.3 on LITE with new DCF-as-floor target; expected to NOT fire BROKEN. **Requires `analyst.py` to pass `dcf_role` through to `build_target` first** (currently it loads archetype via Supabase but doesn't load dcf_role from anywhere). That's V2 wiring — a precursor to D1.

### D-v2. Archetype auto-promote audit (NEW, surfaced during C1 iter 1)

The auto-promote heuristic at `target_engine.py:2983` detects cyclicality via CV > 0.50 + margin sign-changes + prior negative-margin year — all read from HISTORICAL data that doesn't account for regime change. LITE auto-promoted to cyclical from its pre-2024 data despite the post-AI-supercycle business being structurally different. D-v1 lets operators sidestep this via explicit config tagging (`ticker_archetype_overrides.json`); D-v2 makes the heuristic itself regime-aware. Options: (a) recency-weight the CV calculation (recent quarters count more), (b) split detection into "is currently cyclical" vs "was historically cyclical" with regime-classifier, (c) suppress auto-promote when explicit override exists (D-v1 already does this implicitly). Per `feedback_regime_shift_vs_historical_math`: third instance of the same Category-2-acting-like-Category-1 bug pattern.

### D2. Module 1 split (EDGAR hard, trajectory informational)

Memory `feedback_data_guardrail_over_fit`. EDGAR cross-check stays Category 1 (Hard Gate — fact error). Trajectory smoothness becomes Category 3 (Informational warning, no block). Implementation: rewrite `_validate_quarterly_revenue` to query EDGAR via existing `edgar_xbrl.py` client, fall back to trajectory check as warning-only when EDGAR unavailable. Pass criterion: ASTS at commercial launch (50x QoQ from near-zero) passes without override flag.

### D3. Analysis routing by timing category × held status

Per filter philosophy: 收获期+not_held → Auto, 收获期+held → Socratic+future-pricing, 半步领先 → Socratic, 远见期 → Model D. Requires timing_category field on waves/stocks. Schema migration + harness routing logic. Pass criterion: a held position in 收获期 routes to Socratic on auto-refresh.

### D4. §10b Tactical signals layer

Two signal levels (tactical days/weeks, thesis months/years). Tactical NEVER overrides thesis. Options flow scout addition. Catalyst × options confluence. Per filter philosophy: tactical signals are Category 3 (Informational), never gating. Re-entry trigger: now MET (you have ASTS gamma squeeze as the motivating real-world case).

### D5. §7c Expectations decomposition + fast-sell

Re-entry trigger now MET (LITE id=21 + CAMT id=22 + COHR id=25 = 3 chokepoints with reliably structured §7b output). Auto-extract implied expectations from Model B's future-pricing analysis; store in `socratic_analyses.implied_expectations`; auto-generate notification rules for kill triggers. Major scope — schema + harness + alert infrastructure. Should run as its own 7-step cycle. Defer to confirm DCF reposition produces good upstream data before building on top.

---

## E. TIER 3 — investigate before committing

Smaller items needing data check before deciding to ship.

### E1. Non-US discovery archetype bypass

`MIN_QUARTERLY_ROWS_NON_US = 4` at `discovery_scan.py:85`. Add archetype-aware bypass: 2 quarters for `early_revenue_ramp`. Pass criterion: count non-US tickers SKIPPED with "fiscal-calendar guard tripped" in last 30 days; if any are interesting (small-cap, fast-growing, in a wave), the filter needs relaxation. Investigation effort: 30 min query.

### E2. Signal-store census

`MIN_SIGNALS_FOR_ADJUSTMENT = 10` in `feedback_loop.py:60`. Count current settled outcomes per scout. AXON is first signal (T+30 ~2026-06-08); likely <5 outcomes total exist. If census confirms feedback loop is effectively prior-only, document that the "system learns" claim is currently aspirational — not a code change, a status correction. Investigation effort: 30 min.

### E3. Insider selling deviation framing

Surface "397 sells vs 5yr-avg 20 = 20x normal" instead of raw count. Implementation in scout output formatting. Listed in B5 as ready-to-ship but only if we know which scout to modify. Need to identify the source. Investigation effort: 1 hour.

---

## F. DEFERRED — staying on shelf until trigger conditions

Per `feedback_one_step_falsifiable`, these stay in design docs but do NOT enter active queue until specific evidence triggers them.

### F1. Model D (Optionality / TAM frame)
- Source: session 2 doc §3 (updated version with 5-scenario framework, anti-fantasy guardrails, audit phrase)
- Re-entry trigger: macro injection on ASTS + Model B/C explicitly fail to handle optionality. Could be tested now since macro is shipped; would need a re-run of ASTS to see what Models A/B/C produce with the new framework.

### F2. Lateral trace discovery
- Source: session 2 doc §4
- Re-entry trigger: any TSEM-like discovery miss where Hume finds a competitor the engine missed. Until then, the existing wave-map + 13F + scout pipeline is adequate.

### F3. Revolution impact spectrum (ai_helps / ai_threatens scoring)
- Source: session 2 doc §10
- Re-entry trigger: calibration plan complete. Per `feedback_calibration_before_build` — score 10 stocks blindly, check inter-rater agreement before committing to schema + scoring methodology.

### F4. 灵感 mode (Spark / Insight conversation mode)
- Source: session 2 doc §9
- Re-entry trigger: at least 5 unstructured-input cases where the existing chat interface produced inadequate output. Until then, ad-hoc handling is fine.

### F5. 影响图谱 frontend (Impact Graph scatter plot)
- Source: session 2 doc §10
- Re-entry trigger: revolution_impact scoring methodology (F3) shipped and seeded. Frontend builds AFTER backend data.

### F6. Position sizing by signal maturity (Category 2 contextual routing)
- Per `user_position_sizing_discipline` + filter philosophy
- 5% first-touch → 10% T+30 → 15-20% T+60 with thesis intact
- Re-entry trigger: AXON T+30 outcome lands (~2026-06-08). First data point for whether the maturity schedule is correctly calibrated.

### F7. Timing categorization (收获期 / 半步领先 / 一步领先 / 远见期)
- Source: session 2 doc §5
- Schema work: `waves.timing_category` field, seeds per revolution
- Re-entry trigger: needed before D3 (analysis routing by timing × held). Ship D3-pre as schema + seeds; harness routing comes with D3.

### F8. COHR threat notification on LITE
- Source: session 2 doc §8
- Small SQL insert. Re-entry trigger: a notifications infrastructure exists (current state unclear — needs check).

### F9. Adversarial filter prepass v3 (re-wire)
- Source: existing prompt at `prompts/adversarial_filter_prepass_v3.md`
- Re-entry trigger: per its own INTEGRATION NOTES, Module 8 (outcome tracker) ≥20 closed outcomes. Currently 0-1. After AXON T+30 + LITE T+90 + future signals settle.

---

## G. OPEN QUESTIONS — need Hume decisions before action

These are NOT actionable items — they're decisions blocked on judgment that the system can't make.

### G1. Are Max 30% single-name + Max portfolio leverage Category 1 or Category 2?

The philosophy doc placed them as Category 1 (Hard Gate) with rationale "no thesis justifies this concentration." Claude pushed back that this is contextual routing in disguise — position sizing should route by signal maturity (per `user_position_sizing_discipline`), leverage should route by macro regime. Counter-argument: legitimate Category 1 if framed as a "Ulysses contract" (binding future-self against emotional pressure in the moment) rather than as a derivation.

**Resolution path:** decide when implementing position-sizing routing (F6). Until then, keep as documented in philosophy doc.

### G2. Is the "<10 hard gates" budget arbitrary?

Useful as discipline but the specific number is not derived. Suggested reframe in philosophy doc open questions section: "Add hard gates only when catching fact errors. Audit count quarterly. If audit reveals >10, burden of proof shifts to demoting existing gates."

**Resolution path:** decide at next quarterly audit (target: 2026-08-26). Until then, the philosophy doc's current language stands.

### G3. LITE position management at $946.90 (cost basis $70)

Engine id=21 produced REGIME_DOWNSIDE with negative future-pricing gap. Practical floors: $570 (macro), $290-$350 (pure DCF). Bull case requires CPO/OCS conversion to confirmed hyperscaler wins. Engine doesn't answer trim/hold/add — that's your call.

**Resolution path:** explicit Hume decision. Three options: (a) trim to lock in 700%+ gain, (b) hold for bull case conversion, (c) split — trim partial, hold partial. Engine's role is to surface the math, not to size for you.

### G4. AXON T+30 outcome (~2026-06-08)

First end-to-end system signal acted on at 5% (per `project_axon_first_signal`). T+30 is ~13 days away. Outcome will be the first data point for: (i) whether the system's signal recommendations are calibrated, (ii) whether position-sizing maturity schedule (F6) should activate at T+30 or wait longer.

**Resolution path:** check on 2026-06-08. If AXON has moved materially, document the outcome in `bets` table and decide F6 timing.

### G5. COHR thesis decision after id=25 NO_REGIME_SHIFT

Engine now says COHR is fully priced at $377 (rough range $240-$420, downside $80). Watch zone: $240-$290 (macro correction entry). No action recommended at current price.

**Resolution path:** monitor for macro correction; re-evaluate at $240-$290 entry zone.

---

## H. PRIORITY-ORDERED ACTION SEQUENCE

The actual order in which to execute, accounting for dependencies:

1. **Now (10 min):** B1-B2 — commit and push this session's work. Light loop.
2. **Next (2-3 days):** C1 — DCF reposition with full 7-step workflow. Most urgent fix; unblocks D1-D2.
3. **After C1 lands and is validated (week 2):** D2 — Module 1 EDGAR rewrite. Independent of D1, can run in parallel after C1.
4. **After C1 lands (week 2):** D1 — Kill rule contextual routing. Depends on C1.
5. **Investigation (parallel, ad-hoc):** E1, E2, E3 — quick data checks; ship if findings warrant.
6. **Week 3+:** D3, D4, D5 in order of conviction. §7c (D5) ready by evidence; tactical layer (D4) depends on D3 being in place.
7. **Watch:** AXON T+30 lands ~2026-06-08 → triggers F6 decision (G4).
8. **Quarterly:** filter audit re-run (target 2026-08-26). G2 decision integrated.

---

## I. PRINCIPLES IN FORCE

These shape every choice above. Listed for completeness — these aren't to-dos, they're constraints:

- `feedback_one_step_falsifiable` — bundle = contradictions; isolate = clean.
- `feedback_engine_complexity_ratchet` — 17 fixes doubled LITE error; stay deleted on magic numbers.
- `feedback_filter_philosophy` — Hard / Contextual / Informational categorization for any new filter.
- `feedback_change_workflow` — 7-step for non-trivial changes; light loop for surgical edits.
- `feedback_commit_cadence` — commit by milestone, not per-edit; CHANGELOG entries per-change.
- `feedback_audit_verification` — cross-language grep + read-the-file before any deletion.
- `feedback_data_guardrail_over_fit` — Module 1 over-fits early-stage; EDGAR rewrite is the architectural fix.
- `user_dcf_is_wrong_primary` — DCF as downside floor for regime-shift candidates.
- `user_position_sizing_discipline` — 5% first-touch sizing on first-time signals.
- `karpathy-guidelines` — surgical, simplicity-first, goal-driven, falsifiable.

---

## J. NEXT EXPLICIT DECISION FROM HUME

What do you want as the next item to execute? Options:

1. **Ship B1-B2 only** (commit + CHANGELOG), pause to think about C1 design before kicking it off.
2. **Ship B1-B2, then immediately start C1** (DCF reposition cycle 1 — apply behind flag, self-review, fix, run review squad, write cycle report). Single response could land step 1 only; full cycle takes more turns.
3. **Address one of the open questions G1-G5** before any more code change. (G3 LITE position management is the only one with real time pressure — every day at $946 is a day where the macro could trigger and floor moves to $570.)
4. **Re-examine the audit / philosophy docs in light of corrections** — the orphan misclassification was a real flaw. Worth one more pass through the documents to see if any other audit findings have similar issues.
5. **Something else** — your call.

Pick.
