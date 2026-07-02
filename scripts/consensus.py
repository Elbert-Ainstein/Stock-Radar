"""
consensus.py — self-consistency mode-of-N aggregator for the Socratic round-1
verdict (PRD P1).

opus-4-8 rejects the `temperature` param, so a single sealed round-1 verdict is
partly sampling noise — measured: Model B (regime) reproduced only 60% of the
time across 5 runs (see stability_check.py). That noise propagates into the
sealed verdict, the grader's `directional_lean`, and calibration.

This module dampens that variance: sample each model N times and seal the
CONSENSUS. Categorical fields (verdict, confidence) collapse to the MODE; numeric
targets to the MEDIAN across the samples that share the modal verdict; the modal
frequency is recorded as `consistency` (1.0 = perfectly stable, 1/N = max spread)
so the grader can later down-weight low-consistency seals.

Env-gated, default-off: `SELF_CONSISTENCY_N` (int, default 1). N=1 is a no-op (no
aggregation; byte-identical to pre-P1 behavior, zero cost change). When N>1, ONLY
the round-1 model calls multiply (N× per model); corpus callosum / research /
target run once on the aggregated A/B/C.

Pure + unit-tested in test_consensus.py. Reuses `modal_consistency` from
stability_check.py (the shared modal-frequency primitive) rather than
re-deriving it.
"""

from __future__ import annotations

import os
from typing import Optional

# The shared modal-frequency primitive already lives in the stability harness;
# reuse it so "consistency" means exactly the same thing in both places.
from stability_check import modal_consistency


def self_consistency_n() -> int:
    """Read `SELF_CONSISTENCY_N` from the env. Default 1 (no-op).

    Clamps to >= 1 so a bad value (0, negative, non-int garbage) degrades to
    today's single-sample behavior rather than aborting a production run.
    """
    raw = os.environ.get("SELF_CONSISTENCY_N", "1")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 1
    return n if n >= 1 else 1


def _median(values) -> Optional[float]:
    """Median of the numeric values, ignoring None / booleans / non-numeric.

    Returns None if nothing is numeric. Even count -> mean of the two middle
    values. Numeric strings (e.g. "131") are coerced; garbage is skipped.
    """
    nums = []
    for v in values:
        if v is None or isinstance(v, bool):
            continue
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return None
    nums.sort()
    mid = len(nums) // 2
    if len(nums) % 2:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2


def aggregate_samples(samples: list[dict]) -> dict:
    """Collapse N parsed round-1 outputs for ONE model into a consensus dict.

    - verdict, confidence  -> MODE (via modal_consistency)
    - target_low, target_high -> MEDIAN across the samples sharing the modal
      verdict (so the sealed band matches the sealed verdict, not an averaged
      contradiction between an OVERVALUED and an UNDERVALUED sample)
    - consistency -> modal frequency [0..1] of the verdict; for a model that
      emits no verdict (the adversarial model C) it falls back to the modal
      frequency of confidence
    - n_samples -> number of parsed samples aggregated

    Prose / structured fields (reasoning_bullets, valuation_summary, ...) are
    taken verbatim from the first sample that shares the modal verdict, so the
    sealed reasoning stays coherent with the sealed verdict.

    Empty input -> {}. A single sample is returned essentially unchanged, with
    consistency=1.0 / n_samples=1 added (so N=1 carries a trivially-stable
    fingerprint without altering any verdict/target).
    """
    samples = [s for s in samples if isinstance(s, dict)]
    if not samples:
        return {}
    if len(samples) == 1:
        out = dict(samples[0])
        out.setdefault("consistency", 1.0)
        out.setdefault("n_samples", 1)
        return out

    modal_verdict, verdict_cons = modal_consistency([s.get("verdict") for s in samples])
    modal_conf, conf_cons = modal_consistency([s.get("confidence") for s in samples])
    # Directional voters (A/B) -> verdict stability is the meaningful signal.
    # Model C emits no verdict, so fall back to confidence stability.
    consistency = verdict_cons if modal_verdict is not None else conf_cons

    # Median targets from the samples that AGREE with the modal verdict, so the
    # band is internally consistent with the sealed direction.
    cohort = [s for s in samples if s.get("verdict") == modal_verdict] or samples
    tl = _median([s.get("target_low") for s in cohort])
    th = _median([s.get("target_high") for s in cohort])

    out = dict(cohort[0])  # representative prose, coherent with the modal verdict
    if modal_verdict is not None:
        out["verdict"] = modal_verdict
    if modal_conf is not None:
        out["confidence"] = modal_conf
    if tl is not None:
        out["target_low"] = tl
    if th is not None:
        out["target_high"] = th
    out["consistency"] = consistency
    out["n_samples"] = len(samples)
    return out
