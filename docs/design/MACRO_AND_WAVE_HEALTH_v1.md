# Macro Analyst + Wave Health Overlay — System Design v1

**Date:** 2026-05-19 (draft) · 2026-05-20 (v1 lock after review squad)
**Status:** v1 — review squad amendments applied; design ready for schema migration.
**Companion to:** `../../BUILD_PLAN_v2.md`, `../../STATUS_2026_05_15.md`, `../../CHANGELOG.md`
**Purpose:** Specifies two new analytical layers that fill the gap between economy-wide macro analysis and per-stock Socratic analysis.

---

## Review Squad Amendments — 2026-05-20

Critic + Outsider + Red-team passed the DRAFT through. Synthesizer verdict: **SHIP-AFTER-MUST-FIX.** Architecture sound. Four targeted fixes plus three quality-of-life fixes applied below. Four other concerns explicitly rejected with rationale.

**Must-fix (applied):**
1. **Per-stock momentum in `differentiation` jsonb.** Critic found Decision 7 ("Model C derives LITE 3x vs wave 2.3x") cannot be implemented from the original inputs — the differentiation array carried only `{ticker, resilience, reason}`, no per-stock momentum. Without trailing returns Model C fabricates the 3x. Schema now includes `trailing_12mo_return` + `trailing_18mo_return` per ticker.
2. **Hard guard against silent blank-context injection.** Red-team found `run_socratic.fill()` replaces unknown placeholders with `""` (line 79). If a prompt has `[MACRO_CONTEXT]` and `build_context()` doesn't provide it, the run silently produces a context-blind analysis with `macro_environment_id` set in Supabase. Fix documented as a precondition in Part 5 Step 5.
3. **Multi-wave ticker resolution.** CAMT lives in Wave 0 AND Wave 99 (Junction). No lookup rule made the harness non-deterministic. Fix: add `is_primary_wave boolean` to `ticker_revolutions`; harness rule documented in the wave_health schema block.
4. **Bet status enum extension for passes.** `bets.id=1` (LITE pass, position 0%) would ping every macro regime change as a zombie open bet. Fix: extend bets.status CHECK to include `'passed'`; notification cron filters to `status = 'active'`.

**Should-fix (applied):**
5. **`wave_health.beta_methodology`** text column — values like "LLM analogy from 2022 semi correction, no quantitative lookback" prevent the beta from being mistaken for measured fact at read time.
6. **Settlement fields on `wave_health`:** `settlement_window_days`, `benchmark_index`, `actual_wave_return`, `settled_at`. Nullable until settled; schema forces the question at write time.
7. **Bull case filled in.** Outsider noted the Part 4 bear case had concrete data points while the bull case was structural only. Asymmetry signaled self-confirmation. Part 4 Step 1 now lists three concrete bull data points.

**Could-fix (parked as TODOs in this doc):**
- **TODO-1:** Wave 0-2 grouping — wafer inspection (CAMT) vs transceiver optical (LITE) have structurally different betas. Note in `why_drivers` when seeding wave_health.
- **TODO-2:** Health-label composite tie-break rule — priority order momentum > crowding > P/E.
- **TODO-3:** UNIQUE partial index on `macro_environment` where `superseded_by IS NULL` to prevent concurrent-insert duplicate "current" rows.

**Rejected concerns (with rationale):**
- *"Corpus callosum jargon needs explaining"* — internal design doc for a builder who shipped Phase 3. Jargon appropriate.
- *"Part 4 is a reconstruction, not a test"* — true and standard for design docs. The actionable form is captured in Must-fix #1 and Should-fix #7.
- *"$540 range is too wide to justify anything"* — Socratic produces ranges, not points. Wide ranges on contested names under macro stress are correct outputs.
- *"Waves ARE sectors is weakly supported"* — doc already hedges with "functionally sectors." The real risk captured as TODO-1.

---

## The Problem

The Socratic model analyzes stocks in isolation. CAMT's moat, LITE's backlog, GFS's silicon photonics — all stock-specific. But the first real bet the system produced (LITE pass at $970) was driven by macro reasoning: CPI at 3.8%, new Fed chair uncertainty, broad market correction risk. The engine didn't surface any of that. The human had to override the stock-level analysis with macro judgment the system couldn't see.

There's also a missing middle layer. Macro says "SPX might drop 10-15%." But AI infrastructure stocks don't drop 10-15% — they drop 25-40% because of sector-specific dynamics (momentum unwinding, profit-taking on 20x runs, multiple compression on 50x P/E names, crowded positioning). That sector-level translation currently lives in the human's head, not in the system.

## The Solution: Two New Layers

```
Macro Analyst (economy-wide)
    → produces regime assessment with bear/bull cases
    → triggers wave health refresh when regime changes
        ↓
Wave Health Overlay (per-wave, within existing 科技革命 framework)
    → enriches each wave with dynamic sector metrics
    → translates macro into wave-specific impact
        ↓
Socratic Model (per-stock, existing)
    → receives [MACRO_CONTEXT] + [WAVE_CONTEXT] blocks
    → Models A/B/C use these to adjust targets, multiples, timing
```

Neither layer replaces anything. Macro feeds into wave health. Wave health feeds into Socratic. The existing Socratic models, discovery pipeline, and frontend all stay intact.

---

## Part 1: Macro Analyst

### What it is
A module that produces a structured assessment of the current macroeconomic environment. Not a prediction model — a framework for organizing what's happening and what could change.

### What it produces
A `macro_environment` row with:

**Headline:** One-paragraph summary of the current regime.

**Regime classification:** A label like `stagflation_risk`, `goldilocks`, `rate_shock`, `recession_fear`, `policy_uncertainty`. This is descriptive, not predictive — it names the current state.

**Bear case:** What goes wrong from here? Structured as:
- Probability estimate (the human's subjective call, not a model output)
- Specific drivers with evidence (CPI data, oil price, Fed positioning)
- Market implication ("SPX correction 10-15% over 1-3 months")

**Bull case:** Same structure. What goes right?

**State-change triggers:** Specific events that would flip the regime. These become notification rules. Examples:
- "Iran ceasefire → oil drops to $70 → CPI falls → rate cuts back on table"
- "May CPI prints above 4% → rate hike becomes consensus"
- "Warsh's first speech signals dovish pivot"

**Watch dates:** Calendar of upcoming macro events that matter:
- Next CPI release
- Next FOMC meeting (Warsh's first as chair)
- GDP print dates
- Earnings season start

**Falsification:** What would prove this regime assessment wrong? Required field, same discipline as bet falsification.

### How it runs
**Cadence:** Daily lightweight check (cron, costs ~$0.50) + full refresh on state-change trigger or manual request.

**Source:** The daily check scans news for macro-relevant events (CPI release, Fed speech, oil price spike, geopolitical development). If something material is detected, it triggers a full refresh. The full refresh uses Sonnet + web search to produce the complete regime assessment.

**Human input:** The regime assessment can be authored manually (source='manual_hume') or generated by the system (source='run_macro_v1'). The first row should be manual — the human's macro view seeded into the system. Future rows can be AI-generated with human review.

### How it connects downstream
1. The `[MACRO_CONTEXT]` block gets injected into all three Socratic model prompts. The models USE it differently:
   - **Model A** uses macro to cap multiples: "At 3.8% CPI with hike risk, my 48x becomes 35x."
   - **Model B** uses macro to validate or invalidate the regime thesis: "AI capex is structural — chokepoint immune to macro" OR "the ASML-EUV analog was in a zero-rate environment; this regime is different."
   - **Model C** uses macro as its strongest adversarial argument: "Forget company-specific risks — the macro alone implies 25-40% downside for this sector."
   - **Corpus callosum** classifies macro-vs-stock disagreements as JUDGMENT — exactly the timing question a human should resolve.

2. When the macro regime changes (new row supersedes old), the system sends notifications to all open bets linked to the superseded regime: "Macro regime changed from stagflation_risk to policy_uncertainty — review your macro-driven positions."

3. The rough target range paragraph explicitly factors macro: "Regime range $1,100-$1,500 with macro discount 15-25% → effective entry-now range $850-$1,250."

### What it does NOT do
- It does not predict market direction with a number ("SPX will drop exactly 12.7%")
- It does not produce per-stock recommendations (that's the Socratic model's job)
- It does not automatically re-run Socratic analyses when macro changes (notification only — the human decides which positions to re-analyze)
- It does not override stock-level conviction (macro is CONTEXT, not a gate)

### Schema
```sql
CREATE TABLE macro_environment (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_at            timestamptz NOT NULL DEFAULT now(),
  source            text NOT NULL,          -- 'manual_hume' | 'run_macro_v1'
  -- Headline
  state_summary     text NOT NULL,          -- one paragraph
  regime_classification text NOT NULL,      -- 'stagflation_risk' | 'goldilocks' | etc
  -- Bear/bull framework
  bear_case         jsonb NOT NULL,         -- {probability, drivers[], implication}
  bull_case         jsonb NOT NULL,
  -- Triggers and dates
  state_change_triggers jsonb DEFAULT '[]', -- [{event, direction, watch_for}]
  watch_dates       jsonb DEFAULT '[]',     -- [{date, event, importance}]
  -- Settlement
  falsification     text,
  settled_at        timestamptz,
  settled_outcome   text,                   -- 'bear_correct' | 'bull_correct' | 'mixed'
  -- Lifecycle
  superseded_by     bigint REFERENCES macro_environment(id),
  notes             text
);

-- Link macro to bets and analyses
ALTER TABLE bets ADD COLUMN macro_environment_id bigint REFERENCES macro_environment(id);
ALTER TABLE socratic_analyses ADD COLUMN macro_environment_id bigint REFERENCES macro_environment(id);
```

---

## Part 2: Wave Health Overlay

### What it is
A dynamic health layer on top of the existing wave framework in the 科技革命 tab. Each wave already defines the static structure: name, chokepoint, lifecycle stage, companies. Wave health adds the dynamic metrics: momentum, crowding, macro sensitivity, and the critical macro-to-wave translation.

### Why waves ARE sectors
The system already organizes stocks into wave groupings:
- Wave 0: Equipment (ASML, CAMT, KLIC)
- Wave 2: Optical Networking (LITE, COHR)
- Wave 7a: AI-Native Platforms (APP, PLTR)
- Wave 7b: AI Infrastructure Software (DDOG, SNOW)

These are functionally sectors. Creating a separate "sector analyst" would duplicate this structure. Instead, we upgrade each wave with sector-level health metrics.

### What it produces per wave

**Momentum score:** Average 12-month return of stocks in this wave. Flags extreme momentum (>200% avg) as a risk factor for unwinding.

**Crowding score:** How concentrated is institutional ownership in this wave? Qualitative: high / medium / low. High crowding = everyone owns it = crowded exit in a selloff.

**Multiple relative to history:** Average forward P/E of wave stocks vs their 5-year mean. "42x forward, 65% above 5yr mean" tells you how much multiple compression is possible.

**Macro beta:** How much does this wave move per 1% SPX move? Derived from historical behavior of similar stocks in prior corrections. This is the key number — it translates a general "SPX -15%" into a wave-specific "-35%."

**Macro translation:** One sentence combining macro regime + beta: "In current stagflation_risk regime, SPX -15% translates to this wave -30 to -35%." This is the sentence the Socratic model needs.

**Why drivers:** The reasoning behind the beta. Not just "2.3x beta" but WHY: "momentum unwind (avg stock +350% in 12mo) + profit-taking (investors sitting on 10-20x gains sell on any excuse) + multiple compression (50x forward compresses to 35x) + crowded exit (most-owned institutional trade)." This reasoning is what makes the analysis useful, not just the number.

**Intra-wave differentiation:** Not all stocks in a wave behave the same in a correction. Stocks with contracted backlog (LITE: sold out through 2028) are more resilient than stocks without contracted revenue (DDOG: consumption-based). This differentiation is stored as a JSON array:
```json
[
  {
    "ticker": "LITE",
    "resilience": "high",
    "reason": "contracted backlog through 2028",
    "trailing_12mo_return": 9.43,
    "trailing_18mo_return": 12.50
  },
  {
    "ticker": "COHR",
    "resilience": "medium",
    "reason": "gaining share but less contracted",
    "trailing_12mo_return": 1.45,
    "trailing_18mo_return": 2.10
  }
]
```

The `trailing_12mo_return` / `trailing_18mo_return` fields (Must-fix #1) carry per-stock momentum into the `[WAVE_CONTEXT]` block so Model C can actually derive per-stock beta deviations from the wave average. Without these, the "LITE +900% in 18mo → beta could be 3x" derivation in Part 4 is unsupported by the inputs.

### Example: Wave 2 (Optical Networking) with health overlay

**Static (existing):**
- Wave 2: 光互联 Networking
- Chokepoint: 200G EML laser chip (InP)
- Lifecycle: mid-cycle
- Companies: LITE, COHR

**Dynamic (new health overlay):**
- Momentum: extreme (+350% avg 12mo)
- Crowding: high
- Avg P/E: 42x (65% above 5yr mean)
- Macro beta: 2.3x
- Translation: "SPX -15% → this wave -30 to -35%"
- Why: momentum unwind + profit-taking on 20x runs + highest multiples compress first
- Differentiation: LITE (high resilience — $42B contracted backlog) vs COHR (medium — gaining share but less visibility)
- Regime playbook: "In stagflation, contracted-backlog names with pricing power outperform uncontracted names within the same wave."

### How it refreshes

**Weekly:** Every Sunday alongside the theme scan. Wave health runs after the quant scout provides updated momentum and multiple data.

**On macro change:** When a new `macro_environment` row supersedes the previous one, all wave_health rows are refreshed with the new macro context. The beta doesn't change (it's historical), but the macro translation and regime playbook update.

**Manual:** User can trigger a refresh for any specific wave from the 科技革命 tab.

### How it flows into Socratic

When the Socratic model runs on a stock, the harness looks up which wave(s) the stock belongs to, pulls the latest `wave_health` row, and injects it as a `[WAVE_CONTEXT]` block:

```
[WAVE_CONTEXT]
Wave: AI Infrastructure Hardware (Wave 0-2)
Health: OVERHEATED
Momentum: +350% avg 12mo (extreme)
Crowding: high (most-owned institutional trade)
Macro beta: 2.3x → current regime implies -30 to -35% if SPX corrects -15%
Intra-wave: LITE (high resilience, contracted backlog) vs COHR (medium)
Regime playbook: contracted-backlog names outperform in stagflation
```

Model A uses this to adjust its multiple assumption. Model C uses the beta to construct the macro downside scenario. The models derive per-stock implications from the wave-level data — macro and wave stay general, per-stock reasoning stays in the per-stock models.

### Schema
```sql
CREATE TABLE wave_health (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  wave_id           bigint REFERENCES waves(id) NOT NULL,
  macro_env_id      bigint REFERENCES macro_environment(id),

  -- Health metrics
  momentum_score    decimal,
  momentum_label    text,
  crowding_score    text,
  avg_forward_pe    decimal,
  pe_vs_5yr_mean    text,

  -- Macro sensitivity
  macro_beta        decimal,
  beta_methodology  text,           -- Should-fix #5: provenance of the beta
  macro_translation text,
  why_drivers       text,
  regime_playbook   text,

  -- Intra-wave (Must-fix #1: trailing_12mo_return + trailing_18mo_return required per ticker)
  differentiation   jsonb,

  -- Settlement (Should-fix #6 — nullable until settled)
  settlement_window_days  int,
  benchmark_index         text,     -- 'SPX' | 'NDX' | 'SOX'
  actual_wave_return      decimal,
  settled_at              timestamptz,

  -- Lifecycle
  run_at            timestamptz DEFAULT now(),
  superseded_by     bigint REFERENCES wave_health(id)
);

-- Must-fix #3: multi-wave ticker resolution
ALTER TABLE ticker_revolutions
  ADD COLUMN IF NOT EXISTS is_primary_wave boolean NOT NULL DEFAULT false;

-- Must-fix #4: bet status enum extension for passes
ALTER TABLE bets
  DROP CONSTRAINT IF EXISTS bets_status_check;
ALTER TABLE bets
  ADD CONSTRAINT bets_status_check
  CHECK (status IN ('active','passed','settled_win','settled_loss','cancelled'));
-- run_judgment.py sets status='passed' when position_pct=0.
-- Notification cron: WHERE status = 'active' (excludes 'passed').

ALTER TABLE socratic_analyses
  ADD COLUMN wave_health_id bigint REFERENCES wave_health(id);
```

**Harness lookup rule (Must-fix #3):** when a ticker belongs to multiple waves:
1. Use `wave_id` from the row where `ticker_revolutions.is_primary_wave = true` (if exactly one).
2. Otherwise select the most recently refreshed `wave_health` row across all matching waves.
3. Log the resolution path in the Socratic run's `prompt_versions` jsonb so the audit trail records which wave context was injected.

---

## Part 3: Frontend Changes

### Updated tab structure
**监视 | 宏观 | 科技革命 | 发现 | 对话 | 日志**

### 宏观 (Macro) tab — NEW

Top section: Current Regime Card (one-paragraph summary, classification label, key metrics, confidence).
Middle section: Bear case + Bull case side by side, with probabilities, drivers, implication.
State-change triggers: clickable list, each becomes a notification rule.
Watch dates calendar: upcoming macro events.
Right sidebar: affected waves with their macro_translation strings.

### 科技革命 tab — UPGRADED with health overlay

Each wave box in the existing sequence now shows a health indicator:
- 🔴 过热 (OVERHEATED): momentum >200%, crowding high, P/E >40% above mean
- 🟠 偏高 (ELEVATED): momentum 100-200%, moderate crowding
- 🟢 健康 (HEALTHY): momentum <100%, reasonable multiples
- 🔵 低迷 (DEPRESSED): negative momentum, P/E below mean — potential entry zone
- ⚪ 早期 (EARLY): not enough data for health assessment

Expanded view adds: why-the-beta reasoning, intra-wave differentiation table, regime playbook, per-stock cards with [苏格拉底分析 →] buttons.

---

## Part 4: How the Pieces Connect End-to-End

### Example: Full flow for a LITE analysis in current macro

**1. Macro Analyst** produced (or the human entered):
- Regime: stagflation_risk
- Bear case (probability moderate-high): SPX -10 to -15% over 1-3 months
  - Drivers: CPI 3.8% YoY accelerating, oil >$100 from Iran/Hormuz, Warsh confirmed 5/13 trapped between dovish mandate and hawkish data, market pricing 37% probability of HIKE not cut by year-end
- Bull case (probability moderate): SPX holds or grinds higher
  - Drivers: Q2 GDP tracking +3.7% (economy structurally strong), Q1 corporate profits beating consensus (earnings momentum intact), hyperscaler capex commitments $7,250B over 2024-2035 are contractual and structural (AI infrastructure largely insulated from macro tightening)

**2. Wave Health** calculated for Wave 2 (光互联):
- Momentum: extreme (+350%)
- Crowding: high
- Beta: 2.3x
- Translation: "SPX -15% → Wave 2 -30 to -35%"
- LITE resilience: high (contracted backlog)

**3. Socratic Model** runs on LITE with both contexts injected:

Model A: "At 3.8% CPI with hike risk and wave beta 2.3x, my base case multiple drops from 45x to 32x. Revised target $650-800. But contracted backlog provides revenue floor."

Model B: "AI capex is structural — $7,250B committed regardless of macro. LITE's chokepoint position is immune to broad selloffs. Regime analog: ASML held better than semis in 2022 because of EUV monopoly. LITE may outperform its wave's 2.3x beta due to contracted revenue."

Model C: "Wave health says 2.3x beta. But LITE is the HIGHEST-momentum name in this wave (+900% in 18 months). The beta could be 3x for LITE specifically. SPX -15% → LITE -40 to -45%. Entry at $580-680 is plausible. The contracted backlog protects REVENUE but not the STOCK PRICE in a momentum unwind."

Corpus callosum: "All agree macro creates downside risk. Disagreement: does LITE's contracted backlog protect the stock price (B says yes, C says no — revenue is protected but stock isn't). This is a JUDGMENT question — how much does backlog matter for price in a momentum unwind?"

Rough target range: "Regime range $900-$1,500. Macro discount 25-35% in current regime. Effective range at current entry: $585-$1,125. LITE at $970 is in the middle of the macro-adjusted range — not obviously cheap."

**4. Human judgment:** "Pass at $970. The macro says everything gets cheaper. The wave health says this wave drops 30-35% in a correction, maybe more for LITE due to extreme momentum. I'll re-enter at $650-750. Falsification: SPX avoids >5% correction in 90 days AND LITE breaks $1,200."

**5. Bet recorded** with:
- macro_environment_id = current regime
- wave_health_id = current Wave 2 health
- All three IDs (macro, wave, socratic) linked for settlement learning

**6. At T+90 settlement:**
- Did SPX correct >5%? (macro thesis check)
- Did LITE break $1,200? (stock thesis check)
- Was the wave beta prediction accurate? (2.3x predicted — what was actual?)
- Was Model B right (backlog protected price) or Model C right (backlog didn't matter)?

All of this feeds into the learning loop.

---

## Part 5: Sequence of Work

**Not building all of this now.** Per the established discipline: one phase at a time, each with a falsifiable pass criterion.

1. Schema migration (30 min): `2026-05-19_macro_and_wave_health.sql` — create both tables, add FK columns.
2. Seed first macro row (manual): insert current macro analysis as `macro_environment.id=1`.
3. Backfill existing bet: `UPDATE bets SET macro_environment_id = 1 WHERE id = 1`.
4. Seed wave_health for critical waves (manual or semi-automated): minimum Waves 0, 2, 3, 7a, 7b, cross-cutting.
5. Macro prompt + injection (future session): write `prompts/macro/macro_analyst.md`, build `run_macro.py`. Update `model_a/b/c/corpus_callosum/research_question/rough_target_range` prompts to include `[MACRO_CONTEXT]` and `[WAVE_CONTEXT]` placeholder blocks. **Must-fix #2 — placeholder-presence guard:** before any Socratic API call, `build_context()` must regex-scan every loaded prompt body for `[PLACEHOLDER]` tokens, verify each has a non-empty value in the context dict, and raise a hard error if any are missing. Do NOT silently fill with `""` as the current `fill()` does. Test post-implementation: re-run LITE Socratic with macro context injected — verify Model A/B/C produce materially different outputs from the macro-blind 2026-05-15 baseline (`socratic_analyses.id=13`).
6. Wave health automation (future session): refresh logic, momentum/crowding/multiple from quant scout, beta calculation.
7. Frontend (future session): 宏观 tab UI + wave health overlay in 科技革命 tab.
8. Notification triggers from state_change_triggers (aligns with Phase 6).

---

## Part 6: Key Design Decisions (Resolved)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | How often does macro run? | Daily cron + on-demand on state-change trigger | Catch material events without over-running |
| 2 | Does Socratic re-run when macro flips? | No — notification only; human decides which to re-analyze | Cost discipline; force-rerun is wasteful |
| 3 | Bet→macro link required or optional? | Optional FK, but auto-populated with latest at write time | Don't make the user think about it |
| 4 | Supersession model? | Each run inserts new row; previous marked superseded_by | Preserve history for learning |
| 5 | State-change triggers: manual or auto? | Hybrid — manual from macro output, auto for known dates (CPI, FOMC) | Best of both |
| 6 | Per-position implications: macro produces or A/B/C derive? | A/B/C derive from macro + wave context | Keeps macro general; per-stock reasoning in per-stock models |
| 7 | Stock beta encoded where? | In wave_health (sector-level beta) + Model C derives per-stock beta from it | Macro says "SPX -15%"; wave says "2.3x"; Model C says "LITE specifically -40% due to extreme momentum" |
| 8 | Separate sector analyst vs wave upgrade? | Wave upgrade — waves ARE sectors | No duplication; enrich existing structure |

---

## Part 7: What This Does NOT Do
- Does not predict market direction.
- Does not auto-trade.
- Does not replace Socratic.
- Does not touch discovery in v1.
- Does not change harness routing in v1.

---

## Pushbacks from Claude (pre-review, for reviewers to consider)

1. **wave_health refresh model when macro changes** — doc says "beta doesn't change but macro_translation does." Proposal: insert a new wave_health row on each macro change with macro_env_id FK; never UPDATE in place (matches supersession pattern used everywhere else).
2. **Beta calibration methodology is undefined** — input data source, correction definition, lookback window, single-stock vs peer-set average all unspecified.
3. **Health-label composite rule is ambiguous** — three inputs (momentum / crowding / P/E) but only momentum is fully numeric. What if momentum is +250% but crowding is moderate? Need a deterministic composite.
4. **CRCL-class bi-directional macro exposure isn't captured** — single-number beta can't represent "revenue beta positive vs rates, price beta negative vs SPX."
5. **Model C needs `[WAVE_CONTEXT]` too** — the Part 4 example shows Model C deriving "LITE 3x beta vs wave average 2.3x." That requires Model C to see the wave block directly.


---

## v1 changelog vs DRAFT

- 2026-05-19 — DRAFT authored.
- 2026-05-20 — review squad (Critic, Outsider, Red-team, Synthesizer) ran on DRAFT.
- 2026-05-20 — Must-fix #1-4 + Should-fix #5-7 applied. Could-fix items parked as TODOs in this doc. Rejected concerns listed with rationale.
- 2026-05-20 — renamed DRAFT → v1; design ready for schema migration.

The original DRAFT (with pre-review pushbacks at the bottom) is preserved at `MACRO_AND_WAVE_HEALTH_v1_DRAFT.md` for the review trail.
