# CORRIGENDUM — 2026-05-09 (issued same day as REPORT.md v2)

**Status:** REPORT.md v1, v2, and Step 0 are all built on a wrong premise. This file supersedes the action plan in REPORT.md. The architectural findings about memory anchoring and regex misfire still stand; the specific MU "data bug" that motivated the entire cleanup did not exist.

---

## What happened

After three rounds of squad review (each catching a different problem), the fact-checker on Step 0 noticed that the "$90.92 NTM EPS" I'd flagged as contaminated was within $0.01 of current sell-side consensus. That triggered a deeper check — fetching MU's actual Q2 FY26 press release dated March 18, 2026.

**Q2 FY26 actuals per Micron IR:**
> Revenue of **$23.86 billion** versus $13.64 billion for the prior quarter and $8.05 billion for the same period last year.

**$23.86B is real Q2 FY26 revenue.** It was never contaminated.

The "syndication bug" I diagnosed all morning was actually a calendar-vs-fiscal quarter labeling confusion in my own head. `_period_label()` in `scripts/finance_data.py:192-206` derives quarter labels from the period-end month (Feb→1Q, May→2Q, Aug→3Q, Nov→4Q) — calendar quarters, not fiscal. MU's fiscal Q2 FY26 ends in February → labeled `"1Q26"` by the provider. I then pulled MU's 10-Q for *fiscal* Q1 FY26 (period ending Nov 2025, $13.64B), interpreted that as "the real Q1 number," and built an override patching `"1Q26"` → $13.64B.

**That patch took real $23.86B Q2 FY26 actuals and corrupted them to look like the previous quarter.** Multi-statement extension corrupted op income, EBITDA, FCF the same way. The "bug" I was fixing all day was a bug I introduced.

Verification of the trailing-4Q math the sanity check reported: prior 4 calendar quarters before "1Q26" are `4Q25` (= MU fiscal Q1 FY26) $13.64B, `3Q25` (= fiscal Q4 FY25) $11.32B, `2Q25` (= fiscal Q3 FY25) $9.30B, `1Q25` (= fiscal Q2 FY25) $8.05B. Average = $10.58B. Matches what the sanity check reported. Providers' data was correct end to end.

---

## What was actually fixed (good architecture, kept)

- Provider chain abstraction in `finance_data.py` — fallback ordering, env-driven selection — useful and retained
- Manual quarterly override system (`config/manual_quarterly_overrides.json`) — useful for genuine future syndication bugs, retained but emptied
- `_apply_manual_overrides()` patches both `q_inc` and `q_cf` (multi-statement) — useful and retained
- Light-theme color fixes in TableHelpers + ThesisTab — retained (those were independent and correct)
- NavBar Run All Theses progress polling — retained (independent and correct)

## What was rolled back (the wrong-direction fixes)

- `config/manual_quarterly_overrides.json` MU 1Q26 entry — DELETED. Was actively corrupting real data.
- `config/data_provider_overrides.json` MU entry — DELETED. yfinance was returning correct data; the route-around-yfinance had no basis.
- READMEs in both config files updated with an INCIDENT note explaining the misdiagnosis.

## What remains true (no rollback needed)

- **Memory anchoring is a real architectural risk.** When the LLM at TEMPERATURE=0.3 reads its own prior thesis target as `[MEMORY_SECTION]` context, it drifts toward the prior conclusion. This is structural, independent of MU.
- **Forward-driver regex (`forward_drivers.py:441`) bound is too loose for cyclicals.** Pattern `(?:operating|op)\s+margin` with `< 100` upper bound can match gross-margin language as op-margin guidance for memory companies. Real bug, real fix needed (tighten to contiguous `\boperating\s+margin\b` + sector-aware cap). Affects engine UI side, not LLM thesis prompt directly.
- **The memory file `data/memory/MU.md` thesis history rows ($1,180 on 2026-05-09 and $1,300 on 2026-05-10) ran on REAL data.** Whether they're "right" is a thesis-disagreement question (multiple selection 13x vs 9.5x), not a contamination question. The hand-paste's $855 used 9.5x × $90; the pipeline used 13x × ~$92. Both built on real consensus EPS.

## Lingering operational issue (real, separate)

The model API for MU will now return "Cannot build model" because the sanity check correctly fires on the legitimate 2.7x trailing-avg ramp. The check is calibrated for "this is a data error" but real cyclical ramps at cycle peak (memory, semis, autos) can produce 2-3x sequential jumps that look identical to provider errors.

Three options:

(a) **Add archetype-aware thresholds:** `cyclical` / `cyclical-tech` archetypes allow 3x trailing / 4x YoY before firing. Requires touching `_validate_quarterly_revenue()` to accept an archetype hint.

(b) **Run MU thesis with `override_suspect_recent=True`** for now. This is the documented escape hatch and is the *correct* operator action when the data passes 10-Q verification — which it does for MU's $23.86B Q2 FY26.

(c) **Tag MU specifically** with a "known cyclical at peak" flag that bypasses the sanity check while keeping it on for everything else.

My recommendation: **(b) for the immediate render, (a) as a follow-up task.** Don't add ticker-specific bypasses (c); they encode operator memory in a way that's hard to audit.

## Action plan (replaces REPORT.md v2 8-step plan)

1. **DONE — already executed:** roll back the wrong MU entries in both override configs.
2. **DONE — already executed:** update memory note `project_mu_data_bug.md` with the real story.
3. **DONE — written here:** corrigendum so the next reader of the report knows v1/v2 are superseded.
4. **DEFERRED until needed:** archetype-aware sanity check thresholds. File a task; not urgent unless other cyclicals trip the same firing.
5. **DEFERRED:** forward-driver regex tightening + sector-aware cap. Real bug, real fix, but engine-UI side; doesn't block the autonomous-trader path.
6. **OPEN QUESTION:** is the V3.3 thesis prompt's tendency to use 13x NTM-EPS multiple actually wrong for MU at cycle peak? The hand-paste's 9.5x was anchored on "rerating mostly done." This is a calibration question that can only be resolved by tracking realized outcome (Module 9, deferred).

## Meta-lessons

- Squad review is necessary but not sufficient. Three reviewers can converge on a wrong consensus when they all share a wrong premise (here: "$23.86B is contaminated").
- Empirical verification — fetching the actual press release — caught what three rounds of architectural reasoning missed.
- Calendar-vs-fiscal quarter mapping is a recurring trap for non-calendar-FY companies (MU, NVDA, ORCL, CRM, ADBE). Period labels in our system are calendar; analyst commentary uses fiscal. They don't line up.
- "Stop and verify against the actual data" beats "run another round of architectural review" once the architectural picture has stabilized.
- I owe Hume an explicit retraction of the diagnostic. The MU "syndication bug" never existed; the architectural risks I identified along the way are real but they didn't cause the symptom that triggered the investigation.

---

*REPORT.md v1 and v2 are kept for the audit trail. Their architectural findings (3 contamination paths, squad pushbacks, action plan) are correct in shape but the proximate trigger that motivated the investigation was a misdiagnosis.*
