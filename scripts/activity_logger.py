"""
activity_logger.py — Structured activity logging for Stock Radar pipeline.

Writes to the activity_log Supabase table. Every pipeline event (scout runs,
analyst scoring, circuit breaker warnings, model generation, errors) gets a
structured log entry that the /logs dashboard page renders.

Usage:
    from activity_logger import log_info, log_warn, log_error

    log_info("scout", "Scout completed", ticker="LITE", source="scout_quant",
             message="Quant screener finished in 2.3s", duration_ms=2300,
             metadata={"signals": 5, "composite": 7.2})

    log_warn("circuit_breaker", "Low scout coverage", ticker="PLTR",
             source="analyst", message="Only 3/6 scouts scored")

    log_error("scout", "Scout failed", ticker="RKLB", source="scout_news",
              message="Perplexity API timeout after 30s")
"""

from __future__ import annotations

import time
import traceback
from datetime import datetime, timezone
from typing import Any

# Run ID is set by the pipeline runner; None for ad-hoc script runs.
_current_run_id: str | None = None


def set_run_id(run_id: str) -> None:
    """Set the current pipeline run ID (called by run_pipeline.py at start)."""
    global _current_run_id
    _current_run_id = run_id


def get_run_id() -> str | None:
    return _current_run_id


def _get_client():
    """Lazy import to avoid circular deps and allow graceful degradation."""
    try:
        from supabase_helper import get_client
        return get_client()
    except Exception:
        return None


def _write_log(
    category: str,
    level: str,
    title: str,
    ticker: str | None = None,
    source: str = "",
    message: str = "",
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    """Write a single log entry to Supabase. Fire-and-forget — never raises."""
    try:
        sb = _get_client()
        if sb is None:
            return

        row = {
            "category": category,
            "level": level,
            "title": title,
            "ticker": ticker,
            "source": source,
            "message": message or "",
            "run_id": run_id or _current_run_id,
            "metadata": metadata or {},
            "duration_ms": duration_ms,
        }
        sb.table("activity_log").insert(row).execute()
    except Exception as e:
        # Never let logging failures break the pipeline
        print(f"  [activity_logger] write failed: {e}")


def log_info(
    category: str,
    title: str,
    *,
    ticker: str | None = None,
    source: str = "",
    message: str = "",
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    """Log an informational event."""
    _write_log(category, "info", title, ticker=ticker, source=source,
               message=message, run_id=run_id, metadata=metadata,
               duration_ms=duration_ms)


def log_warn(
    category: str,
    title: str,
    *,
    ticker: str | None = None,
    source: str = "",
    message: str = "",
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    """Log a warning event (circuit breaker flags, data quality issues)."""
    _write_log(category, "warn", title, ticker=ticker, source=source,
               message=message, run_id=run_id, metadata=metadata,
               duration_ms=duration_ms)


def log_error(
    category: str,
    title: str,
    *,
    ticker: str | None = None,
    source: str = "",
    message: str = "",
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    """Log an error event."""
    _write_log(category, "error", title, ticker=ticker, source=source,
               message=message, run_id=run_id, metadata=metadata,
               duration_ms=duration_ms)


class LogTimer:
    """Context manager that auto-logs duration.

    Usage:
        with LogTimer("scout", "Quant scout", ticker="LITE", source="scout_quant"):
            run_quant_scout("LITE")
    """

    def __init__(
        self,
        category: str,
        title: str,
        *,
        ticker: str | None = None,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        self.category = category
        self.title = title
        self.ticker = ticker
        self.source = source
        self.metadata = metadata or {}
        self._start = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = int((time.monotonic() - self._start) * 1000)
        if exc_type is not None:
            log_error(
                self.category,
                f"{self.title} — failed",
                ticker=self.ticker,
                source=self.source,
                message=f"{exc_type.__name__}: {exc_val}",
                duration_ms=elapsed_ms,
                metadata={**self.metadata, "traceback": traceback.format_exc()[-500:]},
            )
        else:
            log_info(
                self.category,
                f"{self.title} — completed",
                ticker=self.ticker,
                source=self.source,
                duration_ms=elapsed_ms,
                metadata=self.metadata,
            )
        return False  # don't suppress exceptions
