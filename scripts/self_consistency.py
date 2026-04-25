#!/usr/bin/env python3
"""
self_consistency.py — LLM self-consistency sampling for Stock Radar.

Instead of trusting a single LLM response, sample N times and report
mean ± stderr for numeric fields. High stderr flags unreliable outputs.

The audit recommended N≥5 samples. Default is controlled by the
SELF_CONSISTENCY_N env var (default: 1 for backward compat / cost savings).
Set to 5+ for production-quality scoring.

Usage:
    from self_consistency import sample_model_generation, ConsistencyResult

    result = sample_model_generation(
        generate_fn=lambda: generate_model_with_claude(...),
        n=5,
    )
    print(result.mean_prices)    # {"bull": 180.2, "base": 130.5, "bear": 75.1}
    print(result.stderr_prices)  # {"bull": 12.3, "base": 5.1, "bear": 3.2}
    print(result.high_variance)  # ["bull"] if stderr/mean > threshold
"""
from __future__ import annotations

import math
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable


# Default number of samples — override with SELF_CONSISTENCY_N env var
DEFAULT_N = int(os.environ.get("SELF_CONSISTENCY_N", "1"))

# If stderr/mean exceeds this ratio, the field is flagged as high-variance
HIGH_VARIANCE_THRESHOLD = 0.15  # 15% coefficient of variation


@dataclass
class ConsistencyResult:
    """Aggregated result from N LLM samples."""
    n_samples: int
    n_success: int
    # Scenario prices: mean ± stderr
    mean_prices: dict[str, float] = field(default_factory=dict)
    stderr_prices: dict[str, float] = field(default_factory=dict)
    # Scenario probabilities: mean ± stderr
    mean_probs: dict[str, float] = field(default_factory=dict)
    stderr_probs: dict[str, float] = field(default_factory=dict)
    # Model defaults: mean ± stderr for key numeric fields
    mean_defaults: dict[str, float] = field(default_factory=dict)
    stderr_defaults: dict[str, float] = field(default_factory=dict)
    # Archetype consensus
    archetype_votes: dict[str, int] = field(default_factory=dict)
    archetype_consensus: str | None = None
    # Fields with high variance (stderr/mean > threshold)
    high_variance: list[str] = field(default_factory=list)
    # The "best" result (lowest total stderr, used as the final output)
    best_result: dict | None = None
    # All individual results (for debugging)
    all_results: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary of consistency analysis."""
        lines = [f"Self-consistency: {self.n_success}/{self.n_samples} successful samples"]
        if self.mean_prices:
            for scenario in ["bull", "base", "bear"]:
                p = self.mean_prices.get(scenario, 0)
                se = self.stderr_prices.get(scenario, 0)
                lines.append(f"  {scenario}: ${p:,.0f} ± ${se:,.0f}")
        if self.archetype_votes:
            votes = ", ".join(f"{k}={v}" for k, v in sorted(
                self.archetype_votes.items(), key=lambda x: -x[1]))
            lines.append(f"  archetype votes: {votes}")
        if self.high_variance:
            lines.append(f"  ⚠ high variance: {', '.join(self.high_variance)}")
        return "\n".join(lines)


def _extract_numeric(results: list[dict], path: list[str]) -> list[float]:
    """Extract numeric values from a list of dicts by nested key path."""
    values = []
    for r in results:
        v = r
        for key in path:
            if isinstance(v, dict):
                v = v.get(key)
            else:
                v = None
                break
        if v is not None and isinstance(v, (int, float)) and not math.isnan(v):
            values.append(float(v))
    return values


def _mean_stderr(values: list[float]) -> tuple[float, float]:
    """Compute mean and standard error of a list of values."""
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], 0.0
    m = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return m, se


def _inverse_variance_select(
    results: list[dict],
    mean_prices: dict[str, float],
    mean_defaults: dict[str, float],
) -> dict:
    """Select the best result using inverse-variance weighting.

    For each sample, compute its squared deviation from the consensus mean
    across all trackable numeric fields (prices + defaults). The sample with
    the lowest total squared deviation gets selected — this is equivalent to
    inverse-variance weighting where each sample's "precision" is
    1 / (sum of squared deviations).

    This replaces the old "closest to mean base price" heuristic, which only
    looked at a single field and could pick an outlier on other dimensions.
    """
    if len(results) == 1:
        return results[0]

    def _total_sq_dev(r: dict) -> float:
        dev = 0.0
        # Scenario prices
        for scenario in ["bull", "base", "bear"]:
            actual = (r.get("scenarios", {}).get(scenario, {}).get("price", 0)) or 0
            expected = mean_prices.get(scenario, 0) or 1
            if expected > 0:
                dev += ((actual - expected) / expected) ** 2
        # Model defaults (normalized by mean)
        for key, mean_val in mean_defaults.items():
            actual = (r.get("model_defaults", {}) or {}).get(key)
            if actual is not None and mean_val and mean_val != 0:
                dev += ((float(actual) - mean_val) / mean_val) ** 2
        return dev

    return min(results, key=_total_sq_dev)


def sample_model_generation(
    generate_fn: Callable[[], dict | None],
    n: int | None = None,
    parallel: int = 3,
) -> ConsistencyResult:
    """Run generate_fn N times and aggregate numeric results.

    Parameters
    ----------
    generate_fn : callable
        A zero-argument function that returns a model config dict (or None on failure).
    n : int, optional
        Number of samples. Defaults to SELF_CONSISTENCY_N env var (or 1).
    parallel : int
        Max concurrent API calls (default 3 to avoid rate limits).

    Returns
    -------
    ConsistencyResult
        Aggregated statistics across all successful samples.
    """
    if n is None:
        n = DEFAULT_N

    # Short-circuit: if N=1, just call once (backward compat)
    if n <= 1:
        result = generate_fn()
        return ConsistencyResult(
            n_samples=1,
            n_success=1 if result else 0,
            best_result=result,
            all_results=[result] if result else [],
        )

    # Sample N times in parallel
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(parallel, n)) as pool:
        futures = [pool.submit(generate_fn) for _ in range(n)]
        for f in as_completed(futures):
            try:
                r = f.result()
                if r is not None:
                    results.append(r)
            except Exception:
                pass  # count as failed sample

    if not results:
        return ConsistencyResult(n_samples=n, n_success=0)

    # ── Aggregate scenario prices and probabilities ──
    mean_prices, stderr_prices = {}, {}
    mean_probs, stderr_probs = {}, {}
    high_variance = []

    for scenario in ["bull", "base", "bear"]:
        prices = _extract_numeric(results, ["scenarios", scenario, "price"])
        probs = _extract_numeric(results, ["scenarios", scenario, "probability"])

        mp, sp = _mean_stderr(prices)
        mean_prices[scenario] = round(mp, 2)
        stderr_prices[scenario] = round(sp, 2)

        mpr, spr = _mean_stderr(probs)
        mean_probs[scenario] = round(mpr, 4)
        stderr_probs[scenario] = round(spr, 4)

        # Flag high variance
        if mp > 0 and sp / mp > HIGH_VARIANCE_THRESHOLD:
            high_variance.append(f"{scenario}_price")
        if mpr > 0 and spr / mpr > HIGH_VARIANCE_THRESHOLD:
            high_variance.append(f"{scenario}_prob")

    # ── Aggregate model defaults ──
    mean_defaults, stderr_defaults = {}, {}
    for key in ["revenue_b", "op_margin", "tax_rate", "shares_m", "pe_multiple", "ps_multiple"]:
        values = _extract_numeric(results, ["model_defaults", key])
        m, se = _mean_stderr(values)
        if values:
            mean_defaults[key] = round(m, 4)
            stderr_defaults[key] = round(se, 4)
            if m > 0 and se / m > HIGH_VARIANCE_THRESHOLD:
                high_variance.append(f"default_{key}")

    # ── Archetype consensus ──
    archetype_votes: dict[str, int] = {}
    for r in results:
        arch = (r.get("archetype") or {}).get("primary", "unknown")
        archetype_votes[arch] = archetype_votes.get(arch, 0) + 1
    consensus = max(archetype_votes, key=archetype_votes.get) if archetype_votes else None

    # ── Inverse-variance weighted best result ──
    # Instead of just picking closest-to-mean, weight each sample by 1/σ²
    # where σ is the sample's deviation from the group mean across all numeric
    # fields. Samples that are consistently near the mean get higher weight;
    # outlier samples get downweighted. This produces a more robust consensus.
    best = _inverse_variance_select(results, mean_prices, mean_defaults)

    return ConsistencyResult(
        n_samples=n,
        n_success=len(results),
        mean_prices=mean_prices,
        stderr_prices=stderr_prices,
        mean_probs=mean_probs,
        stderr_probs=stderr_probs,
        mean_defaults=mean_defaults,
        stderr_defaults=stderr_defaults,
        archetype_votes=archetype_votes,
        archetype_consensus=consensus,
        high_variance=high_variance,
        best_result=best,
        all_results=results,
    )
