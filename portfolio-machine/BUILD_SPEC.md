# BUILD_SPEC — The Portfolio Machine

(Text distillation of the operator's Jul 28 spec. CONSTITUTION.md carries the
laws; this file carries the shape and the build order.)

## What it is

A git repo that does automatically what was done by hand: pull prices on a
schedule, adjudicate tripwires on settled prints, keep the log and workbook
current, generate the briefs, run the Saturday Radar, and open consults when
rules fire. Claude Code builds it; a scheduler runs it; Claude (headless)
thinks inside it on schedule. The repo is the book's memory — conversation
stays the place where decisions get made.

## Components

- **data/** — append-only price history per ticker (CSV): date, close,
  settled_flag, source, fetched_at. Daily settled closes via a market-data
  lib (delayed is fine — adjudication is on settled, not live); FX for HK.
  One fetcher, two modes: snapshot (informational) and settled (authoritative).
- **config/** — the book as data, editable without code: holdings.yaml,
  tripwires.yaml, clauses.yaml, catalysts.yaml, grades.yaml, plus
  CONSTITUTION.md read by every Claude pass first.
- **engine/** — pure-Python rules evaluation: wire checks against settled rows,
  book valuation, anti-parabola screen (+100%/6mo), sleeve/factor cap monitors,
  composite grade math IN CODE (kills the off-by-one class of spreadsheet bug).
  Fires write `consults/OPEN_*.md` tickets with the doors pre-drafted.
- **passes/** — scheduled entry points: premarket (9:00 ET — backfill settled,
  adjudicate for real, snapshot premarket, generate brief), close (4:45 ET —
  provisional verdicts, marked as such), event (armed from catalysts.yaml),
  radar (Sat 9:00 — research pass). Cron or GitHub Actions.
- **claude passes** — headless `claude -p "run the premarket pass"` in the
  repo: news classification (PRICE vs THESIS event, primary-source check),
  brief narrative, Radar research, grade-change PROPOSALS (never silent).
- **out/** — rendered artifacts regenerated every pass: xlsx workbook (a
  render target, not the source of truth), HTML briefs, grade sheet, consult
  packs. Delivery: local folder + optional push for fires/contradictions.

## Build order

1. **Skeleton + settled truth** — repo, configs seeded, fetcher with settled
   backfill, wire evaluator, append-only log. ← THIS PHASE (built)
2. **Passes + rendering** — premarket/close scripts, brief generator, workbook
   regeneration, schedule.
3. **Grades as data** — grades.yaml + composite math + migration tracking +
   sheet renderer (methodology v1.1 far-dated de-weight, v1.2 commoditization
   screen, tracks C/Z live in config).
4. **Claude in the loop** — headless passes; CONSTITUTION.md is the spine.
5. **Events + notification** — calendar-armed passes; push channel.

## Phase-1 status & seams

- Built self-contained (no imports from the host repo); extract to a
  standalone repo with `git subtree split` or a plain copy whenever wanted.
- **Config seeds are SCHEMA-TRUE PLACEHOLDERS** where the live workbook data
  was not available at build time (holdings shares/costs, full wire list,
  full grade scores). Every placeholder is marked `SEED_REPLACE`. Replace
  them from the workbook; nothing else changes.
- Tests encode the INTC/MU settlement-flip scenario and the off-by-one
  grade-formula bug as permanent regressions, plus the no-trade law.
