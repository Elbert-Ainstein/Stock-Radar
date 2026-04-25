"""
Single-source-of-truth registries for the Stock Radar pipeline.

ALL scout names, valuation methods, archetypes, and lifecycle stages are
defined here.  Every Python module that needs these constants MUST import
from this file — never re-define the lists locally.

TypeScript mirror: lib/registries.ts
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────────
# SCOUTS
# ──────────────────────────────────────────────────────────────────────────────

# Canonical ordered list of all scouts known to the pipeline.
ALL_SCOUTS: list[str] = [
    "quant",
    "insider",
    "social",
    "news",
    "catalyst",
    "moat",
    "fundamentals",
    "filings",
    "youtube",
]

# Scouts that run without any paid API key.
FREE_SCOUTS: list[str] = ["quant", "insider", "social", "filings"]

# Scouts that require a paid API key (the complement of FREE_SCOUTS).
PAID_SCOUTS: list[str] = [s for s in ALL_SCOUTS if s not in FREE_SCOUTS]

# Map scout names to their importable module names.
SCOUT_MODULE_MAP: dict[str, str] = {s: f"scout_{s}" for s in ALL_SCOUTS}

# Display labels for scout names (used in analyst bucketing & logs).
SCOUT_DISPLAY_NAMES: dict[str, str] = {
    "quant": "Quant",
    "insider": "Insider",
    "news": "News",
    "social": "Social",
    "youtube": "YouTube",
    "fundamentals": "Fundamentals",
    "catalyst": "Catalyst",
    "moat": "Moat",
    "filings": "Filings",
}

# Scout refresh cadence (hours).  Controls how long a signal stays "fresh"
# before the scout will re-scan that stock.  Driven by how quickly each
# signal type decays:
#   Tier 1 (daily)     — data changes intra-day (prices, news, sentiment)
#   Tier 2 (periodic)  — data shifts over days (catalysts, fundamentals, moat)
#   Tier 3 (slow)      — on-demand / weekly (YouTube, filings)
SCOUT_CADENCE_HOURS: dict[str, int] = {
    # Tier 1 — daily
    "quant":        12,   # prices change every session
    "news":         18,   # breaking news = fast signal shift
    "social":       20,   # Reddit/StockTwits churn daily
    "insider":      20,   # SEC Form 4 filings posted nightly

    # Tier 2 — every 2-3 days
    "catalyst":     48,   # upcoming events shift slowly
    "fundamentals": 48,   # quarterly data, rarely changes between earnings
    "moat":         48,   # competitive position evolves over weeks

    # Tier 3 — weekly / on-demand
    "youtube":      168,  # 7 days — slowest scout, lowest hit rate
    "filings":      168,  # earnings-triggered, not daily
}

# Which API key each paid scout requires (key name in .env).
SCOUT_API_KEYS: dict[str, str] = {
    "news": "PERPLEXITY_API_KEY",
    "catalyst": "PERPLEXITY_API_KEY",
    "moat": "PERPLEXITY_API_KEY",
    "fundamentals": "ANTHROPIC_API_KEY",
    "youtube": "GEMINI_API_KEY",
}

# Scouts that directly map to analyst score fields.
SCORE_SCOUTS: dict[str, str] = {
    "quant": "quant_score",
    "insider": "insider_activity",
    "news": "news_sentiment",
    "fundamentals": "fundamentals",
}

# Scouts that contribute to the convergence factor.
CONVERGENCE_SCOUTS: list[str] = ["social", "youtube", "catalyst", "filings", "moat"]

# ──────────────────────────────────────────────────────────────────────────────
# ARCHETYPES
# ──────────────────────────────────────────────────────────────────────────────

ALL_ARCHETYPES: list[str] = [
    "garp",
    "cyclical",
    "transformational",
    "compounder",
    "special_situation",
]

# Archetype-specific forecast horizons (years of explicit DCF projection).
ARCHETYPE_FORECAST_YEARS: dict[str, int] = {
    "garp": 5,
    "special_situation": 5,
    "transformational": 7,
    "cyclical": 8,
    "compounder": 10,
}

# Which year to use as the valuation/exit point.
ARCHETYPE_VALUATION_YEAR: dict[str, int] = {
    "garp": 3,
    "special_situation": 3,
    "transformational": 4,
    "cyclical": 5,
    "compounder": 5,
}

# Margin ramp target year (how long until margins stabilize).
ARCHETYPE_MARGIN_RAMP: dict[str, int] = {
    "garp": 3,
    "special_situation": 3,
    "transformational": 4,
    "cyclical": 5,
    "compounder": 5,
}

# Scout priority by archetype: which scouts are essential, recommended, or optional.
ARCHETYPE_SCOUT_PRIORITY: dict[str, dict[str, list[str]]] = {
    "garp": {
        "always": ["quant", "fundamentals", "news", "catalyst"],
        "recommended": ["moat", "insider", "filings"],
        "optional": ["youtube", "social"],
    },
    "cyclical": {
        "always": ["quant", "fundamentals", "news"],
        "recommended": ["catalyst", "insider", "filings"],
        "optional": ["moat", "youtube", "social"],
    },
    "compounder": {
        "always": ["quant", "fundamentals", "moat"],
        "recommended": ["news", "filings", "insider"],
        "optional": ["catalyst", "youtube", "social"],
    },
    "transformational": {
        "always": ["quant", "fundamentals", "news", "catalyst", "social"],
        "recommended": ["moat", "youtube"],
        "optional": ["insider", "filings"],
    },
    "special_situation": {
        "always": ["quant", "news", "catalyst", "filings", "insider"],
        "recommended": ["fundamentals"],
        "optional": ["moat", "youtube", "social"],
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# VALUATION METHODS
# ──────────────────────────────────────────────────────────────────────────────

# Methods the LLM can select (pipeline input).
LLM_VALUATION_METHODS: list[str] = ["pe", "ps"]

# All methods including engine-derived ones (cyclical is inferred from archetype).
ALL_VALUATION_METHODS: list[str] = ["pe", "ps", "cyclical"]

# ──────────────────────────────────────────────────────────────────────────────
# LIFECYCLE STAGES
# ──────────────────────────────────────────────────────────────────────────────

ALL_LIFECYCLE_STAGES: list[str] = [
    "startup",
    "high_growth",
    "mature_growth",
    "mature_stable",
    "decline",
]

ALL_MOAT_WIDTHS: list[str] = ["none", "narrow", "wide"]

# ──────────────────────────────────────────────────────────────────────────────
# CIRCUIT BREAKER THRESHOLDS (rigid container, values may evolve)
# ──────────────────────────────────────────────────────────────────────────────

# Minimum scouts required before analyst score is considered HIGH confidence.
MIN_SCOUTS_HIGH_CONFIDENCE = 4

# Sigma threshold for inter-scout disagreement on the same metric.
DISAGREEMENT_SIGMA = 3.0

# Maximum composite score swing between consecutive runs before flagging REGIME_CHANGE.
MAX_COMPOSITE_SWING = 2.0

# Maximum target price change (fraction) between runs before flagging.
MAX_TARGET_CHANGE_FRAC = 0.30

# Maximum allowed target-to-price ratio (extreme prediction warning).
MAX_TARGET_PRICE_RATIO = 3.0
