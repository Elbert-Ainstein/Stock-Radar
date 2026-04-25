"""
prediction_logger.py — Log prediction snapshots for feedback calibration.

Every pipeline run records: target price, scenario prices, valuation method,
archetype, routing scores, sigmoid parameters, and context inputs. This is
the data the feedback calibration layer (Phase 5) will regress against.

The data is irreplaceable — you cannot retroactively recover predictions you
did not log. Start logging immediately.
"""

import re
import sys
from datetime import datetime, timezone
from typing import Any

from supabase_helper import get_client
from utils import get_run_id


# ── Helpers ───────────────────────────────────────────────────────────────────

def _coerce_row(snapshot: dict) -> dict:
    """
    Build a well-typed prediction_log row from a raw snapshot dict.
    All float fields fall back to None rather than raising on bad values.
    JSONB fields default to empty dicts.
    """
    def _f(key: str) -> float | None:
        v = snapshot.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "ticker": snapshot["ticker"],
        "run_id": snapshot.get("run_id") or get_run_id(),
        "current_price": _f("current_price"),
        "target_base": _f("target_base"),
        "target_low": _f("target_low"),
        "target_high": _f("target_high"),
        "valuation_method": snapshot.get("valuation_method"),
        "archetype": snapshot.get("archetype"),
        "routing_score": _f("routing_score"),
        "projection_score": _f("projection_score"),
        "event_weight": _f("event_weight"),
        "final_target": _f("final_target"),
        "sigmoid_params": snapshot.get("sigmoid_params") or {},
        "context_inputs": snapshot.get("context_inputs") or {},
        "scenario_probabilities": snapshot.get("scenario_probabilities") or {},
    }


def _strip_bad_column(rows: list[dict], error_msg: str) -> str | None:
    """
    Parse a PostgREST / Postgres 'column does not exist' error and strip
    the offending column from every row in-place. Returns the column name
    that was stripped, or None if the error was something else.
    """
    m = re.search(
        r"column\s+(?:prediction_log\.)?['\"]?([a-zA-Z_][a-zA-Z0-9_]*)['\"]?\s+does not exist",
        error_msg,
    )
    if not m:
        m = re.search(r"Could not find the '([a-zA-Z_][a-zA-Z0-9_]*)' column", error_msg)
    if not m:
        return None

    bad_col = m.group(1)
    sample_val = rows[0].get(bad_col) if rows else None
    sample_repr = repr(sample_val)[:80] if sample_val is not None else "None"
    print(
        f"  [prediction_logger] WARNING: Column '{bad_col}' missing in DB — "
        f"stripping from {len(rows)} rows. Sample value lost: {sample_repr}. "
        f"(Apply supabase/prediction_log.sql to persist this field.)",
        file=sys.stderr,
    )
    for r in rows:
        r.pop(bad_col, None)
    return bad_col


def _upsert_with_retry(table: str, rows: list[dict], on_conflict: str | None = None) -> list[dict]:
    """
    Upsert rows into `table`, retrying up to 5 times and stripping unknown
    columns on each PostgREST schema-mismatch error. Mirrors the pattern
    used in analyst.py for schema-drift resilience.
    """
    sb = get_client()
    for attempt in range(5):
        try:
            if on_conflict:
                resp = sb.table(table).upsert(rows, on_conflict=on_conflict).execute()
            else:
                resp = sb.table(table).insert(rows).execute()
            return resp.data or []
        except Exception as e:
            msg = str(e)
            bad_col = _strip_bad_column(rows, msg)
            if bad_col:
                continue  # retry without that column
            # Not a schema error — give up
            print(f"  [prediction_logger] DB error on '{table}': {e}", file=sys.stderr)
            return []
    print(f"  [prediction_logger] Failed to write to '{table}' after 5 retries.", file=sys.stderr)
    return []


# ── Public API ────────────────────────────────────────────────────────────────

def log_prediction(ticker: str, snapshot_data: dict[str, Any]) -> dict:
    """
    Upsert a single prediction snapshot to the prediction_log table.

    Parameters
    ----------
    ticker : str
        Stock ticker, e.g. "MRVL".
    snapshot_data : dict
        Must contain at minimum 'ticker'. All other fields are optional;
        missing numeric fields are stored as NULL, missing JSONB fields as {}.

    Returns
    -------
    dict
        The inserted/updated row as returned by Supabase, or {} on failure.
    """
    snapshot_data = {**snapshot_data, "ticker": ticker}
    row = _coerce_row(snapshot_data)

    results = _upsert_with_retry(
        "prediction_log",
        [row],
        on_conflict="ticker,run_id",
    )

    if results:
        print(
            f"  [prediction_logger] Logged prediction for {ticker} "
            f"(run: {row.get('run_id')}, target: {row.get('final_target')})"
        )
        return results[0]

    return {}


def log_predictions_batch(predictions: list[dict[str, Any]]) -> list[dict]:
    """
    Batch-insert prediction snapshots for all watchlist stocks in one call.

    Parameters
    ----------
    predictions : list[dict]
        Each dict must contain 'ticker' plus any subset of the prediction_log
        columns. All rows are coerced and schema-drift stripped uniformly.

    Returns
    -------
    list[dict]
        Rows returned by Supabase after insert, or [] on failure.
    """
    if not predictions:
        return []

    rows = [_coerce_row(p) for p in predictions]

    results = _upsert_with_retry(
        "prediction_log",
        rows,
        on_conflict="ticker,run_id",
    )

    if results:
        print(
            f"  [prediction_logger] Batch-logged {len(results)} predictions "
            f"(run: {rows[0].get('run_id')})"
        )
    return results


def record_price_outcome(
    ticker: str,
    prediction_id: str,
    days_elapsed: int,
    actual_price: float,
) -> dict:
    """
    Record an actual price observation against a logged prediction.
    Intended to be called by the price-tracker cron job.

    Parameters
    ----------
    ticker : str
        Stock ticker.
    prediction_id : str
        UUID of the corresponding prediction_log row.
    days_elapsed : int
        Number of calendar days since the prediction was logged.
    actual_price : float
        Observed market price at this checkpoint.

    Returns
    -------
    dict
        The inserted prediction_outcomes row, or {} on failure.
    """
    try:
        actual_price = float(actual_price)
    except (TypeError, ValueError):
        print(
            f"  [prediction_logger] Invalid actual_price for {ticker}: {actual_price!r}",
            file=sys.stderr,
        )
        return {}

    row: dict[str, Any] = {
        "prediction_id": prediction_id,
        "ticker": ticker,
        "days_elapsed": int(days_elapsed),
        "actual_price": actual_price,
    }

    results = _upsert_with_retry("prediction_outcomes", [row])

    if results:
        print(
            f"  [prediction_logger] Recorded outcome for {ticker}: "
            f"${actual_price:.2f} at +{days_elapsed}d (prediction: {prediction_id})"
        )
        return results[0]

    return {}
