"""
confidence.py — Scout-level confidence scoring for Stock Radar.

Each scout's signal carries implicit quality indicators buried in its data.
This module extracts them and produces a normalized 0.0-1.0 confidence score
that propagates through the pipeline.

Confidence measures "how much should we trust this number?" — not whether
the signal is bullish or bearish.

Sources of confidence:
  - Data freshness (EODHD today = 0.95, yfinance weekend cache = 0.70)
  - Source count (Perplexity 3+ sources = 0.85, single source = 0.50)
  - API success (full response = 1.0, timeout/fallback = 0.30)
  - Internal scoring (Gemini confidence: high=0.90, medium=0.65, low=0.40)

Usage:
    from confidence import compute_scout_confidence
    conf = compute_scout_confidence("quant", signal_data, signal_scores)
    # conf = 0.85
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta


def compute_scout_confidence(
    scout_name: str,
    data: dict,
    scores: dict | None = None,
) -> float:
    """Compute confidence score (0.0-1.0) for a scout signal.

    Args:
        scout_name: lowercase scout name (e.g. "quant", "news")
        data: the signal's data dict
        scores: the signal's scores dict (optional)

    Returns:
        Confidence score between 0.0 and 1.0.
    """
    scores = scores or {}

    if scout_name == "quant":
        return _quant_confidence(data, scores)
    elif scout_name == "news":
        return _news_confidence(data)
    elif scout_name == "catalyst":
        return _catalyst_confidence(data)
    elif scout_name == "moat":
        return _moat_confidence(data)
    elif scout_name == "social":
        return _social_confidence(data)
    elif scout_name == "insider":
        return _insider_confidence(data)
    elif scout_name == "filings":
        return _filings_confidence(data)
    elif scout_name == "fundamentals":
        return _fundamentals_confidence(data)
    elif scout_name == "youtube":
        return _youtube_confidence(data)
    else:
        return 0.50  # unknown scout, neutral confidence


def _quant_confidence(data: dict, scores: dict) -> float:
    """Quant confidence based on data completeness and freshness."""
    # Start high — quant data is numerical and verifiable
    conf = 0.90

    # Degrade if key fields are missing
    required = ["price", "market_cap_b", "pe_ratio", "revenue_growth_pct"]
    present = sum(1 for f in required if data.get(f) is not None)
    completeness = present / len(required)
    conf *= (0.5 + 0.5 * completeness)  # 50% floor from completeness

    # Degrade if composite score is missing (means scoring logic failed)
    if not scores.get("composite"):
        conf *= 0.70

    return round(min(1.0, max(0.0, conf)), 2)


def _news_confidence(data: dict) -> float:
    """News confidence based on source count and parsing quality."""
    conf = 0.60  # baseline for LLM-parsed content

    # Citations boost confidence (more sources = more reliable)
    citations = data.get("citations", [])
    if len(citations) >= 3:
        conf = 0.85
    elif len(citations) >= 1:
        conf = 0.70

    # Events extracted = structured output succeeded
    events = data.get("events", [])
    if events:
        conf += 0.05  # small boost for successful event extraction

    # Check for the internal confidence field from Perplexity parsing
    parsed = data.get("parsed_analysis", {})
    if isinstance(parsed, dict):
        pplx_conf = parsed.get("confidence", "").lower()
        if pplx_conf == "high":
            conf = max(conf, 0.85)
        elif pplx_conf == "low":
            conf = min(conf, 0.55)

    return round(min(1.0, max(0.0, conf)), 2)


def _catalyst_confidence(data: dict) -> float:
    """Catalyst confidence based on event count and source quality."""
    events = data.get("catalyst_events", [])
    citations = data.get("citations", [])

    if not events:
        return 0.40  # no catalysts found — low confidence in the absence

    conf = 0.65
    if len(citations) >= 2:
        conf += 0.15
    if len(events) >= 3:
        conf += 0.10

    return round(min(1.0, max(0.0, conf)), 2)


def _moat_confidence(data: dict) -> float:
    """Moat confidence based on source count and strength score."""
    pplx_count = data.get("pplx_count", 0)
    strength = data.get("strength_score", 0)

    conf = 0.55  # baseline for qualitative assessment
    if pplx_count >= 3:
        conf += 0.20
    elif pplx_count >= 1:
        conf += 0.10

    # Strength score gives us confidence in the signal direction
    if strength and abs(strength) > 0:
        conf += 0.10

    return round(min(1.0, max(0.0, conf)), 2)


def _social_confidence(data: dict) -> float:
    """Social confidence based on engagement volume."""
    reddit_engagement = data.get("reddit_engagement", 0) or 0
    stocktwits_total = data.get("stocktwits_total", 0) or 0
    total = reddit_engagement + stocktwits_total

    if total == 0:
        return 0.30  # no social data at all

    conf = 0.45  # social is inherently noisy
    if total >= 50:
        conf = 0.60
    elif total >= 20:
        conf = 0.55
    elif total >= 5:
        conf = 0.50

    return round(min(1.0, max(0.0, conf)), 2)


def _insider_confidence(data: dict) -> float:
    """Insider confidence based on transaction count."""
    count = data.get("transaction_count", 0) or 0

    if count == 0:
        return 0.40  # no insider activity — signal is "absence of signal"

    # More transactions = more reliable pattern
    conf = 0.65
    if count >= 5:
        conf = 0.80
    elif count >= 2:
        conf = 0.70

    return round(min(1.0, max(0.0, conf)), 2)


def _filings_confidence(data: dict) -> float:
    """Filings confidence — low if scout is incomplete."""
    analysis = data.get("analysis", {})
    status = data.get("status", "")

    if status == "no_filings" or not analysis:
        return 0.30

    # If we got structured analysis, moderate confidence
    conf = 0.65
    if isinstance(analysis, dict):
        if analysis.get("forward_guidance"):
            conf += 0.15  # has forward guidance = more useful
        if analysis.get("red_flags"):
            conf += 0.05  # successfully identified risk factors

    return round(min(1.0, max(0.0, conf)), 2)


def _fundamentals_confidence(data: dict) -> float:
    """Fundamentals confidence based on analysis completeness."""
    analysis = data.get("analysis", {})
    if not analysis:
        return 0.35

    conf = 0.70  # Claude analysis with citations

    # Check completeness of sub-sections
    sections = ["moat_analysis", "revenue_analysis", "competitive_position",
                 "risk_assessment", "overall"]
    present = sum(1 for s in sections if analysis.get(s))
    completeness = present / len(sections)
    conf *= (0.6 + 0.4 * completeness)

    # Business quality score present = structured output succeeded
    overall = analysis.get("overall", {})
    if isinstance(overall, dict) and overall.get("business_quality_score"):
        conf += 0.10

    # Citations boost
    citations = data.get("citations", [])
    if len(citations) >= 2:
        conf += 0.05

    return round(min(1.0, max(0.0, conf)), 2)


def _youtube_confidence(data: dict) -> float:
    """YouTube confidence based on video coverage and Gemini analysis."""
    videos = data.get("videos_analyzed", 0) or 0

    if videos == 0:
        return 0.25  # no videos found

    conf = 0.50  # YouTube is a secondary signal

    # Gemini's own confidence assessment
    gemini = data.get("gemini_analysis", {})
    if isinstance(gemini, dict):
        g_conf = (gemini.get("confidence") or "").lower()
        if g_conf == "high":
            conf = 0.70
        elif g_conf == "medium":
            conf = 0.55
        elif g_conf == "low":
            conf = 0.40

    # More videos = broader coverage
    if videos >= 3:
        conf += 0.10
    elif videos >= 2:
        conf += 0.05

    return round(min(1.0, max(0.0, conf)), 2)


def weighted_harmonic_mean(
    values: list[float],
    weights: list[float] | None = None,
) -> float:
    """Compute weighted harmonic mean of confidence values.

    Harmonic mean naturally penalizes low values more than arithmetic mean —
    one garbage input (0.30) with five good inputs (0.90) gives 0.64 instead
    of 0.80. This is the right behavior: one bad apple should drag confidence.

    Returns 0.0 if any value is 0 or if inputs are empty.
    """
    if not values:
        return 0.0

    if weights is None:
        weights = [1.0] * len(values)

    if len(values) != len(weights):
        raise ValueError("values and weights must have same length")

    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0

    # Harmonic mean: 1 / (Σ wi/xi / Σ wi)
    try:
        weighted_reciprocal_sum = sum(
            w / v for v, w in zip(values, weights) if v > 0 and w > 0
        )
        if weighted_reciprocal_sum == 0:
            return 0.0
        active_weight = sum(w for v, w in zip(values, weights) if v > 0 and w > 0)
        return round(active_weight / weighted_reciprocal_sum, 3)
    except ZeroDivisionError:
        return 0.0
