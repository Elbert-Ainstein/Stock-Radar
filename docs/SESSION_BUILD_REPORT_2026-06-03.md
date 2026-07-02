# Stock Radar — Session Build Report

**Date:** 2026-06-03 · **Owner:** Hume
**One line:** Closed the feedback loop, put the best model behind the judgments, hardened the data inputs, and routed DCF by archetype — five shippable pieces, **73 tests green**, one trade-gate decision held for you.

---

## What shipped this session

| Area | What | Verified |
|---|---|---|
| **Feedback loop — write side** | Async **seal layer** on `prediction_log` (system_version, reasoning_fingerprint, cohort_key, model-aware cohort) | Live; sealed AMD/LITE against real data |
| **Models** | Judgment layer → **claude-opus-4-8** (A/B/C + corpus callosum, same model for fairness) + logged **same-provider fallback** that records the model actually used | opus-4-8 confirmed on key; fallback exercised against live API |
| **Feedback loop — read side** | **`run_checkpoint.py` grader** (date-pinned, idempotent, append-only) + **daily cron** (9am, quiet) | Pure helpers unit-tested; cron scheduled |
| **Data integrity (D2)** | **EDGAR cross-check** is the hard gate; trajectory heuristics demoted to advisory; graceful fallback when SEC unavailable | Pulled LITE's real 10-Q series ($425M→$534M→$665M→$808M) |
| **Valuation routing (V2)** | **Archetype-routed `dcf_role`** — transformational/regime-shift names use DCF-as-floor automatically; `analyst.py` picks it up with no flag | LITE/AMD → downside_floor; others → primary |

Plus: a one-time **AXON T+30 review** scheduled for June 9 (also evaluates the F6 position-sizing trigger).

**Direction-grading fix worth noting:** the first live LITE seal exposed that the band-midpoint direction rule reads "flat" when the band straddles spot, even though the models said "down." Fixed by sealing the models' `directional_lean` and grading against it — a real bug the unit tests couldn't have caught, surfaced by running on live data.

---

## Where it sits on the construction map

- **Stage 1 — loop closed:** ✅ done (grader + cron).
- **Stage 2 — inputs trusted:** ✅ done (D2 EDGAR).
- **Stage 3 — archetype routing:** ◐ half — V2 (dcf_role) done; **D1 (kill-rule routing) pending a decision**.
- **Stage 4 — self-improving:** ⚪ later (lights up at N≥10, ~Q4).

---

## The one decision held for you — D1

D1 rewrites the gate that sets **conviction and position size on real trades** (`risk_adj_ev_ratio < 0.90 → BROKEN`, uniform today). Unlike everything above, its behavior can only be confirmed by a live Opus thesis run — so it's not something to ship silently.

**Recommended:** a Python post-processor in `run_thesis` (thesis path only), built as the deterministic source of truth, with thresholds routed by archetype — cyclical/garp/compounder 0.90, transformational 0.60, pre-revenue disabled — and the override annotated in `kill_triggers` so the sealed record stays coherent. The Socratic-path version is a separate, deliberate follow-on. Pure logic gets unit-tested here; you validate with one live LITE run (expected: no longer `BROKEN`).

---

## What's left on the recommended track

1. **D1** — kill-rule routing (decision above).
2. **Opus cost cap** — small runaway-loop guard; more relevant now that everything reasons on opus-4-8.
3. **Socratic kill-routing** — the Stage-3 follow-on to D1, on the live judgment path.
4. **Stage 4** — `[CALIBRATION]` feedback into live analysis, when N≥10 graded outcomes exist (~Q4).

## Your action items (small)

- **Commit** — a lot is uncommitted; committing also makes `system_version` honest.
- **Run a fresh opus-4-8 socratic pass** on LITE/AMD — re-seals them with the new `directional_lean` the grader grades against, and exercises the opus-4-8 judgment layer.
- **Confirm `data.sec.gov` is reachable** from your machine (D2's EDGAR gate needs it; foreign tickers fall back to advisory automatically).
- **G3 — LITE at ~$947** remains your time-sensitive non-code call (trim/hold/split).

---

*All changes are in `scripts/` + `config/` + `supabase/`, documented per-change in `CHANGELOG.md`. Test suites: `test_checkpoint_seal`, `test_run_checkpoint`, `test_finance_data_edgar`, `test_dcf_role_routing`, `test_engine` — 73 passing.*
