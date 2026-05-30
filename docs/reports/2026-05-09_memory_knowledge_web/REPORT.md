# Memory / knowledge / logic web — design report

**Date:** 2026-05-09
**Status:** Architecture proposal in response to Hume's question. Not implementation yet — design + tradeoffs + phased rollout.
**Context:** After today's MU misdiagnosis and the squad-review cascade, Hume asked: "do we have a memory decay system where older memories get less detail but old core structures get to be reference (not dictating, but precedent)? Different knowledges intertwining like a real human's mind?"

---

## TL;DR

We have a per-ticker memory document with item-level decay (`runs_silent` counter → Stale → Archive). It works for what it does, but it's narrow — one document per ticker, no cross-ticker structure, no sector context, no mistake memory.

Hume's vision — a memory/knowledge/logic web where ticker memory references sector patterns references cycle dynamics references operator lessons — is a real architectural step up. It's also a big surface area to get wrong, and the simpler ticker memory we have already poisoned today's MU thesis with a self-referential anchor (the prior $1,180 thesis target became the next run's gravitational center).

**My recommendation: build Phase A only (`lessons.md` — cross-cutting durable mistake memory), wait for evidence it helps, then layer.** Building the full web before fixing the anchor problem (Step 1 of the v2 plan, now superseded) compounds the risk we just spent the day untangling. The MU calendar-vs-fiscal trap is exactly the kind of thing `lessons.md` should catch on the next ticker. That alone justifies Phase A. The full web (Phases B–D) earns its complexity if and only if Phase A demonstrably reduces the rate of repeat errors.

---

## What we have today

`scripts/prompts/memory_update_v1.md` defines the per-ticker memory format. Every thesis run feeds an LLM call that updates `data/memory/{TICKER}.md`. Sections:

| Section | Decay rule | Purpose |
|---|---|---|
| Stable Facts | Updated only on structural change | Durable company description (1 paragraph) |
| Recent Thesis History | Last 5 verbatim → rolled-up `Pre-{date}` line | Specific past targets/conviction |
| Trajectory | Rewritten each run (replaces) | 2-4 sentence narrative of direction |
| Persistent Catalysts | `runs_silent >= 2` → Stale, `>= 4` → Archive | Open positive signals |
| Persistent Risks | Same | Open negative signals |
| Stale Catalysts/Risks | Move back to Persistent if seen again | Cooling-off zone |
| Resolved | Permanent | Catalysts that fired, risks that mitigated |
| Open Questions | Drop when answered | Known unknowns |
| Hume Notes | Preserved verbatim | Operator-injected context |
| Archive | One-line note | Items dropped after 4+ silent runs |

**Decay is item-level, not time-level.** A catalyst silent for 4 runs gets dropped regardless of whether those runs span 2 weeks or 2 years. Thresholds (2 stale / 4 drop) assume monthly cadence — they need re-tuning if event-triggered runs land.

**Limitations:**
1. **Per-ticker only.** No cross-ticker structure. MU's "memory chip cycle peak" knowledge can't help when reasoning about Western Digital (SNDK).
2. **No sector / pattern abstraction.** "Cyclical at peak earnings: market typically applies 5-9x multiple, not 15-20x" lives nowhere — the LLM has to re-derive it every time, with potentially different conclusions per run.
3. **No mistake memory across tickers.** Today's calendar-vs-fiscal MU trap will repeat the next time someone reasons about NVDA, ORCL, CRM, ADBE — none of these have non-calendar fiscal years recorded as a system-level lesson.
4. **No outcome feedback yet.** Module 9 (calibration) is deferred. So memory currently logs intent but doesn't yet learn from realized outcomes.
5. **Specific numbers don't progressively abstract.** $1,180 thesis target stays as exact number in History → rolls up to "avg $X" → eventually drops. It never becomes "MU 2026 peak: rerating from $400 to $X over T months" as durable pattern knowledge. The most-recent-numbers stay; the most-durable lessons evaporate.

---

## Hume's vision, made concrete

A "memory/knowledge/logic web" with five layers, linked by reference (not hard-coded relationships):

### Layer 1 — Ticker memory (already exists)

`data/memory/{TICKER}.md` per stock. Item-level decay (current system). Adds: `archetype` field in frontmatter pointing to one or more pattern files.

### Layer 2 — Sector memory (new)

`data/memory/sector/memory-chips.md`, `data/memory/sector/networking-photonics.md`, `data/memory/sector/cybersecurity.md`, etc. Per-sector durable knowledge:
- Historical cycle dynamics (memory: 5-7 year cycle, supply-demand whipsaw, peak-margin compression)
- Typical valuation regimes at peak vs trough (memory at peak: 5-9x P/E; software secular: 25-40x EV/Sales)
- Key players and their structural positions (TSMC duopoly with Samsung in advanced nodes)
- Common analyst errors specific to the sector (extrapolating peak earnings forward)
- Leading indicators for cycle turn (DRAM ASP direction, capex announcements, inventory days)

### Layer 3 — Pattern memory (new)

`data/memory/pattern/cyclical_at_peak.md`, `data/memory/pattern/secular_growth_at_premium.md`, `data/memory/pattern/post_M&A_uncertainty.md`, `data/memory/pattern/regulatory_overhang.md`. Per-archetype durable knowledge:
- Characteristics that mark this pattern
- Historical multiple ranges
- Common bull-case / bear-case framings
- Where the pattern usually breaks (what kills it)
- Calibration anchors ("at peak earnings, multiple compresses 30-50% from secular average")

### Layer 4 — Decision / outcome memory (Module 9, scoped, deferred)

`data/memory/decisions.md`. Operator's actual portfolio actions and realized outcomes:
- Ticker | entry_date | size | thesis | T+30 | T+90 | T+180 outcome | learning

This already has scaffolding (Module 8, Outcome Tracker, completed) but the calibration loop (Module 9, deferred) is what would feed outcomes back into the memory system.

### Layer 5 — Lessons (cross-cutting mistake memory) — new

`data/memory/lessons.md`. Short list of cross-cutting rules and traps:
- "Calendar vs fiscal quarter mapping: `_period_label()` uses calendar quarters. For non-calendar-FY companies (MU, NVDA, ORCL, CRM, ADBE), the calendar label ≠ fiscal label. Always verify against actual calendar period-end month."
- "Sanity-check firing on cyclicals at peak: real ramps can hit 2-3x trailing-avg. Don't assume bad data; verify against IR press release."
- "Stale single-source benchmarks are not ground truth. Cross-check at least 2 sources for any consensus claim."
- "Memory file thesis history at TEMPERATURE=0.3 acts as anchor. Quarantine contaminated runs from canonical history."

This file is durable — items only added when a real mistake reveals a generalizable pattern. Pruned only when superseded by a better lesson.

### The "web" — how it ties together

Not a graph database. Just markdown files with named references. Ticker memory frontmatter:

```yaml
ticker: MU
archetype: cyclical_at_peak
sector: memory-chips
last_run: 2026-05-10
```

Prompt construction at thesis time injects:
1. The ticker's own memory (`data/memory/MU.md`)
2. The referenced sector memory (`data/memory/sector/memory-chips.md`)
3. The referenced pattern memory (`data/memory/pattern/cyclical_at_peak.md`)
4. The global lessons file (`data/memory/lessons.md`)
5. Recent decisions where the same archetype/sector appeared (when Module 9 lands)

The LLM sees: this ticker + this sector + this pattern + the lessons we've learned. That's the "web."

### Progressive abstraction (Hume's "specific numbers fade, structural knowledge persists")

Memory entries promote up the layers as they age:

```
Recent Thesis History (last 5 runs, exact numbers)
   ↓ at run 6+
Rolled-up Pre-{date} line (directional summary — "avg $X, range $Y-$Z, conviction stable")
   ↓ at ~12 months from now
Pattern memory absorption ("MU 2026 cycle: thesis target re-rated from $400 to $1,300 over 6 months,
                            multiple expanded from 7x to 13x; outcome: [filled by Module 9]")
   ↓ if outcome clearly won/lost
Lesson promotion ("Thesis at cycle peak with 13x multiple — historically converged toward 8-10x;
                   future runs should weight peak-multiple compression at probability X")
```

Each promotion drops specifics, keeps shape. By the time MU's 2026 cycle is in pattern memory, individual targets ($1,180, $1,300) are gone; what remains is "this is what the pattern looks like."

---

## Pros

1. **Cross-ticker pattern recognition.** When the system reasons about NVDA, it pulls `cyclical_at_peak.md` and sees the MU 2026 cycle as precedent. Better calibrated.

2. **Mistake memory prevents repetition.** If `lessons.md` had said "calendar vs fiscal quarter trap" yesterday, today's misdiagnosis catches earlier.

3. **Sector context.** Memory chips in 2018 went from $11B/Q peak to $5.6B/Q trough in 18 months. That history not being in any current memory is a real gap when reasoning about MU at peak today.

4. **Closer to how operators actually reason.** Hume thinks about MU through the lens of "memory cycle pattern" + "AI capex thesis durability" + "what happened to LITE." That's already a web in his head. Encoding it makes the system reason more like he does.

5. **Outcome calibration over time.** Once Module 9 is live, decisions feed lessons feed pattern adjustments. The system improves rather than just accumulating.

## Cons

1. **Token cost.** Each prompt now adds ~3-5K tokens (sector + pattern + lessons). Real money at scale. Lessons file alone is the cheapest layer — high signal/cost ratio.

2. **Maintenance burden.** Pattern files need curation. The system can't reliably write its own pattern files yet (we just spent a day proving it can mis-write its own ticker file).

3. **More anchor surface.** Every layer is another place for a wrong claim to live and propagate. Today's failure mode (memory anchor) repeats at the sector-memory level if a sector file is wrong.

4. **Complexity bloat.** Hume's `feedback_engine_complexity_ratchet.md` memory note documents a prior cycle where "17 fixes doubled LITE error to +98%." Adding 4 more memory layers without proven need is exactly that pattern.

5. **The fragile-web problem.** A web of knowledge can become a house of cards. If the "memory chip cycle = compress at peak" pattern is right 70% of the time but wrong 30%, the system anchors on it 100% of the time at TEMPERATURE=0.3. Same anchor pathology, just structured.

6. **Self-referential loop.** Pattern memory describes patterns extracted from ticker memory. Ticker memory cites pattern memory. Risk: pattern memory says X, ticker memory inherits X, future thesis writes X, that gets folded back into pattern memory as "validated by Y runs." Confirmation bias encoded.

---

## My honest read on "is it necessary?"

**Layer 5 (lessons) — yes, build now.** The MU calendar-vs-fiscal trap WILL repeat on another non-calendar-FY ticker. Lessons.md is the smallest possible architectural change that prevents that. Token cost: ~500-1500 tokens. Risk: low (just a list of operator-curated rules).

**Layer 3 (patterns) — defer.** The need is real (cyclical-at-peak multiple compression IS what the V3 prompt got wrong on MU at 13x vs hand-paste's 9.5x), but the failure mode of getting a pattern file wrong is severe. Build only after Module 9 outcome data validates which patterns are actually predictive.

**Layer 2 (sector) — defer.** Useful but redundant if Layer 3 is well-curated. Sector knowledge that matters (cycle history, valuation regimes) is also pattern knowledge.

**Layer 4 (decisions) — already scoped (Module 9, deferred). Don't duplicate.** Module 9's calibration loop is the right place for outcome → lesson promotion.

**Progressive abstraction (specific → general) — Phase B at earliest.** This is the elegant part of Hume's vision but it requires both pattern memory AND outcome tracking to work. Build the foundations first.

**The "web" linking — emerges naturally if Layers 1, 3, 5 exist.** Don't over-engineer. Markdown files referencing each other by frontmatter field is enough. Don't build a graph DB.

---

## Phased rollout

### Phase A — `lessons.md` (build now, ~30 min)

1. Create `data/memory/lessons.md` with the existing known mistakes:
   - Calendar vs fiscal quarter trap (the MU thing)
   - Sanity-check firing on legitimate cyclical ramps
   - Stale single-source benchmarks
   - Memory file anchor at TEMPERATURE=0.3
   - "Trust the fresh paste" reverses the pipeline purpose
2. Modify `run_thesis.py` prompt construction to inject lessons.md content at a new `[LESSONS]` placeholder.
3. Add a `[LESSONS]` placeholder to `prompts/thesis_v3.md` with framing: "These are recurring traps the system has fallen into. Treat them as operator-injected reminders, not analytical content."
4. Decide: does lessons.md inject into thesis-v3 every run, or only when ticker has the matching archetype? My recommendation: every run for now (it's small and durable), narrow later if token cost becomes an issue.

**Success criterion:** in the next month, no repeat of any failure mode listed in lessons.md.

### Phase B — Pattern memory for one archetype (build after Phase A proves out, ~2 weeks)

1. Pick the archetype with the strongest evidence (probably `cyclical_at_peak` after MU). Write `data/memory/pattern/cyclical_at_peak.md`.
2. Manually tag 2-3 tickers (MU, KLAC, MRVL) with `archetype: cyclical_at_peak`.
3. Modify prompt construction to pull pattern memory when ticker memory has matching archetype.
4. Run thesis on tagged tickers; compare output to pre-Phase-B baseline.

**Success criterion:** pattern-tagged tickers show more calibrated multiple selection vs untagged. Need Module 9 outcome data to validate properly.

### Phase C — Progressive abstraction (build after Phase B, requires Module 9)

When Module 9 lands and provides T+90/T+180 outcomes:
- Promote oldest rolled-up thesis history into pattern memory absorption
- Pattern memory entries get "n=X tickers, m=Y cycles" credibility weights
- Outcome data updates pattern memory probabilities

### Phase D — Sector memory (optional, build only if Phase B-C show value)

Defer indefinitely unless Phase A-C make the case.

---

## What this does NOT solve

- The memory anchor problem at TEMPERATURE=0.3 (specific numbers in history acting as gravitational center). That's Step 1 of the v2 plan we superseded today, still unsolved.
- The forward-driver regex misfire (`forward_drivers.py:441`).
- Calibration / outcome tracking (Module 9, deferred).
- Cross-ticker shared-context contamination (e.g. when MU's contaminated data poisoned shared sector_stats — separate issue).

A knowledge web is a complement to those fixes, not a substitute. If we build Phase A but don't fix the memory anchor, the lessons.md content gets sucked into the same anchoring pathology.

---

## Open questions for Hume

1. **Should `lessons.md` be Hume-curated only, or can the system propose additions?** Recommendation: Hume-curated only initially. Adding "system writes its own lessons" is the same self-referential loop pathology.

2. **Where does archetype assignment come from?** Today we have a `cyclical_normalized_earnings` engine mode but it's engine-side, not memory-side. Does the operator manually tag, does the LLM tag during thesis run, or does an upstream classifier (existing `archetype_system` per memory note `project_archetype_system`) feed in?

3. **Do we keep contaminated runs in memory but quarantine, or strip them entirely?** v2 plan said quarantine; today's MU lesson is "the diagnosis was wrong, the runs weren't contaminated." So quarantine logic might apply less often than I claimed. Need a clearer test for "contaminated run."

4. **Token budget per thesis prompt.** Currently ~12K (prompt) + ~5K (memory) = ~17K. Adding sector + pattern + lessons could push to 25-30K. At Sonnet pricing, that's $0.25-0.40 per run. At ~15 watchlist tickers × 1 run/week = $4-6/week extra. Acceptable, but worth noting.

5. **How does this interact with `## Hume Notes`?** That section is preserved verbatim. Should lessons.md content be allowed to reference Hume Notes? My read: no — Hume Notes is operator-private context, lessons.md is system-public guidance. Keep separate.

6. **The bigger meta-question:** before building more memory layers, do we trust the existing one? Today's MU saga shows the per-ticker memory writes contaminated content even with squad-review oversight. Should Phase A wait until we've validated the memory write-back hygiene from the (superseded) v2 Step 1?

---

## Visualizations

- `mindmap.svg` — five-layer architecture overview with web links
- `decay_flow.svg` — progressive abstraction: specific numbers → directional summary → pattern absorption → lesson promotion
- `complexity_vs_value.svg` — phased rollout cost/benefit estimate

