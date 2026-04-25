"""
calibration.py — Feedback readers for event magnitude calibration and target price convergence.

Two calibration systems:

1. **Event Magnitude Calibration** — compares predicted event impacts
   (from event_reasoner) against actual price movements over the event's
   time horizon. Produces per-event-type calibration ratios.

2. **Target Price Convergence** — compares predicted target prices
   (from prediction_log) against actual outcomes (from prediction_outcomes).
   Tracks systematic bias by archetype and sector.

These feed back into the pipeline:
  - Event calibration ratios adjust the event_reasoner's magnitude estimates.
  - Target convergence bias adjusts scenario probabilities or target spreads.

Usage:
    from calibration import (
        calibrate_event_magnitudes,
        compute_target_convergence,
        get_event_calibration_ratios,
    )

    # During pipeline:
    event_cal = calibrate_event_magnitudes()
    target_conv = compute_target_convergence()

    # Get ratios for event_reasoner:
    ratios = get_event_calibration_ratios()
    # ratios = {"earnings_beat": 0.72, "product_launch": 1.15, ...}
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_env

load_env()

# ─── Helpers ───

def _sb():
    """Get Supabase client, return None on failure."""
    try:
        from supabase_helper import get_client
        return get_client()
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# 1. EVENT MAGNITUDE CALIBRATION
# ═══════════════════════════════════════════════════════════════

def calibrate_event_magnitudes(
    lookback_days: int = 90,
    min_samples: int = 3,
) -> dict:
    """Compare predicted event impacts to actual price movements.

    For each analysis row with event_impacts, we:
      1. Extract the predicted events and their expected_contribution_pct
      2. Look up the actual price change over each event's time_horizon
      3. Compute calibration ratio = actual_change / predicted_change

    Args:
        lookback_days: how far back to look for analysis rows
        min_samples: minimum samples per event type before we trust the ratio

    Returns:
        {
            "by_event_type": {
                "earnings_beat": {
                    "predicted_avg": 5.2,
                    "actual_avg": 3.8,
                    "calibration_ratio": 0.73,
                    "n": 12,
                    "direction_accuracy": 0.83,
                },
                ...
            },
            "overall": {
                "predicted_avg": 4.1,
                "actual_avg": 3.2,
                "calibration_ratio": 0.78,
                "n": 45,
                "direction_accuracy": 0.71,
            },
            "evaluated": int,
            "skipped": int,
        }
    """
    sb = _sb()
    if not sb:
        return {"by_event_type": {}, "overall": {}, "evaluated": 0, "skipped": 0}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    try:
        # Load analysis rows with event impacts
        resp = (
            sb.table("analysis")
            .select("ticker, event_impacts, price_data, created_at")
            .gte("created_at", cutoff)
            .not_.is_("event_impacts", "null")
            .order("created_at", desc=True)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        print(f"  [calibration] Failed to load analysis rows: {e}", file=sys.stderr)
        return {"by_event_type": {}, "overall": {}, "evaluated": 0, "skipped": 0}

    # Collect per-event-type predictions and actuals
    type_predictions: dict[str, list[dict]] = defaultdict(list)
    evaluated = 0
    skipped = 0

    for row in rows:
        ei = row.get("event_impacts") or {}
        events = ei.get("events") or []
        price_data = row.get("price_data") or {}
        price_at_prediction = price_data.get("price")
        ticker = row.get("ticker", "")
        created_at = row.get("created_at", "")

        if not events or not price_at_prediction or price_at_prediction <= 0:
            skipped += 1
            continue

        # Try to get the current price to compute actual change
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if hist.empty:
                skipped += 1
                continue
            current_price = float(hist["Close"].iloc[-1])
        except Exception:
            skipped += 1
            continue

        # Parse created_at to compute how many days have elapsed
        try:
            pred_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            days_elapsed = (datetime.now(timezone.utc) - pred_date).days
        except (ValueError, TypeError):
            skipped += 1
            continue

        for ev in events:
            event_type = ev.get("type", "unknown")
            predicted_pct = ev.get("expected_contribution_pct", 0)
            horizon_months = ev.get("time_horizon_months", 6)

            # Only evaluate if enough time has passed (at least 30 days or half the horizon)
            min_days = max(30, int(horizon_months * 30 * 0.5))
            if days_elapsed < min_days:
                continue

            # Actual price change % since the prediction
            actual_change_pct = ((current_price - price_at_prediction) / price_at_prediction) * 100

            type_predictions[event_type].append({
                "ticker": ticker,
                "predicted_pct": predicted_pct,
                "actual_change_pct": actual_change_pct,
                "days_elapsed": days_elapsed,
                "horizon_months": horizon_months,
            })
            evaluated += 1

    # Aggregate by event type
    by_event_type = {}
    all_predicted = []
    all_actual = []

    for etype, samples in type_predictions.items():
        if len(samples) < min_samples:
            continue

        predicted_vals = [s["predicted_pct"] for s in samples]
        actual_vals = [s["actual_change_pct"] for s in samples]
        pred_avg = sum(predicted_vals) / len(predicted_vals)
        actual_avg = sum(actual_vals) / len(actual_vals)

        # Calibration ratio: how much to scale predictions
        # If we predicted +5% but got +3.5%, ratio = 0.70
        cal_ratio = (actual_avg / pred_avg) if abs(pred_avg) > 0.01 else 1.0
        cal_ratio = max(0.1, min(3.0, cal_ratio))  # clamp to reasonable range

        # Direction accuracy: did we predict the right sign?
        correct_direction = sum(
            1 for s in samples
            if (s["predicted_pct"] >= 0) == (s["actual_change_pct"] >= 0)
        )
        direction_accuracy = correct_direction / len(samples) if samples else 0

        by_event_type[etype] = {
            "predicted_avg": round(pred_avg, 2),
            "actual_avg": round(actual_avg, 2),
            "calibration_ratio": round(cal_ratio, 3),
            "n": len(samples),
            "direction_accuracy": round(direction_accuracy, 3),
        }

        all_predicted.extend(predicted_vals)
        all_actual.extend(actual_vals)

    # Overall stats
    overall = {}
    if all_predicted:
        overall_pred_avg = sum(all_predicted) / len(all_predicted)
        overall_actual_avg = sum(all_actual) / len(all_actual)
        overall_ratio = (overall_actual_avg / overall_pred_avg) if abs(overall_pred_avg) > 0.01 else 1.0
        correct_dir = sum(1 for p, a in zip(all_predicted, all_actual) if (p >= 0) == (a >= 0))
        overall = {
            "predicted_avg": round(overall_pred_avg, 2),
            "actual_avg": round(overall_actual_avg, 2),
            "calibration_ratio": round(max(0.1, min(3.0, overall_ratio)), 3),
            "n": len(all_predicted),
            "direction_accuracy": round(correct_dir / len(all_predicted), 3),
        }

    result = {
        "by_event_type": by_event_type,
        "overall": overall,
        "evaluated": evaluated,
        "skipped": skipped,
    }

    # Store calibration ratios in Supabase for persistence
    _store_calibration(sb, "event_magnitude", result)

    print(f"  [calibration] Event magnitude: {evaluated} evaluated, {skipped} skipped, "
          f"{len(by_event_type)} event types calibrated")
    if overall:
        print(f"  [calibration] Overall ratio: {overall['calibration_ratio']:.2f} "
              f"(predicted avg: {overall['predicted_avg']:.1f}%, actual avg: {overall['actual_avg']:.1f}%)")

    return result


def get_event_calibration_ratios() -> dict[str, float]:
    """Load cached per-event-type calibration ratios.

    Returns a dict mapping event_type → ratio (1.0 = perfectly calibrated).
    Falls back to empty dict if no calibration data exists.
    """
    sb = _sb()
    if not sb:
        return {}

    try:
        resp = (
            sb.table("calibration_cache")
            .select("data")
            .eq("calibration_type", "event_magnitude")
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if resp.data:
            data = resp.data.get("data", {})
            by_type = data.get("by_event_type", {})
            return {k: v["calibration_ratio"] for k, v in by_type.items() if "calibration_ratio" in v}
    except Exception:
        pass

    return {}


# ═══════════════════════════════════════════════════════════════
# 2. TARGET PRICE CONVERGENCE
# ═══════════════════════════════════════════════════════════════

def compute_target_convergence(
    min_days: int = 7,
) -> dict:
    """Compare predicted target prices to actual price outcomes.

    Reads prediction_log (what we predicted) and prediction_outcomes
    (what actually happened), then computes systematic bias by:
      - archetype (are we consistently bullish on cyclicals?)
      - sector (are we over-optimistic on semiconductors?)
      - overall direction (do we skew bullish or bearish?)

    Args:
        min_days: minimum days elapsed before evaluating a prediction

    Returns:
        {
            "by_archetype": {
                "garp": {"bias_pct": 12.3, "mae_pct": 18.5, "n": 15, ...},
                ...
            },
            "by_sector": {
                "semiconductors": {"bias_pct": -5.2, "mae_pct": 14.3, "n": 8, ...},
                ...
            },
            "overall": {
                "bias_pct": 8.1,
                "mae_pct": 16.2,
                "n": 42,
                "accuracy_30d": 0.62,
            },
            "predictions_evaluated": int,
        }
    """
    sb = _sb()
    if not sb:
        return {"by_archetype": {}, "by_sector": {}, "overall": {}, "predictions_evaluated": 0}

    try:
        # Load predictions with outcomes
        pred_resp = (
            sb.table("prediction_log")
            .select("id, ticker, target_base, target_low, target_high, "
                    "current_price, archetype, context_inputs, created_at")
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        predictions = pred_resp.data or []

        if not predictions:
            return {"by_archetype": {}, "by_sector": {}, "overall": {}, "predictions_evaluated": 0}

        # Load all outcomes
        pred_ids = [p["id"] for p in predictions if p.get("id")]
        outcomes_by_pred: dict[str, list[dict]] = defaultdict(list)

        # Batch fetch outcomes (Supabase .in_ has a limit, chunk)
        for i in range(0, len(pred_ids), 50):
            chunk = pred_ids[i:i + 50]
            out_resp = (
                sb.table("prediction_outcomes")
                .select("prediction_id, actual_price, days_elapsed")
                .in_("prediction_id", chunk)
                .execute()
            )
            for o in (out_resp.data or []):
                outcomes_by_pred[o["prediction_id"]].append(o)

    except Exception as e:
        print(f"  [calibration] Failed to load predictions/outcomes: {e}", file=sys.stderr)
        return {"by_archetype": {}, "by_sector": {}, "overall": {}, "predictions_evaluated": 0}

    # Aggregate
    archetype_data: dict[str, list[dict]] = defaultdict(list)
    sector_data: dict[str, list[dict]] = defaultdict(list)
    all_data: list[dict] = []

    evaluated = 0
    for pred in predictions:
        pred_id = pred.get("id")
        outcomes = outcomes_by_pred.get(pred_id, [])
        if not outcomes:
            continue

        target_base = pred.get("target_base")
        current_price = pred.get("current_price")
        if not target_base or not current_price or current_price <= 0:
            continue

        # Use the latest outcome
        latest = max(outcomes, key=lambda o: o.get("days_elapsed", 0))
        if latest.get("days_elapsed", 0) < min_days:
            continue

        actual_price = latest.get("actual_price", 0)
        if not actual_price or actual_price <= 0:
            continue

        # Predicted return vs actual return
        predicted_return_pct = ((target_base - current_price) / current_price) * 100
        actual_return_pct = ((actual_price - current_price) / current_price) * 100
        bias_pct = predicted_return_pct - actual_return_pct  # positive = we were too bullish

        entry = {
            "ticker": pred.get("ticker"),
            "predicted_return_pct": predicted_return_pct,
            "actual_return_pct": actual_return_pct,
            "bias_pct": bias_pct,
            "abs_error_pct": abs(bias_pct),
            "days_elapsed": latest["days_elapsed"],
        }

        archetype = (pred.get("archetype") or "unknown").lower()
        ctx = pred.get("context_inputs") or {}
        sector = (ctx.get("sector") or "unknown").lower()

        archetype_data[archetype].append(entry)
        sector_data[sector].append(entry)
        all_data.append(entry)
        evaluated += 1

    def _summarize(entries: list[dict]) -> dict:
        if not entries:
            return {}
        biases = [e["bias_pct"] for e in entries]
        errors = [e["abs_error_pct"] for e in entries]
        correct_direction = sum(
            1 for e in entries
            if (e["predicted_return_pct"] >= 0) == (e["actual_return_pct"] >= 0)
        )
        return {
            "bias_pct": round(sum(biases) / len(biases), 2),
            "mae_pct": round(sum(errors) / len(errors), 2),
            "n": len(entries),
            "direction_accuracy": round(correct_direction / len(entries), 3),
            "median_bias_pct": round(sorted(biases)[len(biases) // 2], 2),
        }

    result = {
        "by_archetype": {k: _summarize(v) for k, v in archetype_data.items() if len(v) >= 2},
        "by_sector": {k: _summarize(v) for k, v in sector_data.items() if len(v) >= 2},
        "overall": _summarize(all_data),
        "predictions_evaluated": evaluated,
    }

    _store_calibration(sb, "target_convergence", result)

    print(f"  [calibration] Target convergence: {evaluated} predictions evaluated")
    if result["overall"]:
        o = result["overall"]
        print(f"  [calibration] Overall bias: {o['bias_pct']:+.1f}% "
              f"(MAE: {o['mae_pct']:.1f}%, direction accuracy: {o['direction_accuracy']:.0%})")
        bias_direction = "bullish" if o["bias_pct"] > 0 else "bearish"
        if abs(o["bias_pct"]) > 10:
            print(f"  [calibration] WARNING: Systematic {bias_direction} bias detected ({o['bias_pct']:+.1f}%)")

    return result


# ═══════════════════════════════════════════════════════════════
# PERSISTENCE
# ═══════════════════════════════════════════════════════════════

def _store_calibration(sb, calibration_type: str, data: dict):
    """Store calibration results in Supabase for downstream consumption.

    Uses a calibration_cache table. If it doesn't exist, fails silently
    (the calibration still ran — we just can't persist it).
    """
    try:
        sb.table("calibration_cache").upsert({
            "calibration_type": calibration_type,
            "data": data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="calibration_type").execute()
    except Exception as e:
        # Table may not exist yet — non-fatal
        print(f"  [calibration] Cache write failed (non-fatal): {e}", file=sys.stderr)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def run_calibration() -> dict:
    """Run all calibration tasks. Called from feedback loop or standalone."""
    print("\n" + "-" * 60)
    print("  CALIBRATION: Event Magnitudes + Target Convergence")
    print("-" * 60)

    event_cal = calibrate_event_magnitudes()
    target_conv = compute_target_convergence()

    return {
        "event_calibration": event_cal,
        "target_convergence": target_conv,
    }


if __name__ == "__main__":
    run_calibration()
