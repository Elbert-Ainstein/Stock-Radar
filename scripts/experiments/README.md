# Experiments

Quarantine for research-only / spike code per BUILD_PLAN_v2 cleanup.

| File | Quarantined | Why | Resurrect when |
|------|-------------|-----|----------------|
| `run_thesis_v4_spike.py`        | 2026-05-15 | V3.4.3 kill rule (CHANGELOG 2026-05-10) extracted V4's win at 1/4 the cost. V4 stays available for re-running if Phase 0 Test 3 shows V3.4.3 < 7/8 within 5% of V4 sizing. | Phase 0 Test 3 falls below the 7/8 bar. |
| `run_architecture_experiment.py` | 2026-05-15 | One-shot from the Apr 2026 audit. Not on any active pipeline. | Need to re-run the architecture comparison. |

Do NOT import from this folder in production code paths.
