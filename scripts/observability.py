#!/usr/bin/env python3
"""
Observability module for Stock Radar pipeline.

Collects metrics for scout runs, model generation, and data source calls.
Works entirely in-memory — no external dependencies. If Supabase is available,
the summarize() output can be stored in the pipeline_runs.scout_details column.
"""
import time
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ScoutMetrics:
    """Metrics for a single scout execution."""
    scout_name: str
    ticker: Optional[str] = None
    start_time: float = 0.0       # monotonic timestamp
    end_time: float = 0.0         # monotonic timestamp
    duration_s: float = 0.0
    success: bool = False
    error_msg: Optional[str] = None
    signal_count: int = 0
    confidence: Optional[float] = None


@dataclass
class ModelGenMetrics:
    """Metrics for a single model generation call."""
    ticker: str
    duration_s: float = 0.0
    success: bool = False
    tokens_used: int = 0
    repair_attempts: int = 0
    repair_method: Optional[str] = None
    archetype: Optional[str] = None


@dataclass
class DataSourceMetrics:
    """Metrics for a single data source call."""
    ticker: str
    provider: str
    success: bool = False
    latency_s: float = 0.0
    error: Optional[str] = None


class PipelineMetrics:
    """Thread-safe collector for all pipeline observability data."""

    def __init__(self):
        self._lock = threading.Lock()
        self._scouts: list[ScoutMetrics] = []
        self._model_gens: list[ModelGenMetrics] = []
        self._data_sources: list[DataSourceMetrics] = []
        self._pipeline_start: float = time.monotonic()
        self._pipeline_start_wall: str = datetime.now(timezone.utc).isoformat()

    # ── Recording methods ────────────────────────────────────────────

    def record_scout_run(self, metrics: ScoutMetrics) -> None:
        """Record a completed scout run. Safe to call from any thread."""
        with self._lock:
            self._scouts.append(metrics)
        _log_scout(metrics)

    def record_model_gen(
        self,
        ticker: str,
        duration_s: float,
        success: bool,
        tokens_used: int = 0,
        repair_attempts: int = 0,
        repair_method: Optional[str] = None,
        archetype: Optional[str] = None,
    ) -> None:
        """Record a model generation result."""
        m = ModelGenMetrics(
            ticker=ticker,
            duration_s=duration_s,
            success=success,
            tokens_used=tokens_used,
            repair_attempts=repair_attempts,
            repair_method=repair_method,
            archetype=archetype,
        )
        with self._lock:
            self._model_gens.append(m)

    def record_data_source(
        self,
        ticker: str,
        provider: str,
        success: bool,
        latency_s: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        """Record a data source fetch result."""
        ds = DataSourceMetrics(
            ticker=ticker,
            provider=provider,
            success=success,
            latency_s=latency_s,
            error=error,
        )
        with self._lock:
            self._data_sources.append(ds)

    # ── Summary ──────────────────────────────────────────────────────

    def summarize(self) -> dict:
        """Return a dict suitable for the scout_details jsonb column.

        Structure:
        {
            "collected_at": "...",
            "pipeline_duration_s": ...,
            "scouts": { ... per-scout summary ... },
            "model_generation": { ... },
            "data_sources": { ... },
            "totals": { ... }
        }
        """
        with self._lock:
            scouts = list(self._scouts)
            model_gens = list(self._model_gens)
            data_sources = list(self._data_sources)

        elapsed = time.monotonic() - self._pipeline_start

        # ── Scouts ──
        scout_summary = {}
        for s in scouts:
            scout_summary[s.scout_name] = {
                "duration_s": round(s.duration_s, 2),
                "success": s.success,
                "error_msg": s.error_msg,
                "signal_count": s.signal_count,
                "confidence": s.confidence,
            }

        # ── Model generation ──
        model_summary = {}
        total_tokens = 0
        total_repairs = 0
        for m in model_gens:
            model_summary[m.ticker] = {
                "duration_s": round(m.duration_s, 2),
                "success": m.success,
                "tokens_used": m.tokens_used,
                "repair_attempts": m.repair_attempts,
                "repair_method": m.repair_method,
                "archetype": m.archetype,
            }
            total_tokens += m.tokens_used
            total_repairs += m.repair_attempts

        # ── Data sources ──
        ds_summary: dict[str, dict] = {}
        for ds in data_sources:
            key = f"{ds.ticker}:{ds.provider}"
            ds_summary[key] = {
                "ticker": ds.ticker,
                "provider": ds.provider,
                "success": ds.success,
                "latency_s": round(ds.latency_s, 2),
                "error": ds.error,
            }

        # ── Totals ──
        scout_ok = sum(1 for s in scouts if s.success)
        scout_fail = len(scouts) - scout_ok
        model_ok = sum(1 for m in model_gens if m.success)
        model_fail = len(model_gens) - model_ok
        ds_ok = sum(1 for d in data_sources if d.success)
        ds_fail = len(data_sources) - ds_ok

        return {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_start": self._pipeline_start_wall,
            "pipeline_duration_s": round(elapsed, 2),
            "scouts": scout_summary,
            "model_generation": {
                "results": model_summary,
                "total_tokens": total_tokens,
                "total_repair_attempts": total_repairs,
            },
            "data_sources": ds_summary,
            "totals": {
                "scouts_ok": scout_ok,
                "scouts_failed": scout_fail,
                "models_ok": model_ok,
                "models_failed": model_fail,
                "data_sources_ok": ds_ok,
                "data_sources_failed": ds_fail,
            },
        }

    def print_summary(self) -> None:
        """Print a formatted summary table to stdout."""
        with self._lock:
            scouts = list(self._scouts)
            model_gens = list(self._model_gens)
            data_sources = list(self._data_sources)

        elapsed = time.monotonic() - self._pipeline_start
        width = 70

        print(f"\n{'='*width}")
        print("  PIPELINE OBSERVABILITY SUMMARY")
        print(f"{'='*width}")

        # ── Scout table ──
        if scouts:
            print(f"\n  {'Scout':<20} {'Status':<8} {'Duration':>9} {'Signals':>8} {'Error'}")
            print(f"  {'-'*20} {'-'*8} {'-'*9} {'-'*8} {'-'*20}")
            for s in sorted(scouts, key=lambda x: x.scout_name):
                status = "OK" if s.success else "FAIL"
                dur = f"{s.duration_s:.1f}s"
                sig = str(s.signal_count) if s.signal_count else "-"
                err = (s.error_msg[:30] + "...") if s.error_msg and len(s.error_msg) > 30 else (s.error_msg or "")
                print(f"  {s.scout_name:<20} {status:<8} {dur:>9} {sig:>8} {err}")

            scout_ok = sum(1 for s in scouts if s.success)
            total_dur = sum(s.duration_s for s in scouts)
            print(f"\n  Scouts: {scout_ok}/{len(scouts)} succeeded | Total duration: {total_dur:.1f}s")

        # ── Model generation table ──
        if model_gens:
            print(f"\n  {'Ticker':<10} {'Status':<8} {'Duration':>9} {'Tokens':>8} {'Repairs':>8} {'Archetype'}")
            print(f"  {'-'*10} {'-'*8} {'-'*9} {'-'*8} {'-'*8} {'-'*15}")
            for m in sorted(model_gens, key=lambda x: x.ticker):
                status = "OK" if m.success else "FAIL"
                dur = f"{m.duration_s:.1f}s"
                tok = str(m.tokens_used) if m.tokens_used else "-"
                rep = str(m.repair_attempts) if m.repair_attempts else "-"
                arch = m.archetype or "-"
                print(f"  {m.ticker:<10} {status:<8} {dur:>9} {tok:>8} {rep:>8} {arch}")

            model_ok = sum(1 for m in model_gens if m.success)
            total_tokens = sum(m.tokens_used for m in model_gens)
            total_repairs = sum(m.repair_attempts for m in model_gens)
            print(f"\n  Models: {model_ok}/{len(model_gens)} succeeded | Tokens: {total_tokens} | Repairs: {total_repairs}")

        # ── Data source table ──
        if data_sources:
            print(f"\n  {'Ticker':<10} {'Provider':<15} {'Status':<8} {'Latency':>9} {'Error'}")
            print(f"  {'-'*10} {'-'*15} {'-'*8} {'-'*9} {'-'*20}")
            for ds in sorted(data_sources, key=lambda x: (x.ticker, x.provider)):
                status = "OK" if ds.success else "FAIL"
                lat = f"{ds.latency_s:.2f}s"
                err = (ds.error[:30] + "...") if ds.error and len(ds.error) > 30 else (ds.error or "")
                print(f"  {ds.ticker:<10} {ds.provider:<15} {status:<8} {lat:>9} {err}")

            ds_ok = sum(1 for d in data_sources if d.success)
            avg_lat = sum(d.latency_s for d in data_sources) / len(data_sources)
            print(f"\n  Data sources: {ds_ok}/{len(data_sources)} succeeded | Avg latency: {avg_lat:.2f}s")

        # ── Pipeline total ──
        print(f"\n  Pipeline wall-clock: {elapsed:.1f}s")
        print(f"{'='*width}\n")


def _log_scout(m: ScoutMetrics) -> None:
    """Structured log line for a single scout completion."""
    status = "OK" if m.success else "FAIL"
    parts = [
        f"[observability] scout={m.scout_name}",
        f"status={status}",
        f"duration={m.duration_s:.2f}s",
    ]
    if m.ticker:
        parts.append(f"ticker={m.ticker}")
    if m.signal_count:
        parts.append(f"signals={m.signal_count}")
    if m.error_msg:
        parts.append(f"error={m.error_msg[:80]}")
    print("  " + " | ".join(parts))
