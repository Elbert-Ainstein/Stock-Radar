#!/usr/bin/env python3
"""
Analyst Layer: Aggregates all scout signals, detects convergence, scores stocks.
Produces the final analysis.json that the dashboard reads.

Usage:
    python scripts/analyst.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from utils import DATA_DIR, get_watchlist, get_run_id, timestamp

# Event reasoner is optional — degrade gracefully if not importable
# (e.g. first deploy before dependencies are wired up).
try:
    from event_reasoner import reason_events, sum_adjustments
    _EVENT_REASONER_AVAILABLE = True
except ImportError as _e:
    print(f"  [analyst] event_reasoner unavailable: {_e} — event_impacts will be empty")
    _EVENT_REASONER_AVAILABLE = False
    def reason_events(events, stock_context):  # type: ignore
        return []
    def sum_adjustments(reasoned):  # type: ignore
        return {"event_adjustment_pct": 0.0, "raw_sum_pct": 0.0, "capped": False,
                "event_count": 0, "up_count": 0, "down_count": 0}

# Kill-condition evaluator is optional — grades whether a stock's thesis-break
# scenario is approaching, triggered, or safe. Uses Claude to compare the
# plain-English kill condition against current signals.
try:
    from kill_condition_eval import evaluate_kill_condition
    _KILL_EVAL_AVAILABLE = True
except ImportError as _e:
    print(f"  [analyst] kill_condition_eval unavailable: {_e}")
    _KILL_EVAL_AVAILABLE = False

# Target engine is optional — if available, we use the institutional-grade engine target
# as the base_target anchor instead of the user-set static price. Falls back
# gracefully to the user-set target when the engine can't run.
try:
    from target_engine import build_target as _engine_build_target
    from finance_data import fetch_financials as _engine_fetch_financials, EarningsFetchError
    _TARGET_ENGINE_AVAILABLE = True
except ImportError as _e:
    print(f"  [analyst] target_engine unavailable: {_e} — using user-set target as base")
    _TARGET_ENGINE_AVAILABLE = False

# Feedback loop — adaptive scout weights based on historical accuracy.
# Optional: falls back to static FACTOR_WEIGHTS if unavailable or not enough data.
try:
    from feedback_loop import get_adaptive_weights
    _FEEDBACK_LOOP_AVAILABLE = True
except ImportError as _e:
    print(f"  [analyst] feedback_loop unavailable: {_e} — using static weights")
    _FEEDBACK_LOOP_AVAILABLE = False

# Target blend is optional too — same graceful-degrade pattern. If the module
# isn't available (old checkout, import failure), we fall back to the legacy
# static behavior: full event weight, neutral projection score.
try:
    from target_blend import compute_projection_score, blend_targets
    _TARGET_BLEND_AVAILABLE = True
except ImportError as _e:
    print(f"  [analyst] target_blend unavailable: {_e} — using static event weight")
    _TARGET_BLEND_AVAILABLE = False
    def compute_projection_score(fundamentals_data, quant_data, stock_config):  # type: ignore
        return {"score": 0.5, "baseline": 0.5, "contributors": [], "raw_score": 0.5,
                "final_explanation": "baseline 0.50 (target_blend unavailable) = 0.50"}
    def blend_targets(base_target, criteria_pct, event_pct, projection_score):  # type: ignore
        # Neutral-score fallback mirrors the formula so downstream shape is identical.
        weight = 0.65  # midpoint of [0.30, 1.00]
        ev_w = float(event_pct or 0) * weight
        total = float(criteria_pct or 0) + ev_w
        final = round(float(base_target or 0) * (1 + total / 100.0))
        return {"base_target": round(float(base_target or 0)), "criteria_pct": round(float(criteria_pct or 0), 2),
                "event_pct_raw": round(float(event_pct or 0), 2), "event_weight": round(weight, 3),
                "event_pct_weighted": round(ev_w, 2), "total_adjustment_pct": round(total, 2),
                "final_target": final, "formula": "fallback (target_blend unavailable)"}

SIGNAL_WEIGHTS = {
    "bullish": 1.0,
    "neutral": 0.0,
    "bearish": -1.0,
}

# Scoring weights for composite score
# NOTE: convergence is NOT a weighted factor — it's used as a conviction
# gate/label only. Including it as a weighted component in a linear blend
# double-counts scout agreement (the underlying scouts already vote via
# their own weights). Instead, convergence level is surfaced as metadata
# for position-sizing / conviction assessment.
FACTOR_WEIGHTS = {
    "quant_score": 0.28,        # Fundamental quality (quant metrics)
    "fundamentals": 0.24,       # Business fundamentals quality
    "momentum": 0.18,           # Price momentum (strong diversifier vs value)
    "insider_score": 0.12,      # Insider activity
    "news_sentiment": 0.10,     # News sentiment (decayed alpha)
    "youtube": 0.08,            # YouTube analyst sentiment (supplementary)
    # "convergence" removed — now a conviction gate, not a score input
}
# Sum = 1.00. Renormalized at scoring time over *available* factors only.


def _load_scouts_from_supabase() -> dict | None:
    """Primary source of truth: Supabase latest_signals view.

    Scouts write to Supabase (utils.save_signals returns after a successful
    Supabase insert and never falls through to JSON). Reading JSON here meant
    every analyst run was scoring whatever the local JSON happened to contain
    — usually months-stale data. Reading from latest_signals keeps analyst
    aligned with what scouts actually produced in the most recent run.

    Returns a dict shaped like the legacy JSON loader:
        {scout_lowercase: {"signals": [...], "generated_at": latest_ts}}
    or None if the DB is unreachable (caller falls back to JSON).
    """
    try:
        from supabase_helper import get_client
        sb = get_client()
    except Exception as e:
        print(f"  [analyst] Supabase unavailable ({e}) — falling back to JSON scout files")
        return None

    # Canonical scout capitalizations — analyst.analyze_stock matches on these.
    name_map = {
        "quant": "Quant",
        "insider": "Insider",
        "news": "News",
        "social": "Social",
        "youtube": "YouTube",
        "fundamentals": "Fundamentals",
    }

    try:
        rows = sb.table("latest_signals").select("*").execute().data or []
    except Exception as e:
        print(f"  [analyst] latest_signals query failed ({e}) — falling back to JSON")
        return None

    scouts: dict[str, dict] = {}
    for r in rows:
        scout_raw = (r.get("scout") or "").lower()
        canonical = name_map.get(scout_raw, scout_raw.capitalize())
        bucket = scouts.setdefault(scout_raw, {"signals": [], "generated_at": ""})
        bucket["signals"].append({
            "ticker": r.get("ticker"),
            "scout": canonical,
            "signal": r.get("signal"),
            "summary": r.get("summary") or "",
            "data": r.get("data") or {},
            "scores": r.get("scores") or {},
            "ai": r.get("ai") or "",
            "timestamp": r.get("created_at") or "",
        })
        ts = r.get("created_at") or ""
        if ts > bucket["generated_at"]:
            bucket["generated_at"] = ts

    for name, bucket in scouts.items():
        print(f"  Loaded {name}: {len(bucket['signals'])} signals from Supabase")

    return scouts if scouts else None


def _load_scouts_from_json() -> dict:
    """Fallback: read local *_signals.json files (used only when DB is down)."""
    scouts = {}
    for f in DATA_DIR.glob("*_signals.json"):
        scout_name = f.stem.replace("_signals", "")
        try:
            data = json.loads(f.read_text())
            signal_count = len(data.get("signals", []))
            if signal_count > 0:
                scouts[scout_name] = data
                print(f"  Loaded {scout_name}: {signal_count} signals (JSON fallback)")
            else:
                print(f"  Skipped {scout_name}: 0 signals (empty)")
        except Exception as e:
            print(f"  Error loading {f.name}: {e}")
    return scouts


def load_all_scout_data() -> dict:
    """Load scout signals. Supabase first (source of truth), JSON fallback."""
    scouts = _load_scouts_from_supabase()
    if scouts:
        return scouts
    print("  [analyst] Using local JSON scout files — these may be stale")
    return _load_scouts_from_json()


def get_signals_for_ticker(ticker: str, all_scouts: dict) -> list[dict]:
    """Collect all signals for a given ticker across all scouts."""
    signals = []
    for scout_name, scout_data in all_scouts.items():
        for sig in scout_data.get("signals", []):
            if sig.get("ticker") == ticker:
                signals.append(sig)
    return signals


def compute_convergence(signals: list[dict]) -> dict:
    """Detect convergence across scouts.

    Scoring is a smooth function of net sentiment and unanimity — no cliffs.
      net        = (bullish - bearish) / total   ∈ [-1, +1]
      unanimity  = max(bullish, bearish) / total ∈ [0, 1]
      score      = 5 + net * 5 * (0.5 + 0.5 * unanimity)

    This way, 3/3 bullish scores 10, 3/4 bullish scores ~8.3, 2/4 bullish ~6.9,
    and going from 2→3 bullish does not jump from 7 to 10.
    """
    if not signals:
        # Missing data → neutral 5, not 0 (which would drag composite down unfairly)
        return {"level": "none", "score": 5, "bullish": 0, "bearish": 0, "neutral": 0, "total": 0}

    bullish = sum(1 for s in signals if s.get("signal") == "bullish")
    bearish = sum(1 for s in signals if s.get("signal") == "bearish")
    neutral = sum(1 for s in signals if s.get("signal") == "neutral")
    total = len(signals)

    if total == 0:
        return {"level": "none", "score": 5, "bullish": 0, "bearish": 0, "neutral": 0, "total": 0}

    net = (bullish - bearish) / total
    unanimity = max(bullish, bearish) / total
    # Amplify direction by unanimity — mixed signals stay near 5
    score = 5 + net * 5 * (0.5 + 0.5 * unanimity)
    score = round(max(0, min(10, score)), 1)

    # Level labels (descriptive, not used for scoring anymore)
    if bullish >= 3 and bearish == 0 and total >= 3:
        level = "strong_bullish"
    elif net >= 0.5:
        level = "moderate_bullish"
    elif net > 0:
        level = "lean_bullish"
    elif bearish >= 3 and bullish == 0 and total >= 3:
        level = "strong_bearish"
    elif net <= -0.5:
        level = "moderate_bearish"
    elif net < 0:
        level = "lean_bearish"
    else:
        level = "mixed"

    return {
        "level": level,
        "score": score,
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "total": total,
    }


import re

def _extract_threshold(hint: str) -> float | None:
    """Pull the first number from an eval_hint that looks like a threshold."""
    m = re.search(r'[\u2265>=]+\s*\$?([\d.]+)', hint)
    if m:
        return float(m.group(1))
    m = re.search(r'[\u2264<=]+\s*\$?([\d.]+)', hint)
    if m:
        return float(m.group(1))
    return None


def _progress_pct(current: float | None, target: float, higher_is_better: bool = True) -> float | None:
    """Compute 0-100 progress toward a threshold."""
    if current is None or target == 0:
        return None
    if higher_is_better:
        return min(100, max(0, (current / target) * 100))
    else:
        # Lower is better (e.g. shares ≤ 80M)
        if current <= target:
            return 100
        # Overshoot: how far past target
        return max(0, 100 - ((current - target) / target) * 100)


def _find_relevant_news(criterion_id: str, criterion_label: str, all_news: list[dict]) -> list[dict]:
    """Find news headlines relevant to a criterion by keyword matching."""
    if not all_news:
        return []

    # Build keyword set from criterion id + label
    keywords = set()
    for word in criterion_id.replace("_", " ").split():
        if len(word) > 2:
            keywords.add(word.lower())
    for word in criterion_label.split():
        w = word.lower().strip("()%+$,.")
        if len(w) > 2 and w not in {"the", "and", "for", "from", "with", "above", "below", "toward", "stays", "reaches", "exceeds", "sustains", "growing"}:
            keywords.add(w)

    matched = []
    for article in all_news:
        title = article.get("title", "").lower()
        url = article.get("url", "")
        source = article.get("source", "")
        date = article.get("date", "")

        # Score: how many keywords appear in the headline
        hits = sum(1 for kw in keywords if kw in title)
        if hits >= 2:
            matched.append({
                "title": article.get("title", ""),
                "url": url,
                "source": source,
                "date": date,
                "relevance": hits,
            })

    # Sort by relevance, return top 3
    matched.sort(key=lambda x: x["relevance"], reverse=True)
    return matched[:3]


def _variable_fallback(variable: str, quant_data: dict, threshold: float | None, hint: str) -> tuple:
    """
    Variable-based fallback evaluation when keyword matching doesn't fire.
    Returns (current_val, current_label, target_val, target_label, progress, status, note) or all Nones.

    Only fires when the hint itself confirms the metric — otherwise we'd
    misapply thresholds (e.g., treating "Inventory turnover >= 4x" as
    "Operating margin >= 4%").
    """
    hint_lower = hint.lower()

    # ─── R = Revenue ───
    # Skip when the hint is about a SEGMENT (government, international,
    # product-line, region) rather than total revenue — applying total
    # company revenue growth to a segment-specific threshold would be a
    # false positive.
    segment_keywords = [
        "government", "international", "domestic", "segment", "region",
        "product line", "division", "vertical", "enterprise", "consumer",
    ]
    is_segment_hint = any(w in hint.lower() for w in segment_keywords)

    if "R" in variable and not is_segment_hint:
        rev_growth = quant_data.get("revenue_growth_pct")
        market_cap_b = quant_data.get("market_cap_b") or 0
        ps_ratio = quant_data.get("ps_ratio")
        current_rev_b = (market_cap_b / ps_ratio) if ps_ratio and ps_ratio > 0 else None

        # Absolute-revenue hints (e.g., "revenue >= $4.4B")
        rev_abs_match = re.search(r'\$\s*([\d.]+)\s*[Bb]\b', hint)
        if rev_abs_match and "revenue" in hint_lower and current_rev_b is not None:
            target_rev = float(rev_abs_match.group(1))
            progress = _progress_pct(current_rev_b, target_rev)
            met = current_rev_b >= target_rev
            return (
                current_rev_b, f"${current_rev_b:.1f}B",
                target_rev, f"${target_rev:.0f}B",
                progress, "met" if met else "not_yet",
                f"Revenue ${current_rev_b:.1f}B {'meets' if met else 'vs'} ${target_rev:.0f}B target"
            )

        # Growth-rate hints (require explicit "growth"/"YoY"/"QoQ" signal)
        is_growth_hint = any(w in hint_lower for w in ["growth", "yoy", "qoq", "year-over-year", "year over year"])
        if is_growth_hint and rev_growth is not None and threshold is not None and threshold < 500:
            progress = _progress_pct(rev_growth, threshold)
            met = rev_growth >= threshold
            return (
                rev_growth, f"{rev_growth:.1f}%",
                threshold, f"{threshold:.0f}%",
                progress, "met" if met else "not_yet",
                f"Revenue growth {rev_growth:.1f}% {'meets' if met else 'vs'} {threshold:.0f}% target"
            )

        # No safe auto-match — indicate missing evaluation rather than guess
        if rev_growth is not None:
            return (
                rev_growth, f"{rev_growth:.1f}%",
                None, "",
                None, "not_yet",
                "Qualitative criterion — current revenue growth "
                f"{rev_growth:.1f}% YoY shown for reference"
            )

    # ─── M = Margin ───
    # Only evaluate if the hint is actually about a margin — not inventory
    # turns, SBC, or anything else that happens to use variable "M".
    if "M" in variable and "margin" in hint_lower:
        gross_margin = quant_data.get("gross_margin_pct")
        op_margin = quant_data.get("operating_margin_pct")
        if "gross" in hint_lower and gross_margin is not None:
            margin_val = gross_margin
            margin_name = "Gross margin"
        elif ("operating" in hint_lower or "op margin" in hint_lower) and op_margin is not None:
            margin_val = op_margin
            margin_name = "Operating margin"
        elif op_margin is not None:
            margin_val = op_margin
            margin_name = "Operating margin"
        elif gross_margin is not None:
            margin_val = gross_margin
            margin_name = "Gross margin"
        else:
            return (None,) * 7

        if threshold is not None:
            progress = _progress_pct(margin_val, threshold)
            met = margin_val >= threshold
            return (
                margin_val, f"{margin_val:.1f}%",
                threshold, f"{threshold:.0f}%",
                progress, "met" if met else "not_yet",
                f"{margin_name} {margin_val:.1f}% {'meets' if met else 'vs'} {threshold:.0f}% target"
            )
        return (
            margin_val, f"{margin_val:.1f}%",
            None, "",
            None, "not_yet",
            f"{margin_name} currently {margin_val:.1f}%"
        )

    # ─── P = Multiple / Valuation ───
    # Only evaluate when hint explicitly mentions a multiple (P/E, P/S, multiple)
    is_multiple_hint = any(w in hint_lower for w in [
        "p/e", "pe multiple", "pe ratio", "price/earnings",
        "p/s", "price/sales", "multiple", "valuation"
    ])
    if "P" in variable and is_multiple_hint:
        forward_pe = quant_data.get("forward_pe")
        ps_ratio = quant_data.get("ps_ratio")
        pe_ratio = quant_data.get("pe_ratio")

        if ("p/s" in hint_lower or "price/sales" in hint_lower) and ps_ratio is not None:
            val = ps_ratio
            val_name = "P/S"
        elif forward_pe is not None:
            val = forward_pe
            val_name = "Forward P/E"
        elif pe_ratio is not None:
            val = pe_ratio
            val_name = "Trailing P/E"
        elif ps_ratio is not None:
            val = ps_ratio
            val_name = "P/S"
        else:
            return (None,) * 7

        if val is not None and threshold is not None:
            # Multiples: lower can be better (compression) or higher (expansion)
            lower_is_better = any(w in hint_lower for w in ["compress", "below", "<=", "≤"])
            if lower_is_better:
                progress = _progress_pct(val, threshold, higher_is_better=False)
                met = val <= threshold
            else:
                progress = _progress_pct(val, threshold)
                met = val >= threshold
            return (
                val, f"{val:.1f}×",
                threshold, f"{threshold:.0f}×",
                progress, "met" if met else "not_yet",
                f"{val_name} {val:.1f}× {'meets' if met else 'vs'} {threshold:.0f}× target"
            )
        if val is not None:
            return (
                val, f"{val:.1f}×",
                None, "",
                None, "not_yet",
                f"{val_name} currently {val:.1f}×"
            )

    # ─── S = Shares ───
    # Only evaluate when hint is about shares outstanding/dilution
    if "S" in variable and any(w in hint_lower for w in ["share", "dilut", "float"]):
        market_cap_b = quant_data.get("market_cap_b") or 0
        price = quant_data.get("price") or 0
        shares_m = (market_cap_b * 1000) / price if price > 0 else None

        if shares_m is not None and threshold is not None:
            progress = _progress_pct(shares_m, threshold, higher_is_better=False)
            met = shares_m <= threshold
            return (
                shares_m, f"{shares_m:.0f}M",
                threshold, f"{threshold:.0f}M",
                progress, "met" if met else "not_yet",
                f"Diluted shares {shares_m:.0f}M {'within' if met else 'above'} {threshold:.0f}M limit"
            )
        if shares_m is not None:
            return (
                shares_m, f"{shares_m:.0f}M",
                None, "",
                None, "not_yet",
                f"Diluted shares currently ~{shares_m:.0f}M"
            )

    # ─── T = Tax / other — no quant data source, skip auto-eval ───
    return (None,) * 7


def evaluate_criteria(ticker: str, criteria: list[dict], quant_data: dict, news_data: dict) -> list[dict]:
    """
    Auto-evaluate criteria based on available scout data.
    Uses two-pass approach:
      1. Keyword-based matching (specific patterns like "revenue", "margin", etc.)
      2. Variable-based fallback (uses the R/M/T/S/P variable field from criteria)
    Returns criteria list with evaluation fields.
    """
    if not criteria:
        return []

    # Collect all news headlines for keyword matching
    all_news = []
    if news_data:
        all_news = news_data.get("headlines", [])
        if not all_news:
            all_news = news_data.get("articles", [])

    evaluated = []
    for c in criteria:
        result = dict(c)  # copy
        cid = c.get("id", "")
        variable = c.get("variable", "")
        hint = c.get("eval_hint", "")

        status = c.get("status", "not_yet")
        note = ""
        progress = None
        current_val = None
        target_val = None
        current_label = ""
        target_label = ""
        matched = False  # Track if keyword matching fired

        threshold = _extract_threshold(hint)

        # ═══ PASS 1: Keyword-based matching (specific patterns) ═══

        # ═══ Revenue checks ═══
        # Must distinguish between:
        #   - Growth-rate criteria  ("Revenue growth ≥ 25% YoY")
        #   - Absolute-revenue criteria  ("Q3 revenue ≥ $4.4B")
        # Previously, both would run `rev_growth >= threshold` and a $4.4B
        # target would spuriously "meet" when growth was any positive %.
        if "revenue" in cid.lower() or "growth" in cid.lower() or "qoq_growth" in cid.lower():
            hint_lower = hint.lower()
            label_lower = c.get("label", "").lower()
            rev_growth = quant_data.get("revenue_growth_pct", None)
            market_cap_b = quant_data.get("market_cap_b") or 0
            ps_ratio = quant_data.get("ps_ratio")
            current_rev_b = (market_cap_b / ps_ratio) if ps_ratio and ps_ratio > 0 else None

            # Detect absolute-$B revenue target (e.g., "$4.4B", "4.4 billion")
            abs_rev_match = re.search(r'\$\s*([\d.]+)\s*[Bb]\b', hint) or re.search(r'\$\s*([\d.]+)\s*[Bb]\b', label_lower)
            is_growth_hint = any(w in hint_lower for w in ["growth", "yoy", "qoq", "year-over-year"]) \
                          or any(w in label_lower for w in ["growth", "yoy", "qoq"])
            is_absolute_hint = bool(abs_rev_match) and not is_growth_hint

            if is_absolute_hint and current_rev_b is not None:
                target_rev = float(abs_rev_match.group(1))
                current_val = current_rev_b
                target_val = target_rev
                current_label = f"${current_rev_b:.1f}B"
                target_label = f"${target_rev:.1f}B"
                progress = _progress_pct(current_rev_b, target_rev)
                matched = True
                if current_rev_b >= target_rev:
                    status = "met"
                    note = f"Revenue ~${current_rev_b:.1f}B meets ${target_rev:.1f}B target"
                else:
                    gap = target_rev - current_rev_b
                    note = f"Revenue ~${current_rev_b:.1f}B — ${gap:.1f}B short of ${target_rev:.1f}B target"
            elif is_growth_hint and rev_growth is not None and threshold is not None and threshold < 500:
                current_val = rev_growth
                target_val = threshold
                current_label = f"{rev_growth:.1f}%"
                target_label = f"{threshold:.0f}%"
                progress = _progress_pct(rev_growth, threshold)
                matched = True
                if rev_growth >= threshold:
                    status = "met"
                    note = f"Revenue growth {rev_growth:.1f}% meets {threshold:.0f}% threshold"
                else:
                    gap = threshold - rev_growth
                    note = f"Revenue growth {rev_growth:.1f}% — needs {gap:.1f} ppt more to reach {threshold:.0f}%"

        # ═══ Margin checks ═══
        # Require "margin" in cid OR hint (NOT label alone). Labels are
        # narrative text: "Alani integration complete with margin accretion"
        # is about integration, not a margin threshold. The cid and the
        # eval_hint are the canonical signal that this is a margin criterion.
        label_lower = c.get("label", "").lower()
        hint_lower = hint.lower()
        mentions_margin = "margin" in cid.lower() or "margin" in hint_lower
        plausible_pct = threshold is not None and 0 < threshold <= 100
        if not matched and mentions_margin and plausible_pct:
            gross_margin = quant_data.get("gross_margin_pct", None)
            op_margin = quant_data.get("operating_margin_pct", None)
            adj_op_margin = quant_data.get("adj_operating_margin_pct", None)

            is_gross = "gross" in cid.lower() or "gross" in label_lower or "gross" in hint_lower
            is_operating = ("operating" in cid.lower() or "operating" in label_lower or "operating" in hint_lower
                             or "op margin" in hint_lower or "op_margin" in cid.lower())
            is_adj_op = ("adj" in cid.lower() or "adjusted" in label_lower) and is_operating

            if is_gross and gross_margin is not None:
                current_val = gross_margin
                target_val = threshold
                current_label = f"{gross_margin:.1f}%"
                target_label = f"{threshold:.0f}%"
                progress = _progress_pct(gross_margin, threshold)
                matched = True
                if gross_margin >= threshold:
                    status = "met"
                    note = f"Gross margin {gross_margin:.1f}% meets {threshold:.0f}% target"
                else:
                    gap = threshold - gross_margin
                    note = f"Gross margin {gross_margin:.1f}% — {gap:.1f} ppt below {threshold:.0f}% target"

            if not matched and is_operating:
                margin_val = adj_op_margin if (is_adj_op and adj_op_margin is not None) else op_margin
                margin_name = "Adj. operating margin" if (is_adj_op and adj_op_margin is not None) else "Operating margin"
                if margin_val is not None:
                    current_val = margin_val
                    target_val = threshold
                    current_label = f"{margin_val:.1f}%"
                    target_label = f"{threshold:.0f}%"
                    progress = _progress_pct(margin_val, threshold)
                    matched = True
                    if margin_val >= threshold:
                        status = "met"
                        note = f"{margin_name} {margin_val:.1f}% meets {threshold:.0f}% target"
                    else:
                        gap = threshold - margin_val
                        note = f"{margin_name} {margin_val:.1f}% — {gap:.1f} ppt below {threshold:.0f}% target"

        # ═══ Share count / dilution ═══
        if not matched and ("share" in cid.lower() or "dilut" in cid.lower()):
            shares = quant_data.get("shares_outstanding_m", None)
            if shares is not None and threshold is not None:
                current_val = shares
                target_val = threshold
                current_label = f"{shares:.0f}M"
                target_label = f"{threshold:.0f}M"
                progress = _progress_pct(shares, threshold, higher_is_better=False)
                matched = True
                if shares <= threshold:
                    status = "met"
                    note = f"Shares {shares:.0f}M within {threshold:.0f}M limit"
                else:
                    over = shares - threshold
                    note = f"Shares {shares:.0f}M — {over:.0f}M above {threshold:.0f}M limit"

        # ═══ SBC dilution ═══
        if not matched and "sbc" in cid.lower():
            sbc_pct = quant_data.get("sbc_pct_of_revenue", None)
            if sbc_pct is not None and threshold is not None:
                current_val = sbc_pct
                target_val = threshold
                current_label = f"{sbc_pct:.1f}%"
                target_label = f"<{threshold:.0f}%"
                progress = _progress_pct(sbc_pct, threshold, higher_is_better=False)
                matched = True
                if sbc_pct < threshold:
                    status = "met"
                    note = f"SBC {sbc_pct:.1f}% of revenue, below {threshold:.0f}% ceiling"
                else:
                    note = f"SBC {sbc_pct:.1f}% of revenue — exceeds {threshold:.0f}% ceiling"

        # ═══ FCF checks ═══
        if not matched and "fcf" in cid.lower():
            fcf = quant_data.get("free_cash_flow_b", None)
            if fcf is not None and threshold is not None:
                current_val = fcf
                target_val = threshold
                current_label = f"${fcf:.1f}B"
                target_label = f"${threshold:.0f}B"
                progress = _progress_pct(fcf, threshold)
                matched = True
                if fcf >= threshold:
                    status = "met"
                    note = f"FCF ${fcf:.1f}B meets ${threshold:.0f}B target"
                else:
                    gap = threshold - fcf
                    note = f"FCF ${fcf:.1f}B — ${gap:.1f}B short of ${threshold:.0f}B target"

        # ═══ Cash runway ═══
        if not matched and "cash_runway" in cid.lower():
            cash = quant_data.get("cash_b", None)
            quarterly_burn = quant_data.get("quarterly_burn_m", None)
            if cash is not None and quarterly_burn is not None and quarterly_burn > 0:
                quarters = (cash * 1000) / quarterly_burn
                current_val = quarters
                target_val = 6
                current_label = f"{quarters:.0f} quarters"
                target_label = "6 quarters (18mo)"
                progress = _progress_pct(quarters, 6)
                matched = True
                if quarters >= 6:
                    status = "met"
                    note = f"Cash runway ~{quarters:.0f} quarters ({cash:.1f}B cash at ${quarterly_burn:.0f}M/qtr burn)"
                else:
                    note = f"Cash runway only ~{quarters:.0f} quarters — need 6+ (${quarterly_burn:.0f}M/qtr burn)"
                    status = "failed"

        # ═══ Backlog checks ═══
        if not matched and "backlog" in cid.lower():
            backlog = quant_data.get("backlog_b", None)
            if backlog is not None and threshold is not None:
                current_val = backlog
                target_val = threshold
                current_label = f"${backlog:.2f}B"
                target_label = f"${threshold:.1f}B"
                progress = _progress_pct(backlog, threshold)
                matched = True
                if backlog >= threshold:
                    status = "met"
                    note = f"Backlog ${backlog:.2f}B meets ${threshold:.1f}B target"
                else:
                    gap = threshold - backlog
                    note = f"Backlog ${backlog:.2f}B — ${gap:.2f}B short of ${threshold:.1f}B target"

        # ═══ PASS 2: Variable-based fallback (when keyword matching didn't fire) ═══
        if not matched and quant_data:
            fb = _variable_fallback(variable, quant_data, threshold, hint)
            if fb[0] is not None:
                current_val, current_label, target_val, target_label, progress, fb_status, note = fb
                if fb_status in ("met", "failed"):
                    status = fb_status
                matched = True

        # ═══ News-based qualitative checks ═══
        if news_data:
            headlines = news_data.get("headlines", []) or news_data.get("articles", [])
            headline_text = " ".join(h.get("title", "") for h in headlines).lower()

            if "faa" in cid.lower():
                if "faa" in headline_text and ("type certificate" in headline_text or "tc granted" in headline_text or "type cert" in headline_text):
                    if "approved" in headline_text or "granted" in headline_text or "received" in headline_text:
                        status = "met"
                        note = "FAA Type Certificate granted per recent news"
                        progress = 100
                elif "faa" in headline_text and ("means of compliance" in headline_text or "moc" in headline_text):
                    note = "100% Means of Compliance accepted — TC pending"
                    progress = progress or 70
                elif "faa" in headline_text and "tia" in headline_text:
                    note = "TIA activities underway — TC progressing"
                    progress = progress or 85

            if "neutron" in cid.lower() and "first" in cid.lower():
                if "neutron" in headline_text:
                    if any(w in headline_text for w in ["success", "complet", "maiden flight", "first flight"]):
                        status = "met"
                        note = "Neutron first flight completed"
                        progress = 100
                    elif "delay" in headline_text or "slip" in headline_text:
                        note = "Neutron timeline slipped per recent news"
                        progress = progress or 40
                    elif any(w in headline_text for w in ["test", "static fire", "stage"]):
                        note = "Neutron testing in progress"
                        progress = progress or 60

            if "commercial_flight" in cid.lower():
                if any(w in headline_text for w in ["commercial flight", "first flight", "passenger flight", "revenue flight"]):
                    if any(w in headline_text for w in ["complet", "success", "launch"]):
                        status = "met"
                        note = "First commercial flight completed"
                        progress = 100

            if "united" in cid.lower():
                if "united" in headline_text and "firm order" in headline_text:
                    status = "met"
                    note = "United Airlines firm order conversion confirmed"
                    progress = 100

        # ═══ Downgrade over-eager auto-"met" for milestone criteria ═══
        # If the criterion describes an EVENT (integration complete, product
        # launched, contract awarded, certification granted), a single quant
        # threshold match is not sufficient evidence — the event also has
        # to have occurred. Keep the quant data as supporting context but
        # roll status back to "not_yet" pending news confirmation.
        milestone_keywords = [
            "integration complete", "integration successful", "launch", "launched",
            "commercial flight", "first flight", "maiden flight",
            "type certificate", "tc granted", "certified", "certification",
            "firm order", "contract award", "awarded", "signed",
            "approved", "approval", "approved by", "granted",
            "acquisition complete", "merger complete", "closed acquisition",
            "ipo", "spin-off", "divestiture complete",
        ]
        label_lc = c.get("label", "").lower()
        is_milestone = any(k in label_lc for k in milestone_keywords)
        if is_milestone and status == "met" and matched and not note.lower().startswith((
            "faa", "neutron", "first commercial flight", "united airlines"
        )):
            # Only downgrade if this "met" came from quant auto-match, not a
            # news-confirmed qualitative match above.
            note = (
                f"Quant threshold met ({current_label}) — but this is a "
                f"milestone criterion; requires news/mgmt confirmation of event."
            )
            status = "not_yet"

        # ═══ Find relevant news for this criterion ═══
        relevant_news = _find_relevant_news(cid, c.get("label", ""), all_news)

        # Default note if nothing matched
        if not note:
            if current_val is None and quant_data:
                note = "Criterion requires qualitative assessment — check earnings call or news"
            elif current_val is None:
                note = "Awaiting data — run pipeline to collect latest metrics"
            else:
                note = f"Currently {current_label}, target {target_label}"

        result["status"] = status
        result["evaluation_note"] = note
        result["progress_pct"] = round(progress, 1) if progress is not None else None
        result["current_value"] = current_val
        result["target_value"] = target_val
        result["current_label"] = current_label
        result["target_label"] = target_label
        result["relevant_news"] = relevant_news
        evaluated.append(result)

    return evaluated


def collect_events_from_signals(signals: list[dict]) -> list[dict]:
    """Pull raw events out of every scout signal that emitted one.

    Today only the News scout emits events (Perplexity structured output),
    but Filings/YouTube/Social can plug into the same shape later. We just
    walk each signal's data.events list — scouts without events contribute
    nothing.
    """
    events: list[dict] = []
    for sig in signals:
        scout = sig.get("scout", "unknown")
        data = sig.get("data") or {}
        raw_events = data.get("events") or []
        for e in raw_events:
            if not isinstance(e, dict):
                continue
            # Stamp which scout detected it if not already present.
            if not e.get("detected_by"):
                e = {**e, "detected_by": scout}
            events.append(e)
    return events


def analyze_stock(ticker: str, name: str, sector: str, signals: list[dict], all_scouts: dict) -> dict:
    """Produce full analysis for a single stock."""

    # ─── Gather factor scores, tracking which are actually available ───
    # Any factor with no underlying data is excluded from the composite and
    # the remaining weights are renormalized. This prevents a missing scout
    # from silently scoring 5 and pulling the composite toward the mean.
    factors: dict[str, float] = {}  # factor_name → score (0-10)

    # ── Quant factor ──
    quant_signal = next((s for s in signals if s.get("scout") == "Quant"), None)
    quant_data = quant_signal.get("data", {}) if quant_signal else {}
    if quant_signal:
        qs = quant_signal.get("scores", {}).get("composite")
        if qs is not None:
            factors["quant_score"] = max(0, min(10, float(qs)))

    # ── Insider factor ──
    # Form-4 transaction count is NOT direction-aware (a burst of sells
    # would be counted the same as buys). Treat it as an "activity" signal,
    # not a bullish one. Only nudge away from neutral when the scout itself
    # judged bullish/bearish with context, or when count is extreme.
    insider_signal = next((s for s in signals if s.get("scout") == "Insider"), None)
    if insider_signal:
        idata = insider_signal.get("data", {}) or {}
        icount = idata.get("transaction_count", 0) or 0
        # Use the scout's own signal direction when available; otherwise stay neutral.
        isig = insider_signal.get("signal", "neutral")
        # Start from neutral 5, nudge up/down based on signal + scaled activity.
        base = 5.0
        if isig == "bullish":
            base = 6.0 + min(2.5, icount * 0.25)  # 6.0 → 8.5 max
        elif isig == "bearish":
            base = 4.0 - min(2.5, icount * 0.25)  # 4.0 → 1.5 min
        else:
            # Neutral/unknown direction — lean slightly toward activity being a positive
            # signal only for very high counts (founder-led companies with heavy activity).
            if icount >= 8:
                base = 5.5
        factors["insider_score"] = max(0, min(10, base))

    # ── News factor ──
    # Prefer fine-grained bull/bear counts from the scout's data when present;
    # fall back to the 3-way signal label otherwise.
    news_signal = next((s for s in signals if s.get("scout") == "News"), None)
    if news_signal:
        ndata = news_signal.get("data", {}) or {}
        bull_n = ndata.get("bull_signals")
        bear_n = ndata.get("bear_signals")
        if bull_n is not None and bear_n is not None and (bull_n + bear_n) > 0:
            # Net signal scaled by volume — caps at ±5 from midpoint
            total_n = bull_n + bear_n
            net = (bull_n - bear_n) / total_n
            # Confidence factor grows with sample size (saturates at ~10 signals)
            conf = min(1.0, total_n / 10.0)
            news_score = 5 + net * 5 * (0.4 + 0.6 * conf)
        else:
            news_sentiment_val = SIGNAL_WEIGHTS.get(news_signal.get("signal", "neutral"), 0)
            news_score = 5 + news_sentiment_val * 3  # -1..1 → 2..8
        factors["news_sentiment"] = max(0, min(10, news_score))

    # ── Convergence (conviction gate — NOT a scoring factor) ──
    # Convergence measures multi-scout agreement. It is NOT included in the
    # composite score because it double-counts the same scouts' signals.
    # Instead, it's surfaced as a conviction label for position-sizing.
    # Only count scouts that actually contribute to the composite score —
    # otherwise YouTube/Social inflate convergence while adding nothing.
    _SCORED_SCOUTS = {"Quant", "Insider", "News", "Fundamentals", "YouTube"}
    scored_signals = [s for s in signals if s.get("scout") in _SCORED_SCOUTS]
    convergence = compute_convergence(scored_signals)

    # ── Momentum factor (derived from quant price data) ──
    # Guard explicit None — 0 is a legitimate value for change_pct/distance_from_high.
    change_pct = quant_data.get("change_pct")
    if change_pct is None:
        change_pct = 0
    distance_from_high = quant_data.get("distance_from_high_pct")
    if distance_from_high is None:
        distance_from_high = 50  # neutral default only when truly missing
    # Only score momentum when we have at least one real data point
    if quant_data.get("price"):
        momentum_score = 5 + change_pct * 0.3 + (50 - distance_from_high) * 0.05
        factors["momentum"] = max(0, min(10, momentum_score))

    # ── YouTube factor ──
    # YouTube scout produces gemini_analysis with sentiment + confidence.
    # Map to a 0-10 score so it actually contributes to composite.
    youtube_signal = next((s for s in signals if s.get("scout") == "YouTube"), None)
    if youtube_signal:
        yt_data = youtube_signal.get("data", {}) or {}
        yt_analysis = yt_data.get("gemini_analysis", {}) or {}
        yt_sentiment = (yt_analysis.get("sentiment") or "").lower()
        yt_confidence = (yt_analysis.get("confidence") or "").lower()
        # Base score from sentiment direction
        yt_base = {"bullish": 7.5, "bearish": 2.5, "neutral": 5.0}.get(yt_sentiment, 5.0)
        # Amplify with confidence
        conf_mult = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(yt_confidence, 0.5)
        yt_score = 5.0 + (yt_base - 5.0) * conf_mult
        factors["youtube"] = max(0, min(10, yt_score))

    # ── Fundamentals factor ──
    # Only contributes if the fundamentals scout actually produced an analysis.
    # Without this guard, every stock missing a fundamentals signal would get
    # a free score of 5, effectively adding 1.0 to the composite.
    fundamentals_signal = get_signals_for_ticker(
        ticker, {"fundamentals": all_scouts.get("fundamentals", {"signals": []})}
    )
    fundamentals_data = {}
    if fundamentals_signal:
        fdata = fundamentals_signal[0].get("data", {}).get("analysis", {})
        if fdata:
            fundamentals_data = fdata
            bq = fdata.get("overall", {}).get("business_quality_score")
            if bq is not None:
                factors["fundamentals"] = float(bq)

    # ─── Composite Score (renormalized over available factors) ───
    # Use adaptive weights when feedback loop has enough data;
    # otherwise fall back to static FACTOR_WEIGHTS.
    active_weights = FACTOR_WEIGHTS
    if _FEEDBACK_LOOP_AVAILABLE:
        try:
            adaptive = get_adaptive_weights(window_days=30)
            if adaptive and adaptive != FACTOR_WEIGHTS:
                active_weights = adaptive
        except Exception as _aw_err:
            print(f"  [analyst] get_adaptive_weights failed: {_aw_err} — using defaults", file=sys.stderr)

    total_weight = sum(active_weights.get(f, 0) for f in factors)
    if total_weight > 0:
        composite_raw = sum(
            factors[f] * active_weights.get(f, 0) for f in factors
        ) / total_weight
    else:
        composite_raw = 5  # no data at all → neutral
    composite = round(max(0, min(10, composite_raw)), 1)

    # Pull scoring fields back out for downstream use / display
    quant_score = factors.get("quant_score", 5)
    insider_score = factors.get("insider_score", 5)
    news_score = factors.get("news_sentiment", 5)
    momentum_score = factors.get("momentum", 5)
    fundamentals_score = factors.get("fundamentals", 5)
    youtube_score = factors.get("youtube", 5)

    # Overall signal
    if composite >= 7:
        overall_signal = "bullish"
    elif composite >= 4:
        overall_signal = "neutral"
    else:
        overall_signal = "bearish"

    # Alerts
    alerts = []
    if convergence["level"] == "strong_bullish":
        alerts.append({"type": "convergence", "message": f"Strong convergence: {convergence['bullish']}/{convergence['total']} scouts bullish"})
    if convergence["level"] in ("strong_bearish", "moderate_bearish"):
        alerts.append({"type": "warning", "message": f"Bearish convergence: {convergence['bearish']}/{convergence['total']} scouts bearish"})
    if quant_data.get("change_pct", 0) > 5:
        alerts.append({"type": "momentum", "message": f"Strong daily move: +{quant_data['change_pct']}%"})
    if quant_data.get("change_pct", 0) < -5:
        alerts.append({"type": "warning", "message": f"Sharp decline: {quant_data['change_pct']}%"})

    # ─── Criteria Evaluation ───
    # Load criteria from watchlist config for this ticker
    watchlist = get_watchlist()
    stock_config = next((w for w in watchlist if w["ticker"] == ticker), None)
    criteria = stock_config.get("criteria", []) if stock_config else []

    # Get news data for qualitative checks
    news_signal_data = news_signal.get("data", {}) if news_signal else {}

    evaluated_criteria = evaluate_criteria(ticker, criteria, quant_data, news_signal_data)

    # Compute criteria confidence score
    WEIGHT_MULTIPLIER = {"critical": 2, "important": 1.5, "monitoring": 1}
    total_weight = sum(WEIGHT_MULTIPLIER.get(c.get("weight", "monitoring"), 1) for c in evaluated_criteria)
    met_weight = sum(WEIGHT_MULTIPLIER.get(c.get("weight", "monitoring"), 1) for c in evaluated_criteria if c.get("status") == "met")
    criteria_confidence = round((met_weight / total_weight * 100) if total_weight > 0 else 0, 1)

    # ─── Base target: engine-first, user-set fallback ───
    # The institutional-grade engine computes a data-driven base target from live
    # financials + forward drivers. If the engine can run, its base-case
    # price becomes the anchor for criteria/event adjustments. If it can't
    # (missing data, EarningsFetchError, import failure), we fall back to
    # the user-set target from stock_config.
    #
    # When both are available and diverge by >50%, we flag it — either the
    # user-set target is stale or the engine has bad inputs (MU-class bug).
    user_set_target = (stock_config.get("target", {}).get("price") or 0) if stock_config else 0
    engine_target = 0
    engine_target_available = False
    engine_target_warnings: list[str] = []

    if _TARGET_ENGINE_AVAILABLE and ticker:
        try:
            _fin = _engine_fetch_financials(ticker)
            _tres = _engine_build_target(_fin)
            engine_target = round(_tres.base)
            engine_target_available = True
            engine_target_warnings = list(_tres.warnings or [])
            if engine_target > 0:
                print(f"  [{ticker}] Engine base target: ${engine_target}")
        except EarningsFetchError as e:
            print(f"  [{ticker}] Engine target skipped (EarningsFetchError): {e}")
        except Exception as e:
            print(f"  [{ticker}] Engine target failed: {e} — falling back to user-set target")

    # Pick the best available anchor
    if engine_target_available and engine_target > 0:
        base_target = engine_target
        base_target_source = "engine"
    else:
        base_target = user_set_target
        base_target_source = "user_set"

    # Divergence guardrail: warn when both exist and differ significantly
    if engine_target > 0 and user_set_target > 0:
        divergence_pct = abs(engine_target - user_set_target) / user_set_target * 100
        if divergence_pct > 50:
            alerts.append({
                "type": "target_divergence",
                "message": (
                    f"Engine target ${engine_target} vs user-set ${user_set_target} "
                    f"({divergence_pct:+.0f}% divergence). Verify inputs or update "
                    f"user target. Engine data warnings: {engine_target_warnings or 'none'}"
                ),
            })
    adjusted_pct = 0
    for c in evaluated_criteria:
        pct = c.get("price_impact_pct") or 0
        direction = c.get("price_impact_direction", "up")
        status = c.get("status")
        if direction == "down_if_failed":
            if status == "failed":
                adjusted_pct -= abs(pct)
            # "not_yet" → no penalty (awaiting evidence)
        else:
            if status == "met":
                adjusted_pct += pct
    adjusted_target = round(base_target * (1 + adjusted_pct / 100))

    # ─── Event impacts (Phase 1: audit-only, NOT merged into adjusted_target) ───
    # Collect raw events from all scouts, run through the reasoner to produce
    # structured impact records with causal chain + expected contribution.
    # Kept side-by-side with criteria_evaluation so we can diff dashboard
    # renderings and sanity-check magnitudes before enabling price-target merge.
    raw_events = collect_events_from_signals(signals)
    thesis_text = ""
    if stock_config:
        thesis_text = (
            stock_config.get("thesis")
            or stock_config.get("description")
            or stock_config.get("why")
            or ""
        )
    stock_context = {
        "ticker": ticker,
        "sector": sector,
        "thesis": thesis_text,
    }

    reasoned_events: list[dict] = []
    event_summary: dict = {
        "event_adjustment_pct": 0.0, "raw_sum_pct": 0.0, "capped": False,
        "event_count": 0, "up_count": 0, "down_count": 0,
    }
    if raw_events and _EVENT_REASONER_AVAILABLE:
        try:
            reasoned_events = reason_events(raw_events, stock_context)
            event_summary = sum_adjustments(reasoned_events)
        except Exception as e:
            print(f"  [event_reasoner] {ticker} failed: {e} — proceeding without event_impacts")

    # ─── Projection-vs-returns spectrum + dynamic event-weight blend ───
    # Compute where this company sits (0.0 mature returns → 1.0 revolutionary
    # projection) using revenue growth, forward PE, user tags, and valuation
    # method. event_weight scales linearly from 0.30 to 1.00 off that score,
    # so revolutionary stories get near-full event flow while mature cash cows
    # damp events down (they're mostly noise for those businesses).
    projection = compute_projection_score(fundamentals_data, quant_data, stock_config or {})
    blend = blend_targets(
        base_target=base_target,
        criteria_pct=adjusted_pct,
        event_pct=event_summary["event_adjustment_pct"],
        projection_score=projection["score"],
    )

    # Legacy audit field: static full-weight blend, kept so the dashboard can
    # diff "what old code would have proposed" vs the new spectrum-aware target.
    proposed_target_with_events = round(
        base_target * (1 + (adjusted_pct + event_summary["event_adjustment_pct"]) / 100)
    )

    # ─── Kill-condition evaluation ───
    # Check whether the stock's thesis-break scenario is approaching or triggered.
    # Uses Claude to compare the plain-English kill condition against current data.
    kill_eval = None
    kill_condition_text = (stock_config.get("kill_condition") or "") if stock_config else ""
    if kill_condition_text and _KILL_EVAL_AVAILABLE:
        news_signal_for_kill = {}
        if news_signal:
            news_signal_for_kill = news_signal.get("data", {})
        kill_eval = evaluate_kill_condition(
            ticker=ticker,
            kill_condition=kill_condition_text,
            quant_data=quant_data,
            signals=signals,
            news_data=news_signal_for_kill,
        )
        # Surface kill-condition warnings/triggers as high-priority alerts
        if kill_eval.get("status") == "triggered":
            alerts.insert(0, {
                "type": "kill_triggered",
                "message": f"THESIS BREAK: {kill_eval['reasoning']}",
            })
            # A triggered kill condition must override the composite-derived
            # signal — a stock can't be "bullish" if its thesis just broke.
            overall_signal = "bearish"
        elif kill_eval.get("status") == "warning":
            alerts.insert(0, {
                "type": "kill_warning",
                "message": f"Kill condition watch: {kill_eval['reasoning']}",
            })
            # Downgrade bullish to neutral on kill warning; leave bearish/neutral alone
            if overall_signal == "bullish":
                overall_signal = "neutral"

    return {
        "ticker": ticker,
        "name": name,
        "sector": sector,
        "overall_signal": overall_signal,
        "composite_score": composite,
        "convergence": convergence,
        "signals": signals,
        "scores": {
            "quant": round(quant_score, 1),
            "convergence": convergence["score"],
            "fundamentals": round(fundamentals_score, 1),
            "insider": round(insider_score, 1),
            "news_sentiment": round(news_score, 1),
            "momentum": round(momentum_score, 1),
            "youtube": round(youtube_score, 1),
        },
        "fundamentals": fundamentals_data,
        "price_data": {
            "price": quant_data.get("price") or 0,
            "change": quant_data.get("change") or 0,
            "change_pct": quant_data.get("change_pct") or 0,
            "market_cap_b": quant_data.get("market_cap_b") or 0,
        },
        "criteria_evaluation": {
            "criteria": evaluated_criteria,
            "confidence_pct": criteria_confidence,
            "base_target": base_target,
            "base_target_source": base_target_source,  # "engine" or "user_set"
            "engine_target": engine_target if engine_target_available else None,
            "user_set_target": user_set_target,
            "adjusted_target": adjusted_target,
            "adjustment_pct": round(adjusted_pct, 1),
            "met_count": sum(1 for c in evaluated_criteria if c.get("status") == "met"),
            "total_count": len(evaluated_criteria),
        },
        "event_impacts": {
            "events": reasoned_events,
            "summary": event_summary,
            # Projection-vs-returns spectrum score with full audit trail:
            # { score, baseline, contributors[], raw_score, final_explanation }
            "projection_score": projection,
            # Dynamic blend of criteria + event adjustments, weighted by
            # projection_score. `blend.final_target` is the spectrum-aware
            # target; `blend.formula` is the human-readable deduction chain
            # rendered on the dashboard.
            "blend": blend,
            # Convenience: the dollar target the blend produces. Downstream
            # code / UI can treat this as the merged target when merge_enabled
            # flips to True. Kept separate from adjusted_target (criteria-only)
            # for now so the deduction chain stays auditable.
            "final_target": blend["final_target"],
            # Phase 3: merge is live. Downstream consumers (dashboards, alerts,
            # rankings) now read final_target (blend of engine base + criteria
            # + event adjustments) as the authoritative price target.
            "merge_enabled": True,
            "proposed_target_with_events": proposed_target_with_events,
            "reasoner_available": _EVENT_REASONER_AVAILABLE,
            "blend_available": _TARGET_BLEND_AVAILABLE,
        },
        "alerts": alerts,
        "kill_condition_eval": kill_eval,
        "timestamp": timestamp(),
    }


def _save_analysis_to_supabase(analysis: list[dict], run_id: str | None, scout_details: dict):
    """Save analysis results to Supabase.

    Resilient to schema drift: if a column the Python side writes hasn't been
    added to the live DB yet (e.g. event_impacts migration not applied), we
    strip that key from the payload and retry rather than silently dropping
    the whole row. This has bitten us once already — a missing event_impacts
    column caused every analyst save to fail, leaving the dashboard stuck on
    stale data.
    """
    try:
        from supabase_helper import get_client
        sb = get_client()
    except Exception:
        return

    if not run_id:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_local"

    rows = []
    for a in analysis:
        rows.append({
            "ticker": a["ticker"],
            "composite_score": a["composite_score"],
            "overall_signal": a["overall_signal"],
            "convergence": a.get("convergence", {}),
            "scores": a.get("scores", {}),
            "alerts": a.get("alerts", []),
            "criteria_eval": a.get("criteria_evaluation", {}),
            "event_impacts": a.get("event_impacts", {}),
            "kill_condition_eval": a.get("kill_condition_eval"),
            "fundamentals": a.get("fundamentals", {}),
            "price_data": a.get("price_data", {}),
            "run_id": run_id,
        })

    import re as _re
    # Retry a few times, each time stripping the unknown column reported by PostgREST
    for attempt in range(5):
        try:
            sb.table("analysis").upsert(rows, on_conflict="ticker,run_id").execute()
            print(f"  [DB] Saved {len(rows)} analysis rows to Supabase (run: {run_id})")
            return
        except Exception as e:
            msg = str(e)
            # PostgREST PGRST204 / Postgres 42703 → column not found
            bad_col = None
            m = _re.search(r"column\s+(?:analysis\.)?['\"]?([a-zA-Z_][a-zA-Z0-9_]*)['\"]?\s+does not exist", msg)
            if not m:
                m = _re.search(r"Could not find the '([a-zA-Z_][a-zA-Z0-9_]*)' column", msg)
            if m:
                bad_col = m.group(1)
            if bad_col and bad_col in rows[0]:
                # Log column name AND sample value so systematic drops are
                # visible (same column dropped repeatedly = unapplied migration).
                sample_val = rows[0].get(bad_col)
                sample_repr = repr(sample_val)[:80] if sample_val is not None else "None"
                print(
                    f"  [DB] WARNING: Column '{bad_col}' missing in DB — stripping "
                    f"from {len(rows)} rows. Sample value lost: {sample_repr}. "
                    f"(Apply migration.sql to persist this field.)",
                    file=sys.stderr,
                )
                for r in rows:
                    r.pop(bad_col, None)
                continue
            # Unknown error — give up
            print(f"  [DB] Failed to save analysis: {e}")
            return
    print(f"  [DB] Failed to save analysis after retries")


def main():
    print("=" * 60)
    print("ANALYST: AGGREGATION & SCORING")
    print("=" * 60)

    # Load all scout data
    print("\nLoading scout data...")
    all_scouts = load_all_scout_data()

    if not all_scouts:
        print("  ❌ No scout data found! Run scouts first.")
        return

    # Load watchlist
    watchlist = get_watchlist()
    print(f"\nAnalyzing {len(watchlist)} stocks...")
    print("-" * 60)

    run_id = get_run_id()

    analysis = []
    for stock in watchlist:
        ticker = stock["ticker"]
        name = stock["name"]
        sector = stock.get("sector", "Unknown")

        try:
            print(f"\n  Analyzing {ticker} ({name})...")
            signals = get_signals_for_ticker(ticker, all_scouts)
            print(f"  Found {len(signals)} signals from {len(set(s.get('scout','') for s in signals))} scouts")

            result = analyze_stock(ticker, name, sector, signals, all_scouts)
            analysis.append(result)

            score = result["composite_score"]
            sig = result["overall_signal"]
            conv = result["convergence"]
            emoji = "🟢" if sig == "bullish" else ("🔴" if sig == "bearish" else "🟡")
            print(f"  {emoji} Score: {score}/10 | Signal: {sig} | Convergence: {conv['bullish']}/{conv['total']} bullish")

            for alert in result["alerts"]:
                alert_emoji = "🚨" if alert["type"] == "warning" else "📡"
                print(f"  {alert_emoji} {alert['message']}")

            # Print criteria evaluation
            crit_eval = result.get("criteria_evaluation", {})
            if crit_eval.get("total_count", 0) > 0:
                met = crit_eval["met_count"]
                total = crit_eval["total_count"]
                conf = crit_eval["confidence_pct"]
                adj_target = crit_eval["adjusted_target"]
                base_target = crit_eval["base_target"]
                adj_pct = crit_eval["adjustment_pct"]
                src = crit_eval.get("base_target_source", "user_set")
                src_tag = "⚙️engine" if src == "engine" else "📌user-set"
                print(f"  📋 Criteria: {met}/{total} met | Confidence: {conf:.0f}% | Target ({src_tag}): ${base_target} → ${adj_target} ({adj_pct:+.1f}%)")

            # Print event impacts if any were surfaced
            ev_impacts = result.get("event_impacts", {})
            ev_summary = ev_impacts.get("summary", {}) or {}
            ev_count = ev_summary.get("event_count", 0)
            if ev_count > 0:
                ev_adj = ev_summary.get("event_adjustment_pct", 0.0)
                ups = ev_summary.get("up_count", 0)
                downs = ev_summary.get("down_count", 0)
                proposed = ev_impacts.get("proposed_target_with_events", 0)
                print(
                    f"  📰 Events: {ev_count} ({ups}↑ / {downs}↓) | "
                    f"Audit adj: {ev_adj:+.1f}% | Proposed target w/events: ${proposed} "
                    f"(not merged in Phase 1)"
                )

            # Save each stock's analysis immediately — don't wait for the whole batch.
            # This way, if a later stock crashes, previously analyzed stocks are still saved.
            _save_analysis_to_supabase([result], run_id, {})
        except Exception as e:
            print(f"  [FAIL] {ticker} analysis error: {e}")
            import traceback
            traceback.print_exc()

    # Sort by composite score
    analysis.sort(key=lambda x: x["composite_score"], reverse=True)

    # Save complete scout details (for metadata)
    scout_details = {
        name: {
            "signal_count": len(data.get("signals", [])),
            "generated_at": data.get("generated_at", ""),
        }
        for name, data in all_scouts.items()
    }

    # Also save JSON for backward compat
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stock_count": len(analysis),
        "scouts_active": list(all_scouts.keys()),
        "scout_details": scout_details,
        "analysis": analysis,
    }

    output_path = DATA_DIR / "analysis.json"
    output_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n[Analyst] Saved analysis to {output_path}")

    # Summary table
    print("\n" + "=" * 60)
    print("FINAL RANKINGS")
    print("=" * 60)
    print(f"  {'Rank':<5} {'Ticker':<7} {'Score':<7} {'Signal':<10} {'Convergence':<15} {'Price':<10}")
    print("  " + "-" * 55)
    for i, a in enumerate(analysis, 1):
        emoji = "🟢" if a["overall_signal"] == "bullish" else ("🔴" if a["overall_signal"] == "bearish" else "🟡")
        conv = f"{a['convergence']['bullish']}/{a['convergence']['total']} bull"
        price = f"${a['price_data']['price']:.2f}" if a['price_data']['price'] else "N/A"
        print(f"  {emoji} #{i:<3} {a['ticker']:<7} {a['composite_score']:<7.1f} {a['overall_signal']:<10} {conv:<15} {price}")

    return analysis


if __name__ == "__main__":
    main()
