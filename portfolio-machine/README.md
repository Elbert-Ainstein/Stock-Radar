# The Portfolio Machine — Phase 1

A git repo that does automatically what was done by hand: pull settled
prices, adjudicate tripwires on settled prints only, keep an append-only log,
and open consult tickets when rules fire. **It never trades** — see
`CONSTITUTION.md` (read it first; every design rule in here is a law bought
with a logged mistake). `BUILD_SPEC.md` carries the full five-phase plan.

## Quick start

```bash
pip install pyyaml requests yfinance pytest

# run the constitution + regression suite (offline, <1s)
python -m pytest tests/ -q

# the premarket pass (fetch settled closes, cross-check, adjudicate, value)
python passes/premarket.py            # network
python passes/premarket.py --offline  # adjudicate what's already on file
```

## What exists (Phase 1)

| Piece | File(s) | What it enforces (CONSTITUTION ref) |
|---|---|---|
| Append-only log | `engine/log.py`, `data/log.jsonl` | real clocks, corrections forward (§VI) |
| Price store + fetcher | `engine/fetch.py`, `data/prices/*.csv` | settled vs snapshot, provenance, two-source flag-never-average (§VI) |
| Wire evaluator | `engine/rules.py` | consults-never-orders (§V Rule 5), settled-only adjudication, conflict rows blocked |
| Wire state | `data/wire_state.yaml` | machine-written status/history; `config/tripwires.yaml` stays human-only (comments survive fires) |
| Euphoria protocol | `engine/rules.py euphoria_checks` | §V: position ≥2× cost → automatic consult (trim / signed defense) |
| Anti-parabola screen | `engine/rules.py anti_parabola` | §V sizing law + v1.2.1 Momentum-RISK redline (informational) |
| Consult tickets | `engine/consults.py`, `consults/OPEN_*.md` | doors, no recommendation, signature (§VII) |
| Book valuation + floor | `engine/valuation.py` | declared gaps never guesses; HK FX; the $40K floor reported, never counted (§V) |
| Grades v1.2.1 in code | `engine/grades.py`, `config/grades.yaml` | §III: 7 factors, letters, moat-answer-required-for-A, Track-Z rubric refusal; kills the off-by-one class (keyed by name) |
| Market calendar | `engine/market_calendar.py`, `config/market_calendar.yaml` | True/False/UNKNOWN — never assume (§VI) |
| Premarket pass | `passes/premarket.py` | orchestration, loud degradation |
| The book as data | `config/*.yaml` | editable without code; clauses carry the doors |
| Regressions | `tests/` | INTC/MU settlement flips · same-day/exchange-local settlement (law 2 choke points) · conflicted-latest blocks · off-by-one grades · euphoria/floor · no-trade law · provenance · calendar honesty · config integrity · premarket smoke |

## Before trusting it: replace the seeds

Every `SEED_REPLACE` marker in `config/` is a placeholder awaiting the live
workbook's numbers (holdings shares/costs, real wire levels, catalyst
details, grade scores, methodology dates). The schemas are final; the values
are not. Wire adjudication logic is real regardless of seed values.

## Scheduling (Phase 2 formalizes; works today)

```cron
# premarket — 9:00 ET weekdays. Use CRON_TZ so DST can never shift the pass
# (9:00 ET is 14:00 UTC in winter, 13:00 UTC in summer — a fixed UTC line is
# wrong for half the year).
CRON_TZ=America/New_York
0 9 * * 1-5  cd /path/to/portfolio-machine && python passes/premarket.py >> data/cron.log 2>&1
```

The pass exits 0 on clean runs (including legitimate all-exchanges-closed
skips) and 1 on degraded runs (every fetch failed, or an armed wire was
unadjudicable because its fetch failed) — point your cron monitor at the
exit code.

## Extraction to a standalone repo

This directory is fully self-contained (no imports from the host repo).
To split it out with history: `git subtree split -P portfolio-machine -b pm-main`
then push that branch to a new repo — or just copy the folder and `git init`.

## Roadmap

Phase 2: close pass + brief/workbook rendering + schedule ·
Phase 3: grade sheet renderer + migrations ·
Phase 4: Claude headless passes (news classification, Radar, consult drafts,
grade proposals) with CONSTITUTION.md as the spine ·
Phase 5: catalyst-armed event passes + push notifications.
