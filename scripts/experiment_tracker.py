#!/usr/bin/env python3
"""
experiment_tracker.py — Lightweight experiment tracking for Stock Radar.

Logs pipeline runs, model generation parameters, and performance metrics
to a local JSON-lines file + optional MLflow integration.

Each "experiment" is a pipeline run or model generation with:
  - Run ID, timestamp, git commit hash
  - Parameters (model config, WACC, growth rates, etc.)
  - Metrics (IC, hit rate, Sharpe, model accuracy)
  - Artifacts (model JSON paths, analysis outputs)

Storage: data/experiments/ directory (one .jsonl file per experiment name)

When MLflow is available (MLFLOW_TRACKING_URI set), also logs there.

Usage:
    from experiment_tracker import Tracker

    with Tracker("pipeline_run") as t:
        t.log_params({"n_stocks": 50, "wacc_method": "bottom_up_beta"})
        # ... run pipeline ...
        t.log_metrics({"mean_ic": 0.08, "hit_rate": 65.2})
        t.log_artifact("data/analysis.json")
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Local storage
EXPERIMENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "experiments"

# MLflow integration (optional)
try:
    import mlflow
    HAS_MLFLOW = True
except ImportError:
    mlflow = None  # type: ignore
    HAS_MLFLOW = False


@dataclass
class Run:
    """A single tracked experiment run."""
    run_id: str
    experiment: str
    start_time: str
    end_time: str | None = None
    status: str = "running"     # running | completed | failed
    git_commit: str | None = None
    git_branch: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    duration_s: float | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "experiment": self.experiment,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "git_commit": self.git_commit,
            "git_branch": self.git_branch,
            "params": self.params,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "tags": self.tags,
            "duration_s": self.duration_s,
        }


def _get_git_info() -> tuple[str | None, str | None]:
    """Get current git commit hash and branch name."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).resolve().parent.parent),
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).resolve().parent.parent),
        ).decode().strip()
        return commit, branch
    except Exception:
        return None, None


class Tracker:
    """Experiment tracker with local JSON-lines + optional MLflow backend.

    Usage as context manager:
        with Tracker("pipeline_run") as t:
            t.log_params({"key": "value"})
            t.log_metrics({"accuracy": 0.95})
            t.log_artifact("path/to/file.json")

    Usage without context manager:
        t = Tracker("pipeline_run")
        t.start()
        t.log_params(...)
        t.end()
    """

    def __init__(self, experiment: str, tags: dict[str, str] | None = None):
        self.experiment = experiment
        self._run = Run(
            run_id=str(uuid.uuid4())[:8],
            experiment=experiment,
            start_time=datetime.now(timezone.utc).isoformat(),
            tags=tags or {},
        )
        self._start_wall = 0.0
        self._log_file = EXPERIMENTS_DIR / f"{experiment}.jsonl"
        self._mlflow_run = None

    def start(self) -> "Tracker":
        """Start the run (called automatically by __enter__)."""
        self._start_wall = time.time()
        commit, branch = _get_git_info()
        self._run.git_commit = commit
        self._run.git_branch = branch

        # Ensure log directory exists
        EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

        # Start MLflow run if available
        if HAS_MLFLOW and os.environ.get("MLFLOW_TRACKING_URI"):
            try:
                mlflow.set_experiment(self.experiment)
                self._mlflow_run = mlflow.start_run(
                    run_name=self._run.run_id,
                    tags=self._run.tags,
                )
                if commit:
                    mlflow.set_tag("git_commit", commit)
                if branch:
                    mlflow.set_tag("git_branch", branch)
            except Exception as e:
                print(f"  [tracker] MLflow start failed: {e}")

        return self

    def log_params(self, params: dict[str, Any]):
        """Log parameters (model config, hyperparameters, etc.)."""
        self._run.params.update(params)
        if self._mlflow_run and HAS_MLFLOW:
            try:
                # MLflow params must be strings
                mlflow.log_params({
                    k: str(v)[:250] for k, v in params.items()
                })
            except Exception:
                pass

    def log_metrics(self, metrics: dict[str, float], step: int | None = None):
        """Log metrics (IC, hit rate, Sharpe, etc.)."""
        self._run.metrics.update(metrics)
        if self._mlflow_run and HAS_MLFLOW:
            try:
                mlflow.log_metrics(
                    {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))},
                    step=step,
                )
            except Exception:
                pass

    def log_artifact(self, path: str):
        """Log an artifact file path."""
        self._run.artifacts.append(path)
        if self._mlflow_run and HAS_MLFLOW:
            try:
                if os.path.exists(path):
                    mlflow.log_artifact(path)
            except Exception:
                pass

    def set_tag(self, key: str, value: str):
        """Set a tag on the run."""
        self._run.tags[key] = value
        if self._mlflow_run and HAS_MLFLOW:
            try:
                mlflow.set_tag(key, value)
            except Exception:
                pass

    def end(self, status: str = "completed"):
        """End the run and flush to storage."""
        self._run.end_time = datetime.now(timezone.utc).isoformat()
        self._run.status = status
        self._run.duration_s = round(time.time() - self._start_wall, 2)

        # Write to local JSONL
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(self._run.to_dict()) + "\n")
        except Exception as e:
            print(f"  [tracker] Failed to write local log: {e}")

        # End MLflow run
        if self._mlflow_run and HAS_MLFLOW:
            try:
                mlflow.end_run(status="FINISHED" if status == "completed" else "FAILED")
            except Exception:
                pass

    def __enter__(self) -> "Tracker":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "failed" if exc_type else "completed"
        self.end(status=status)
        return False  # don't suppress exceptions


# ─── Query / comparison utilities ─────────────────────────────────────

def list_runs(experiment: str, last_n: int = 20) -> list[dict]:
    """List recent runs for an experiment."""
    log_file = EXPERIMENTS_DIR / f"{experiment}.jsonl"
    if not log_file.exists():
        return []

    runs = []
    for line in log_file.read_text().strip().split("\n"):
        if line.strip():
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return runs[-last_n:]


def compare_runs(experiment: str, metric: str, last_n: int = 10) -> list[dict]:
    """Compare a specific metric across recent runs.

    Returns sorted list of {run_id, timestamp, metric_value, params}.
    """
    runs = list_runs(experiment, last_n)
    results = []
    for r in runs:
        val = r.get("metrics", {}).get(metric)
        if val is not None:
            results.append({
                "run_id": r["run_id"],
                "timestamp": r["start_time"],
                "value": val,
                "params": r.get("params", {}),
                "status": r.get("status", "unknown"),
            })
    results.sort(key=lambda x: x["value"], reverse=True)
    return results


def best_run(experiment: str, metric: str, minimize: bool = False) -> dict | None:
    """Find the run with the best value for a metric."""
    runs = list_runs(experiment, last_n=100)
    best = None
    best_val = float("inf") if minimize else float("-inf")
    for r in runs:
        val = r.get("metrics", {}).get(metric)
        if val is None:
            continue
        if (minimize and val < best_val) or (not minimize and val > best_val):
            best = r
            best_val = val
    return best


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Experiment tracker")
    parser.add_argument("--list", metavar="EXPERIMENT", help="List runs for experiment")
    parser.add_argument("--compare", nargs=2, metavar=("EXPERIMENT", "METRIC"),
                        help="Compare metric across runs")
    parser.add_argument("--best", nargs=2, metavar=("EXPERIMENT", "METRIC"),
                        help="Find best run for metric")
    parser.add_argument("--last", type=int, default=10, help="Number of recent runs")
    parser.add_argument("--demo", action="store_true", help="Run a demo experiment")
    args = parser.parse_args()

    if args.demo:
        print("Running demo experiment...")
        with Tracker("demo", tags={"type": "test"}) as t:
            t.log_params({"model": "claude-opus", "n_stocks": 50, "wacc": "bottom_up"})
            time.sleep(0.1)  # simulate work
            t.log_metrics({"mean_ic": 0.082, "hit_rate": 64.5, "sharpe": 1.23})
        print(f"Run logged: {t._run.run_id}")
        print(f"Log file: {t._log_file}")

    elif args.list:
        runs = list_runs(args.list, args.last)
        for r in runs:
            print(f"  {r['run_id']} | {r['start_time'][:19]} | {r['status']}")
            if r.get("metrics"):
                metrics_str = ", ".join(f"{k}={v:.4f}" for k, v in r["metrics"].items())
                print(f"    metrics: {metrics_str}")

    elif args.compare:
        results = compare_runs(args.compare[0], args.compare[1], args.last)
        print(f"Comparing '{args.compare[1]}' across runs:")
        for r in results:
            print(f"  {r['run_id']} | {r['value']:.4f} | {r['status']}")

    elif args.best:
        r = best_run(args.best[0], args.best[1])
        if r:
            print(f"Best run for '{args.best[1]}':")
            print(f"  Run: {r['run_id']} ({r['start_time'][:19]})")
            print(f"  Value: {r['metrics'].get(args.best[1])}")
            print(f"  Params: {json.dumps(r.get('params', {}), indent=2)}")
        else:
            print("No runs found")
    else:
        parser.print_help()
