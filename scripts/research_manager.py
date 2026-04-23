"""
research_manager.py — Rule-based research orchestration layer.

Provides intelligent scout routing based on stock archetypes, signal conflict
detection, and research sufficiency checking.  This is a pure rule-based system
— no LLM calls are made for orchestration decisions.

Usage from run_pipeline.py:
    from research_manager import plan_research, detect_conflicts, check_sufficiency
    plan = plan_research(ticker, archetype={"primary": "garp", ...}, mode="smart")
    # ... run plan.scouts_to_run ...
    conflicts = detect_conflicts(scout_results)
    sufficiency = check_sufficiency("garp", scout_results)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Scout priority matrix: archetype -> {always, recommended, optional}
# ---------------------------------------------------------------------------

SCOUT_PRIORITY: dict[str, dict[str, list[str]]] = {
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

# Complete set of all scouts known to the pipeline.
ALL_SCOUTS = [
    "quant", "news", "catalyst", "moat", "social",
    "insider", "filings", "fundamentals", "youtube",
]

# Map scout names to their importable module names.
SCOUT_MODULE_MAP: dict[str, str] = {
    "quant": "scout_quant",
    "news": "scout_news",
    "catalyst": "scout_catalyst",
    "moat": "scout_moat",
    "social": "scout_social",
    "insider": "scout_insider",
    "filings": "scout_filings",
    "fundamentals": "scout_fundamentals",
    "youtube": "scout_youtube",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ConflictReport:
    """A detected conflict between scout signals."""
    scouts_involved: list[str]
    description: str
    severity: str  # "warning" or "critical"
    suggested_action: str


@dataclass
class SufficiencyReport:
    """Whether the research coverage is sufficient for the given archetype."""
    sufficient: bool
    missing_critical: list[str]
    missing_recommended: list[str]
    coverage_score: float  # 0.0 – 1.0


@dataclass
class ResearchPlan:
    """The output of plan_research() — tells the pipeline what to run."""
    ticker: str
    archetype_primary: str | None
    scouts_to_run: list[str]
    mode: str
    rationale: str


# ---------------------------------------------------------------------------
# Scout selection
# ---------------------------------------------------------------------------

def select_scouts(archetype: str | None, mode: str = "full") -> list[str]:
    """Return the list of scouts to run for *archetype* under *mode*.

    Modes:
        full  — always + recommended + optional (all scouts, same as current)
        smart — always + recommended (skip optionals, saves API calls)
        fast  — always only (minimum viable signal set)

    If *archetype* is ``None`` or not found in SCOUT_PRIORITY the function
    falls back to returning ALL_SCOUTS (backwards compatible).
    """
    if archetype is None or archetype not in SCOUT_PRIORITY:
        return list(ALL_SCOUTS)

    tiers = SCOUT_PRIORITY[archetype]

    if mode == "fast":
        return list(tiers["always"])
    elif mode == "smart":
        return list(tiers["always"]) + list(tiers["recommended"])
    else:  # "full" or unknown mode
        return list(tiers["always"]) + list(tiers["recommended"]) + list(tiers["optional"])


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def _extract_scout_result(scout_results: dict, scout_name: str) -> tuple[bool, dict]:
    """Return (succeeded, result_tuple) for a scout from the results dict.

    scout_results values are expected to be tuples of (name, success, error_or_none).
    """
    if scout_name not in scout_results:
        return False, {}
    entry = scout_results[scout_name]
    if isinstance(entry, tuple) and len(entry) >= 2:
        return entry[1], {}
    return False, {}


def detect_conflicts(scout_results: dict) -> list[ConflictReport]:
    """Analyze completed scout results for signal conflicts.

    This inspects which scouts succeeded/failed and applies heuristic patterns.
    Because detailed signal payloads are stored in Supabase (not returned from
    scout main()), the first-pass detection here is intentionally conservative
    — it flags based on scout success/failure patterns rather than deep payload
    inspection.  Future iterations can query Supabase for richer analysis.

    Parameters
    ----------
    scout_results : dict
        Mapping of scout_name -> (name, success: bool, error_msg | None).
    """
    conflicts: list[ConflictReport] = []

    # Helper: did a scout succeed?
    def ok(name: str) -> bool:
        if name not in scout_results:
            return False
        entry = scout_results[name]
        return isinstance(entry, tuple) and len(entry) >= 2 and entry[1]

    # --- Pattern: moat_vs_insider ---
    # Both completed — flag if results may conflict (informational).
    if ok("moat") and ok("insider"):
        conflicts.append(ConflictReport(
            scouts_involved=["moat", "insider"],
            description=(
                "Both moat and insider scouts completed. Review for divergence: "
                "a strong-moat signal combined with heavy insider selling may "
                "indicate hidden risk."
            ),
            severity="warning",
            suggested_action="Compare moat durability score with insider net transaction direction in the analyst summary.",
        ))

    # --- Pattern: sentiment_divergence ---
    # Social/youtube positive vs news/catalyst negative (or vice versa).
    social_ran = ok("social") or ok("youtube")
    news_ran = ok("news") or ok("catalyst")
    if social_ran and news_ran:
        conflicts.append(ConflictReport(
            scouts_involved=["social", "youtube", "news", "catalyst"],
            description=(
                "Both sentiment (social/youtube) and news/catalyst scouts completed. "
                "Check for sentiment divergence: retail enthusiasm with negative "
                "institutional news flow can precede corrections."
            ),
            severity="warning",
            suggested_action="Cross-reference social sentiment direction with news tone in the analyst composite.",
        ))

    # --- Pattern: growth_vs_valuation ---
    if ok("quant") and ok("fundamentals"):
        conflicts.append(ConflictReport(
            scouts_involved=["quant", "fundamentals"],
            description=(
                "Both quant and fundamentals scouts completed. Watch for "
                "growth-vs-valuation tension: high revenue growth paired with "
                "elevated P/E and low growth-adjusted return may signal overvaluation."
            ),
            severity="warning",
            suggested_action="Check quant valuation metrics against fundamentals growth rates in the analyst output.",
        ))

    return conflicts


# ---------------------------------------------------------------------------
# Sufficiency checking
# ---------------------------------------------------------------------------

def check_sufficiency(archetype: str | None, scout_results: dict) -> SufficiencyReport:
    """Check whether enough scouts succeeded for the given archetype.

    Parameters
    ----------
    archetype : str | None
        The stock's primary archetype.  ``None`` / unknown uses all scouts as
        the expected set.
    scout_results : dict
        Mapping of scout_name -> (name, success: bool, error_msg | None).

    Returns
    -------
    SufficiencyReport
    """
    def ok(name: str) -> bool:
        if name not in scout_results:
            return False
        entry = scout_results[name]
        return isinstance(entry, tuple) and len(entry) >= 2 and entry[1]

    if archetype is None or archetype not in SCOUT_PRIORITY:
        # Unknown archetype — treat all scouts as equally important.
        ran = [s for s in ALL_SCOUTS if ok(s)]
        missing = [s for s in ALL_SCOUTS if not ok(s)]
        score = len(ran) / len(ALL_SCOUTS) if ALL_SCOUTS else 1.0
        return SufficiencyReport(
            sufficient=len(missing) == 0,
            missing_critical=missing,
            missing_recommended=[],
            coverage_score=round(score, 2),
        )

    tiers = SCOUT_PRIORITY[archetype]
    always = tiers["always"]
    recommended = tiers["recommended"]
    optional = tiers.get("optional", [])

    missing_critical = [s for s in always if not ok(s)]
    missing_recommended = [s for s in recommended if not ok(s)]

    total_expected = len(always) + len(recommended) + len(optional)
    total_ok = sum(1 for s in always + recommended + optional if ok(s))
    score = total_ok / total_expected if total_expected else 1.0

    return SufficiencyReport(
        sufficient=len(missing_critical) == 0,
        missing_critical=missing_critical,
        missing_recommended=missing_recommended,
        coverage_score=round(score, 2),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def plan_research(
    ticker: str,
    archetype: dict[str, Any] | None = None,
    mode: str = "full",
) -> ResearchPlan:
    """Build a research plan for *ticker*.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol.
    archetype : dict | None
        Archetype dict from Supabase (``stocks.archetype`` jsonb).  Expected
        keys: ``primary``, ``secondary``, ``justification``.  If ``None`` the
        plan falls back to running all scouts.
    mode : str
        One of ``"full"``, ``"smart"``, ``"fast"``.

    Returns
    -------
    ResearchPlan
    """
    primary = None
    if archetype and isinstance(archetype, dict):
        primary = archetype.get("primary")

    scouts = select_scouts(primary, mode=mode)

    # Build human-readable rationale
    if primary and primary in SCOUT_PRIORITY:
        tier_label = {"full": "all tiers", "smart": "always + recommended", "fast": "always only"}
        rationale = (
            f"Archetype '{primary}' detected for {ticker}. "
            f"Mode '{mode}' selects {tier_label.get(mode, mode)}: "
            f"{', '.join(scouts)} ({len(scouts)} scouts)."
        )
    else:
        rationale = (
            f"No recognized archetype for {ticker}. "
            f"Falling back to all {len(scouts)} scouts (backwards-compatible)."
        )

    return ResearchPlan(
        ticker=ticker,
        archetype_primary=primary,
        scouts_to_run=scouts,
        mode=mode,
        rationale=rationale,
    )


def print_conflict_warnings(conflicts: list[ConflictReport]) -> None:
    """Pretty-print conflict reports to the terminal."""
    if not conflicts:
        return
    print(f"\n  SIGNAL CONFLICT CHECKS ({len(conflicts)} patterns flagged):")
    for c in conflicts:
        icon = "!!" if c.severity == "critical" else "?"
        print(f"    [{icon}] {c.severity.upper()}: {c.description}")
        print(f"        Action: {c.suggested_action}")


def print_sufficiency_report(report: SufficiencyReport, archetype: str | None) -> None:
    """Pretty-print a sufficiency report to the terminal."""
    label = archetype or "unknown"
    status = "SUFFICIENT" if report.sufficient else "INSUFFICIENT"
    print(f"\n  RESEARCH SUFFICIENCY [{label}]: {status} (coverage {report.coverage_score:.0%})")
    if report.missing_critical:
        print(f"    MISSING CRITICAL scouts: {', '.join(report.missing_critical)}")
    if report.missing_recommended:
        print(f"    Missing recommended scouts: {', '.join(report.missing_recommended)}")
