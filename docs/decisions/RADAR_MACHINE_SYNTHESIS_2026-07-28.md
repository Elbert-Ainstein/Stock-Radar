# Stock Radar × The Portfolio Machine — fit, conflicts, and the synthesis

**Status:** §3 supremacy clause + build items 1, 2, 5 **IMPLEMENTED** 2026-07-28
(operator: "your choice"). Item 3 (calibration-weighted evidence) deferred until
~30 seals ripen — it would print noise today. Item 4 (shared ledger clause) folded
into the clause text in both constitutions. See the changelog entry of this date.
**Date:** 2026-07-28
**Context:** Two constitutions now live in this repo. Stock Radar (CLAUDE.md
design rules + lessons L1–L8) is a research engine hunting 10× opportunities.
The Portfolio Machine (`portfolio-machine/CONSTITUTION.md`, SAMLA) is a
restraint engine guarding a real book. The owner asked: how do they fit,
where do they conflict, and what would something better look like?

---

## 1. Shared DNA — these are the same epistemology twice

Both systems were written in scar tissue: every rule is a logged mistake.

| Principle | Stock Radar form | Portfolio Machine form |
|---|---|---|
| Gates are code, not prose | `trade_gate.py` clamp table, `kill_gate.py` | wire evaluator, euphoria protocol |
| Two-source verification, flag never average | EDGAR XBRL revenue cross-check | two-source price cross-check, CONFLICT rows |
| Append-only memory, corrections forward | `prediction_log` seals | `data/log.jsonl`, correction rows |
| Declared unknowns beat guesses | `EarningsFetchError` hard-fail, never estimate historicals | calendar True/False/**None**, valuation gaps |
| Clock honesty | L1 horizon clocks, dated-signpost kills (L5) | law 2 settled-only, law 5 real clocks |
| Human at the money moment | money-path merges need owner approval | consult doors + signature |

The convergence is not stylistic — **both systems independently arrived at
"dated, code-adjudicated triggers ratified by a human"** (Radar's L5 kill
signposts; the Machine's tripwires). They are the same object approached from
opposite ends: Radar derives the trigger level from a thesis; the Machine
adjudicates the trigger against settled reality.

## 2. Real conflicts — four, all resolvable, none cosmetic

**C1 — The advise line.** SAMLA Law 1 / §VII: "this system analyzes; it never
advises buy/sell/hold." But Radar's thesis path emits conviction scores and
clamp-table position sizes — that *is* advice under SAMLA's definition. Left
unreconciled, the merged system violates its own constitution daily.

**C2 — Settlement regime vs spot gates.** Radar's trade gate recomputes
`risk_adj_ev_ratio` from **spot** — by SAMLA's law 2 a provisional number.
The Machine adjudicates only next-day settled prints (the INTC/MU scars). If
the two share one price layer, one regime must be declared supreme at the
point of action.

**C3 — Two graders, one word.** Radar grades *predictions* (sealed bands at
T+30/60/90). The Machine grades *companies* (7-factor v1.2.1) and *operator
process* (signed defenses). Naive merge collides the vocabularies and poisons
both calibration loops.

**C4 — Two sizing authorities.** Radar's clamp table maps conviction →
position size. Charter §V has its own sizing law (staged thirds, starter size
under anti-parabola, sleeve caps, the floor). Two authorities over the same
book is how inconsistent books happen.

There is also a temperament difference that is NOT a conflict: Radar is an
opinion factory (offense — find the 10×), SAMLA is a restraint machine
(defense — protect the floor, slow the hand). A portfolio needs both organs;
it needs them **separated**, not blended.

## 3. The resolution principle

**Cortex and brainstem.** Stock Radar is the research cortex: it generates
theses, targets, conviction, kill signposts — upstream, fast, spot-driven,
opinionated. The Portfolio Machine is the brainstem: settled facts, wires,
consults — the ONLY layer that touches the book. The interface between them
is exactly one object: **the consult ticket**.

Supremacy clause (one sentence, both constitutions):

> At the point of research, Radar's design rules govern; at the point of
> action, the Machine's laws govern — and everything Radar produces enters
> the action layer only as *evidence inside a consult*, never as a verdict.

This dissolves all four conflicts: Radar's conviction/sizing output becomes a
proposed ceiling attached to a ticket the operator signs (C1, C4); spot-based
gates keep running for research prioritization but never adjudicate the book
(C2); the two graders keep their own names — *prediction grades* (Radar) and
*seat grades* (Machine) — connected by one new loop below (C3).

## 4. What "better" concretely is — proposed build items (Phase 2+)

1. **The bridge (`radar_bridge`).** A read-only exporter: a Supabase `theses`
   row (verdict of record) renders into consult-evidence markdown with full
   provenance (thesis date, targets, conviction, risk_adj_ev_ratio, gate
   artifacts). The Machine attaches it to any consult on that ticker. Radar
   never gains write access to the book; the Machine never calls a model.
2. **Signposts become wires.** Radar's L5 dated kill signposts and
   target-engine levels export as *proposed* tripwires (a PENDING block the
   operator ratifies into `config/tripwires.yaml` by hand — the file stays
   human-only). The Machine adjudicates them on settled prints. L5 and the
   tripwire system merge into one object.
3. **Calibration-weighted evidence — the genuinely new organ.** The grader's
   T+30/60/90 outcomes produce a per-archetype reliability score; every
   consult that cites a thesis prints it ("theses like this one have graded
   X% inside band at T+90"). Radar's calibration loop finally has a consumer,
   and the operator signs with known instrument error. Neither system alone
   could build this.
4. **One ledger discipline, two ledgers.** Seals stay in Supabase; the book's
   log stays in `data/log.jsonl`. Shared rule (already true of both): append
   only, corrections forward, no exceptions. No merge needed — just the
   shared clause cited in both docs.
5. **Type A conviction ↔ the DEFEND door.** Radar's Type A (strategic
   conviction never clamped by price) maps to the euphoria protocol's signed
   defense: holding a doubled Type A name requires exactly that signature.
   The Machine supplies the enforcement Radar's L3 lacked; Radar supplies the
   thesis text the defense cites.

**Not proposed:** merging the codebases. The Machine stays extractable and
dependency-thin (its safety case rests on being auditable in an afternoon);
the bridge is one file on the Radar side writing plain markdown/YAML.

## 5. What shipped (2026-07-28)

- **Supremacy clause** — CLAUDE.md rule 7 and the CONSTITUTION machine appendix.
- **Item 1 (bridge) + item 2 (signposts→wires)** — `scripts/radar_bridge.py`,
  one-way: evidence into `portfolio-machine/data/evidence/<TICKER>.md`,
  signposts + the gate-algebra actionability level into
  `data/radar_proposed_wires.yaml` as PROPOSALS (engine never reads it;
  ratification is a hand edit of the human-only `config/tripwires.yaml`).
- **Item 5 (Type A ↔ DEFEND)** — `engine/evidence.py` stamps evidence age
  (STALE past 45d) and attaches it BENEATH the settled facts on every consult;
  live structural conviction obliges the DEFEND door to cite the thesis.
- **Enforced limits:** `position_size_pct` never crosses the line (pinned by
  test); no target ⇒ no invented price wire (design rule 1); malformed or
  undated research degrades loudly to STALE, never to silence.

**Still open:** item 3, calibration-weighted evidence — print each thesis's
archetype hit-rate on the consult so the operator signs knowing the
instrument's error. Blocked on ripened seals, not on design.
