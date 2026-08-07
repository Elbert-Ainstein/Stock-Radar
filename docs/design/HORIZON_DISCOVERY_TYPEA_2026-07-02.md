# Lessons of 2026-07-02 — horizon clocks, dual-mode gating, Type A as bits

**Source:** operator session lessons (Hume, 2026-07-02), formalized as implementable
specs. **Status:** spec locked by owner; build sequenced below. This is the
"human-hypothesis intake" the TEN_X doc asked for, applied to the system itself.

**Caveat carried from the source:** the external session's "engine results" ran on
assumed parameters, not this engine. Where a real run disagrees with that session's
numbers, the mismatch is diagnostic gold, not error — log it, don't paper over it.

---

## L1 — The gate has a clock, and it was invisible ★ SHIPPED 2026-07-02

The Step-12 clamp table silently encodes the 12–18-month timescale of the trade the
system was born from (the memory-cycle capture). Applied to a 3-year thesis
(robotics), it clamps everything to no-buy — not because the market is expensive
but because the ruler is wrong for the object.

**Spec (implemented in `trade_gate.py` + `run_thesis.py`):**
- `thesis_horizon_years` is a per-name field (`config/thesis_horizons.json`;
  absent = 1.25y, the table's native clock — zero behavior change until set).
- The clamp table is **annualized-return-equivalent**: band thresholds scale as
  `t^(h/1.25)`, so a 1.3× ratio on an 18-month clock and a 2.5× on a 3-year clock
  are judged by the same annualized bar (both HIGH-adjacent), while 1.3× at 3
  years honestly reads MEDIUM (~9%/yr).
- Every verdict **states which clock it was judged on**: the horizon is logged,
  included in the enforcement record, and persisted on the theses row
  (`supabase/2026-07-02_theses_horizon.sql`).

**Acceptance:** identical ratio, different horizons → different clamps, both
derivable by hand from the annualized bands; default-horizon behavior byte-identical
to the pre-change gate (regression-tested).

**Same-day review corrections (both confirmed adversarially):**
1. **Conservative-only scaling until the prompt knows the clock.** thesis_v3.md
   Step 6 still pins `risk_adj_target` to a 12–18-month date, so two-sided
   scaling would loosen the BROKEN edge against a mismatched number. Scaled
   thresholds are floored at their native values — a configured clock can only
   TIGHTEN the gate. Two-sided honesty (and threading the clock into Model D's
   bracket) unlocks when the prompt carries `[THESIS_HORIZON]` (L3 batch).
2. **The operator's clock always wins.** The gate initially read a
   `thesis_horizon_years` field from the model's own closing JSON ahead of the
   config — i.e., the model could choose the ruler it was judged by. Fixed:
   config/default is always passed explicitly; a conflicting model-emitted
   horizon is ignored and flagged (`horizon_source` / `model_horizon_ignored`
   in the enforcement record).

## L2 — Discovery and allocation are different machines (dual-mode gating)

The moat framework finds structural elites the market has priced. Only the
inverted hunt — preconditions of regime change — surfaces 10× candidates. SNDK at
$38.50 fails the six-moat screen AND the gate. So:

- **Allocation mode** (current run_thesis path): the gate clamps hard. Unchanged.
- **Discovery mode**: the gate is *diagnostic* — output is a new stance
  **STALK** with a stored `trigger_price`, never a sized position. STALK is a NEW
  field (`stance` + `trigger_price` columns), NOT a new value of `conviction`
  (which the kill gate, UI pills, and outcomes seeding all pattern-match on).
- **The six signature screens are the revival spec for dormant discovery gen-2**
  (its intake was a SyntaxError for 6.5 weeks; the ROADMAP's "revive or retire"
  question is hereby answered: revive, with this intake):
  S1 anomalies that survive verification (the MU/EDGAR lesson as code — a
  sanity-check firing that XBRL then CONFIRMS is a *signal*, not an error),
  S2 sold-out-before-noticed (lead times/allocation language before coverage),
  S3 smart money before analysts (13F adds with zero/negative coverage — gen-2's
  13F differ already exists), S4 TAM redefinition, S5 new primitives,
  S6 hated inflections (improving prints + persistent short interest/downgrades).
- Each screen emits evidence + a trigger price; STALK names get **alerts**
  (watchlist → pending orders, not sentiment).

**Acceptance:** a backtest-style dry run shows SNDK-at-$38.50-shape passing S1+S3
into STALK with a trigger, while the allocation gate still (correctly) refuses to
size it that day.

## L3 — Type A should be bits, not vibes

`strategic_conviction` today is an LLM's mood. Persist it as auditable columns:

- `input_or_substitute` (single bit: is the product an INPUT to customers' output,
  or a SUBSTITUTE for customer effort? Separates Atlassian from Duolingo/Chegg
  better than any multiple; a substitute-side failure gets a **structural cap no
  price can lift** — Chegg was cheap the entire way to zero).
- `five_q_bits` (jsonb: the five-question gate, each pass/fail + one-line evidence).
- `moat_category` (one of the six) — with the L2 caveat that moats are an
  ALLOCATION lens, not a discovery lens.
- `bond_depth` for human-aggregation names; `wave_layer` + `supplier_count`
  scarcity tags for hardware.
- Prompt change: thesis Step-12's strategic_conviction must be DERIVED from the
  bits ("state each bit, then the conviction it implies") — prose becoming
  enforcement, same as the trade gate.

**Acceptance:** two consecutive runs on the same name agree on ≥4/5 bits (bits are
stabler than moods); a substitute-flagged name can never emit strategic HIGH.

## L4 — Silent constraints are bugs (the engine must never have an invisible opinion)

- **Accessibility is a field, not a drop reason:** `venue`, `access_route`
  (Connect/ADR/local), `disclosure_quality` on discovery candidates; excluded
  names appear WITH their exclusion reason, count surfaced per run.
- **Every run emits its parameter block:** horizon, clamp table (post-scaling),
  archetype, dcf_role, N, macro-block age, allowlist size — one JSON blob logged
  and persisted with the run. (The `[trade_gate]`/`[kill_gate]` log lines are the
  start; formalize as `run_parameters` jsonb.)
- **Zero-result auto-diagnosis:** any run/sweep producing zero actionable names
  auto-generates a gate-artifact analysis — for each name, WHICH gate killed it
  and what parameter would have to change — answering "is everything expensive,
  or is my ruler wrong?" instead of a silent shrug. (The 6/6-BROKEN incident is
  exactly the case this would have caught in one run.)

## L5 — Kill conditions are the actual product

- Kill conditions must be **dated, external signposts** (coverage decisions,
  1,000-unit deployments, capacity financings, renewal prints) — never vibes
  ("competition intensifies" is not falsifiable).
- **Archetype-templated:** consumer → bookings decay; SaaS → NRR + seat
  commentary; cyclicals → capex discipline; wave-two/regulated → regulatory
  events. Templates live beside `ARCHETYPE_KILL_GUIDANCE` in
  `kill_condition_eval.py` and feed the thesis prompt's kill_triggers step.
- STALK names carry `trigger_price` **alerts** (the refresh-prices path already
  polls quotes — compare against stored triggers, surface breaches).

## L6 — The cascade has a clock too: anointment closes windows

Scarcity migrates (memory → packaging → optics → memory-efficiency → power →
robotics). A giant's strategic check (NVIDIA into optics; AMD/MEXT) is
simultaneously S3 confirmation AND the bell that the pre-crowd window at that
node closed. Spec:
- The cascade is a **persisted first-class object** — and ~70% of it already
  exists: `analyst_panel.py`'s 7-node [CHAIN] with cycle clocks IS the cascade
  tracker. Extend it with (a) per-node `scarcity_state`, (b) **anointment
  events** (dated, sourced), (c) a rule: an anointment at node N advances the
  hunt pointer one derivative deeper (N+1), logged, not rediscovered per run.

## L7 — Human hypothesis intake

Formal template (markdown in `data/hypotheses/`, one file per hypothesis):
`claim / mechanism / signatures expected (mapped to S1–S6) / kill conditions
(dated signposts) / horizon / status`. run_thesis and discovery both read the
folder; the corpus callosum's job is falsification, not origination. The two
best theses of 2026-07-02 (verified human aggregation; two-wave robotics) came
from the human — the system should have a front door for that.

## L8 — Ordering: none of this outruns the ledger

The through-line: an engine only learns if its feedback loop tells the truth.
**Status correction as of this writing:** the poisoning described in the source
lessons was fixed and merged the same morning (PR #1: zero-row snapshot disabled,
grader source-filtered, quarantine applied, off-by-one fixed, migration run).
The ledger is clean; grades ripening this week land on filtered seals. The
ordering STANDS as a principle — L1–L7 are all things you calibrate over time,
so nothing here may ever bypass the seal/grade discipline (STALK triggers and
discovery hits get sealed too, or they never earn trust).

---

## Build sequence (slots into docs/ROADMAP.md)

| # | Item | Size | Touches money path? | Status |
|---|------|------|--------------------|--------|
| 1 | L1 horizon-aware gate + per-name horizons + clock-stated verdicts | S | trade_gate/run_thesis (additive, default-identical) | **SHIPPED** (this PR) |
| 2 | L4 parameter-block emission + zero-result auto-diagnosis | S–M | logging only | next |
| 3 | L5 archetype kill templates + dated-signpost linting of kill_triggers | M | kill_condition_eval + prompt | next |
| 4 | L3 Type A bits (columns + prompt derivation + migration) | M–L | thesis prompt (cohort reset — batch with 3) | after owner reviews bit definitions |
| 5 | L2 discovery gen-2 revival: S1–S6 screens, STALK stance + trigger_price + alerts | L | new path (discovery mode never sizes) | design first slice: S1+S3 |
| 6 | L6 cascade object: analyst_panel + scarcity_state + anointment events | M | context layer only | after 5's first slice |
| 7 | L7 hypothesis intake folder + template + injection | S | prompt context | anytime |

Prompt-touching items (3, 4) batch together to spend the cohort reset once.
