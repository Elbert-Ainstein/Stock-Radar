#!/usr/bin/env python3
"""
drift_monitor.py — Data & model drift monitoring for Stock Radar.

Detects when input distributions or model outputs shift significantly,
which could indicate:
  - Market regime change (volatility spike, sector rotation)
  - Data quality issues (API changes, stale data)
  - Model degradation (features losing predictive power)

Monitors three types of drift:

1. **Feature drift** — Are scout scores, financial metrics, or price
   distributions changing vs the reference period?

2. **Prediction drift** — Are model outputs (target prices, probabilities,
   composite scores) shifting?

3. **Concept drift** — Is the relationship between inputs and outcomes
   changing? (signal → return correlation degrading)

Uses Evidently AI for statistical drift detection (KS test, PSI,
Wasserstein distance) with local HTML reports.

Usage:
    python drift_monitor.py --check           # Run all drift checks
    python drift_monitor.py --report          # Generate HTML report
    python drift_monitor.py --feature-drift   # Feature drift only
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pandas as pd
    import numpy as np
except ImportError:
    pd = np = None  # type: ignore

try:
    from evidently.report import Report
    from evidently.metric_preset import DataDriftPreset, TargetDriftPreset
    from evidently.metrics import (
        DataDriftTable,
        DatasetDriftMetric,
        ColumnDriftMetric,
    )
    HAS_EVIDENTLY = True
except ImportError:
    HAS_EVIDENTLY = False

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = DATA_DIR / "drift_reports"
REFERENCE_FILE = DATA_DIR / "drift_reference.json"


# ─── Data types ───────────────────────────────────────────────────────

@dataclass
class DriftResult:
    """Result of a drift check."""
    check_type: str          # "feature" | "prediction" | "concept"
    timestamp: str
    is_drifted: bool         # overall drift detected?
    drift_share: float       # fraction of features that drifted
    drifted_features: list[str]  # which features drifted
    details: dict[str, Any] = field(default_factory=dict)
    report_path: str | None = None

    def summary(self) -> str:
        status = "DRIFT DETECTED" if self.is_drifted else "No drift"
        lines = [
            f"[{self.check_type}] {status} — {self.drift_share:.0%} of features drifted",
        ]
        if self.drifted_features:
            lines.append(f"  Drifted: {', '.join(self.drifted_features[:10])}")
        if self.report_path:
            lines.append(f"  Report: {self.report_path}")
        return "\n".join(lines)


# ─── Data loading ─────────────────────────────────────────────────────

def _load_pipeline_history() -> pd.DataFrame | None:
    """Load historical pipeline outputs from data/ directory.

    Looks for analysis.json history (multiple snapshots) or falls back
    to the current analysis.json + any archived versions.
    """
    if not pd:
        return None

    records = []

    # Load current analysis
    analysis_file = DATA_DIR / "analysis.json"
    if analysis_file.exists():
        try:
            data = json.loads(analysis_file.read_text())
            if isinstance(data, dict):
                for ticker, info in data.items():
                    if isinstance(info, dict):
                        record = {
                            "ticker": ticker,
                            "snapshot": "current",
                            "composite_score": info.get("composite_score"),
                            "quant_score": info.get("scores", {}).get("quant"),
                            "news_score": info.get("scores", {}).get("news_sentiment"),
                            "momentum_score": info.get("scores", {}).get("momentum"),
                            "insider_score": info.get("scores", {}).get("insider"),
                            "fundamentals_score": info.get("scores", {}).get("fundamentals"),
                            "overall_signal": info.get("overall_signal"),
                        }
                        records.append(record)
        except Exception:
            pass

    # Load model outputs
    models_file = DATA_DIR / "models.json"
    if models_file.exists():
        try:
            models = json.loads(models_file.read_text())
            if isinstance(models, list):
                for m in models:
                    ticker = m.get("ticker", "")
                    record = {
                        "ticker": ticker,
                        "snapshot": "current",
                        "bull_price": m.get("scenarios", {}).get("bull", {}).get("price"),
                        "base_price": m.get("scenarios", {}).get("base", {}).get("price"),
                        "bear_price": m.get("scenarios", {}).get("bear", {}).get("price"),
                        "bull_prob": m.get("scenarios", {}).get("bull", {}).get("probability"),
                        "base_prob": m.get("scenarios", {}).get("base", {}).get("probability"),
                        "bear_prob": m.get("scenarios", {}).get("bear", {}).get("probability"),
                        "revenue_b": m.get("model_defaults", {}).get("revenue_b"),
                        "op_margin": m.get("model_defaults", {}).get("op_margin"),
                        "pe_multiple": m.get("model_defaults", {}).get("pe_multiple"),
                    }
                    # Merge with existing record for this ticker
                    for existing in records:
                        if existing.get("ticker") == ticker:
                            existing.update({k: v for k, v in record.items() if v is not None})
                            break
                    else:
                        records.append(record)
        except Exception:
            pass

    if not records:
        return None

    df = pd.DataFrame(records)
    # Convert numeric columns
    numeric_cols = [c for c in df.columns if c not in ("ticker", "snapshot", "overall_signal")]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _save_reference(df: pd.DataFrame):
    """Save current data as the reference distribution."""
    REFERENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_json(REFERENCE_FILE, orient="records", indent=2)
    print(f"  Saved reference distribution ({len(df)} records)")


def _load_reference() -> pd.DataFrame | None:
    """Load the reference distribution."""
    if not REFERENCE_FILE.exists() or not pd:
        return None
    try:
        return pd.read_json(REFERENCE_FILE)
    except Exception:
        return None


# ─── Drift detection ─────────────────────────────────────────────────

def check_feature_drift(
    current: pd.DataFrame | None = None,
    reference: pd.DataFrame | None = None,
    generate_report: bool = True,
) -> DriftResult:
    """Check for feature drift between reference and current data.

    Uses Evidently's DataDriftPreset when available, falls back to
    manual KS-test.
    """
    if current is None:
        current = _load_pipeline_history()
    if reference is None:
        reference = _load_reference()

    if current is None:
        return DriftResult(
            check_type="feature",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_drifted=False,
            drift_share=0,
            drifted_features=[],
            details={"error": "No current data available"},
        )

    if reference is None:
        # First run — save current as reference
        _save_reference(current)
        return DriftResult(
            check_type="feature",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_drifted=False,
            drift_share=0,
            drifted_features=[],
            details={"note": "First run — saved as reference"},
        )

    # Use numeric columns only
    numeric_cols = current.select_dtypes(include=[np.number]).columns.tolist()
    common_cols = [c for c in numeric_cols if c in reference.columns]

    if not common_cols:
        return DriftResult(
            check_type="feature",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_drifted=False,
            drift_share=0,
            drifted_features=[],
            details={"error": "No common numeric columns"},
        )

    report_path = None

    if HAS_EVIDENTLY and generate_report:
        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            report = Report(metrics=[DataDriftPreset()])
            report.run(
                reference_data=reference[common_cols].dropna(),
                current_data=current[common_cols].dropna(),
            )
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = str(REPORTS_DIR / f"feature_drift_{timestamp_str}.html")
            report.save_html(report_path)
        except Exception as e:
            print(f"  [drift] Evidently report failed: {e}")

    # Manual KS-test fallback (always run for structured results)
    from scipy import stats as sp_stats

    drifted = []
    details = {}
    for col in common_cols:
        ref_vals = reference[col].dropna().values
        cur_vals = current[col].dropna().values
        if len(ref_vals) < 5 or len(cur_vals) < 5:
            continue
        stat, p_value = sp_stats.ks_2samp(ref_vals, cur_vals)
        details[col] = {"ks_stat": float(stat), "p_value": float(p_value)}
        if p_value < 0.05:
            drifted.append(col)

    drift_share = len(drifted) / len(common_cols) if common_cols else 0

    return DriftResult(
        check_type="feature",
        timestamp=datetime.now(timezone.utc).isoformat(),
        is_drifted=drift_share > 0.3,  # >30% of features drifted
        drift_share=drift_share,
        drifted_features=drifted,
        details=details,
        report_path=report_path,
    )


def check_prediction_drift(
    current: pd.DataFrame | None = None,
    reference: pd.DataFrame | None = None,
) -> DriftResult:
    """Check for drift in model prediction outputs."""
    if current is None:
        current = _load_pipeline_history()
    if reference is None:
        reference = _load_reference()

    if current is None or reference is None:
        return DriftResult(
            check_type="prediction",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_drifted=False,
            drift_share=0,
            drifted_features=[],
            details={"error": "Missing data"},
        )

    # Focus on prediction columns
    pred_cols = [c for c in ["composite_score", "bull_price", "base_price", "bear_price",
                              "bull_prob", "base_prob", "bear_prob"]
                 if c in current.columns and c in reference.columns]

    from scipy import stats as sp_stats
    drifted = []
    details = {}
    for col in pred_cols:
        ref_vals = reference[col].dropna().values
        cur_vals = current[col].dropna().values
        if len(ref_vals) < 3 or len(cur_vals) < 3:
            continue

        # PSI (Population Stability Index)
        psi = _compute_psi(ref_vals, cur_vals)
        stat, p_value = sp_stats.ks_2samp(ref_vals, cur_vals)
        details[col] = {"psi": float(psi), "ks_stat": float(stat), "p_value": float(p_value)}

        if psi > 0.2 or p_value < 0.05:  # PSI > 0.2 = significant shift
            drifted.append(col)

    drift_share = len(drifted) / len(pred_cols) if pred_cols else 0

    return DriftResult(
        check_type="prediction",
        timestamp=datetime.now(timezone.utc).isoformat(),
        is_drifted=drift_share > 0.3,
        drift_share=drift_share,
        drifted_features=drifted,
        details=details,
    )


def _compute_psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Compute Population Stability Index between two distributions."""
    # Create bins from reference distribution
    breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)  # handle duplicates

    ref_counts = np.histogram(reference, bins=breakpoints)[0]
    cur_counts = np.histogram(current, bins=breakpoints)[0]

    # Normalize to proportions
    ref_pct = ref_counts / ref_counts.sum()
    cur_pct = cur_counts / cur_counts.sum()

    # Avoid log(0)
    ref_pct = np.clip(ref_pct, 1e-6, None)
    cur_pct = np.clip(cur_pct, 1e-6, None)

    psi = np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))
    return float(psi)


def check_concept_drift() -> DriftResult:
    """Check for concept drift (degrading signal-to-return correlation).

    Compares IC from recent window vs historical average.
    """
    try:
        from feedback_loop import compute_information_coefficient
        ic_result = compute_information_coefficient()
    except Exception:
        return DriftResult(
            check_type="concept",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_drifted=False,
            drift_share=0,
            drifted_features=[],
            details={"error": "IC computation not available"},
        )

    drifted = []
    neutral_ic = ic_result.get("neutral_ic", {})
    for scout, ic_val in neutral_ic.items():
        if ic_val < 0:
            drifted.append(f"{scout} (IC={ic_val:.4f})")

    return DriftResult(
        check_type="concept",
        timestamp=datetime.now(timezone.utc).isoformat(),
        is_drifted=len(drifted) > len(neutral_ic) * 0.5,
        drift_share=len(drifted) / max(len(neutral_ic), 1),
        drifted_features=drifted,
        details={"neutral_ic": neutral_ic},
    )


def run_all_checks(generate_report: bool = True) -> list[DriftResult]:
    """Run all drift checks and return results."""
    results = []

    print("Checking feature drift...")
    results.append(check_feature_drift(generate_report=generate_report))

    print("Checking prediction drift...")
    results.append(check_prediction_drift())

    print("Checking concept drift...")
    results.append(check_concept_drift())

    return results


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Drift monitoring for Stock Radar")
    parser.add_argument("--check", action="store_true", help="Run all drift checks")
    parser.add_argument("--feature-drift", action="store_true", help="Feature drift only")
    parser.add_argument("--prediction-drift", action="store_true", help="Prediction drift only")
    parser.add_argument("--save-reference", action="store_true",
                        help="Save current data as reference distribution")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    args = parser.parse_args()

    if args.save_reference:
        df = _load_pipeline_history()
        if df is not None:
            _save_reference(df)
        else:
            print("No data available to save as reference")

    elif args.check or args.report:
        results = run_all_checks(generate_report=args.report)
        print("\n── Drift Summary ──")
        for r in results:
            print(r.summary())

    elif args.feature_drift:
        r = check_feature_drift()
        print(r.summary())

    elif args.prediction_drift:
        r = check_prediction_drift()
        print(r.summary())

    else:
        parser.print_help()
