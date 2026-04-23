#!/usr/bin/env python3
"""
Event taxonomy and baseline impact templates.

The taxonomy is the canonical list of event types the system recognizes.
Each type has a baseline (min, max) magnitude range, baseline confidence,
and a typical time horizon. These anchor the LLM reasoner — the reasoner
picks a value within the range with a justification, rather than inventing
a number from scratch.

Baselines are calibrated from empirical event-study literature:
  - M&A target CARs: +15-30% (3-day window)
  - Top-decile earnings surprises: +3-5%
  - FDA approvals (small biotech): +15-40%
  - Refer to docs/event_target_plan.md §4 for full derivation
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Direction = Literal["up", "down"]


@dataclass
class EventTemplate:
    """Baseline impact profile for one event type."""
    type_id: str
    display_name: str
    direction: Direction
    magnitude_min_pct: float  # lower bound of expected target Δ
    magnitude_max_pct: float  # upper bound
    baseline_confidence: float  # 0-1, used as prior; reasoner may adjust
    typical_horizon_months: int
    notes: str

    @property
    def midpoint_pct(self) -> float:
        return (self.magnitude_min_pct + self.magnitude_max_pct) / 2.0

    @property
    def signed_magnitude_range(self) -> tuple[float, float]:
        """Return (lo, hi) with sign applied according to direction.

        For "up" events:  (min, max)   e.g. (+5, +15)
        For "down" events: (-max, -min) e.g. (-15, -5)

        lo is always ≤ hi so that clamp(lo, hi, x) works correctly.
        """
        lo_unsigned = min(self.magnitude_min_pct, self.magnitude_max_pct)
        hi_unsigned = max(self.magnitude_min_pct, self.magnitude_max_pct)
        if self.direction == "up":
            return (lo_unsigned, hi_unsigned)
        else:
            return (-hi_unsigned, -lo_unsigned)


# ─── Taxonomy v1 ───
# Keep narrow at launch (21 types). Expand as gaps appear in real data.
EVENT_TEMPLATES: dict[str, EventTemplate] = {
    # ═══ M&A ═══
    "ma_target": EventTemplate(
        type_id="ma_target",
        display_name="Acquisition target announced",
        direction="up",
        magnitude_min_pct=15.0, magnitude_max_pct=35.0,
        baseline_confidence=0.85, typical_horizon_months=4,
        notes="Premium usually ~20-30% to undisturbed price; deal-close risk caps upside.",
    ),
    "ma_acquirer": EventTemplate(
        type_id="ma_acquirer",
        display_name="Acquisition announced (as acquirer)",
        direction="up",  # can be down; reasoner overrides based on synergy read
        magnitude_min_pct=-5.0, magnitude_max_pct=5.0,
        baseline_confidence=0.55, typical_horizon_months=12,
        notes="Directional per synergy quality; sign flips on dilutive / overpriced deals.",
    ),

    # ═══ Regulatory ═══
    "regulatory_approval": EventTemplate(
        type_id="regulatory_approval",
        display_name="Regulatory approval granted",
        direction="up",
        magnitude_min_pct=8.0, magnitude_max_pct=25.0,
        baseline_confidence=0.90, typical_horizon_months=0,
        notes="FDA, FAA TC, CE mark, antitrust clearance. Immediate; magnitude scales with addressable revenue unlocked.",
    ),
    "regulatory_rejection": EventTemplate(
        type_id="regulatory_rejection",
        display_name="Regulatory rejection / adverse ruling",
        direction="down",
        magnitude_min_pct=10.0, magnitude_max_pct=40.0,
        baseline_confidence=0.90, typical_horizon_months=0,
        notes="Often catastrophic for single-asset biotech / aviation. Scale with revenue dependency.",
    ),

    # ═══ Earnings ═══
    "earnings_beat_raise": EventTemplate(
        type_id="earnings_beat_raise",
        display_name="Earnings beat + guidance raise",
        direction="up",
        magnitude_min_pct=3.0, magnitude_max_pct=10.0,
        baseline_confidence=0.80, typical_horizon_months=6,
        notes="Top decile surprise. Pair of beat + raise > either alone.",
    ),
    "earnings_miss_cut": EventTemplate(
        type_id="earnings_miss_cut",
        display_name="Earnings miss + guidance cut",
        direction="down",
        magnitude_min_pct=5.0, magnitude_max_pct=15.0,
        baseline_confidence=0.80, typical_horizon_months=6,
        notes="Guide-cut is the larger signal; miss alone lands milder.",
    ),
    "guidance_raise": EventTemplate(
        type_id="guidance_raise",
        display_name="Mid-quarter guidance raise",
        direction="up",
        magnitude_min_pct=2.0, magnitude_max_pct=8.0,
        baseline_confidence=0.75, typical_horizon_months=6,
        notes="Standalone guidance raise without earnings. Slightly smaller than beat+raise.",
    ),
    "guidance_cut": EventTemplate(
        type_id="guidance_cut",
        display_name="Mid-quarter guidance cut",
        direction="down",
        magnitude_min_pct=3.0, magnitude_max_pct=12.0,
        baseline_confidence=0.80, typical_horizon_months=6,
        notes="Standalone guidance cut without earnings. Pre-announcements often signal deeper issues.",
    ),

    # ═══ Operations / capacity ═══
    "capacity_expansion": EventTemplate(
        type_id="capacity_expansion",
        display_name="Capacity / facility expansion",
        direction="up",
        magnitude_min_pct=1.0, magnitude_max_pct=6.0,
        baseline_confidence=0.50, typical_horizon_months=18,
        notes="LITE-Canada case. Contingent on demand; confidence gated by utilization risk.",
    ),
    "supply_constraint": EventTemplate(
        type_id="supply_constraint",
        display_name="Supply / production constraint",
        direction="down",
        magnitude_min_pct=2.0, magnitude_max_pct=8.0,
        baseline_confidence=0.70, typical_horizon_months=6,
        notes="Yield issues, sourcing disruption, raw material crunch.",
    ),

    # ═══ Customer ═══
    "customer_win_major": EventTemplate(
        type_id="customer_win_major",
        display_name="Major customer win",
        direction="up",
        magnitude_min_pct=2.0, magnitude_max_pct=8.0,
        baseline_confidence=0.60, typical_horizon_months=12,
        notes="Anchor customer or >5% of revenue contract. Magnitude scales with size/TCV.",
    ),
    "customer_loss_major": EventTemplate(
        type_id="customer_loss_major",
        display_name="Major customer loss",
        direction="down",
        magnitude_min_pct=5.0, magnitude_max_pct=15.0,
        baseline_confidence=0.80, typical_horizon_months=9,
        notes="Asymmetric: losses hit harder than equivalent wins.",
    ),

    # ═══ Product ═══
    "product_launch": EventTemplate(
        type_id="product_launch",
        display_name="Product commercial launch",
        direction="up",
        magnitude_min_pct=2.0, magnitude_max_pct=8.0,
        baseline_confidence=0.55, typical_horizon_months=12,
        notes="Commercial (revenue-generating) launch, not demo/pilot.",
    ),
    "product_delay": EventTemplate(
        type_id="product_delay",
        display_name="Product / program delay",
        direction="down",
        magnitude_min_pct=2.0, magnitude_max_pct=10.0,
        baseline_confidence=0.80, typical_horizon_months=6,
        notes="Further delays after initial slip compound faster.",
    ),

    # ═══ Executive / governance ═══
    "exec_change_positive": EventTemplate(
        type_id="exec_change_positive",
        display_name="Positive executive hire",
        direction="up",
        magnitude_min_pct=2.0, magnitude_max_pct=6.0,
        baseline_confidence=0.40, typical_horizon_months=18,
        notes="Proven operator hire; confidence low because impact takes quarters to show.",
    ),
    "exec_change_negative": EventTemplate(
        type_id="exec_change_negative",
        display_name="Unexpected CEO/CFO departure",
        direction="down",
        magnitude_min_pct=3.0, magnitude_max_pct=12.0,
        baseline_confidence=0.70, typical_horizon_months=9,
        notes="Reaction is larger when departure is sudden / unexplained.",
    ),

    # ═══ Legal ═══
    "litigation_adverse": EventTemplate(
        type_id="litigation_adverse",
        display_name="Adverse material litigation",
        direction="down",
        magnitude_min_pct=3.0, magnitude_max_pct=12.0,
        baseline_confidence=0.75, typical_horizon_months=15,
        notes="Patent invalidation, class-action liability, major antitrust ruling.",
    ),
    "litigation_favorable": EventTemplate(
        type_id="litigation_favorable",
        display_name="Favorable material litigation",
        direction="up",
        magnitude_min_pct=1.0, magnitude_max_pct=5.0,
        baseline_confidence=0.60, typical_horizon_months=15,
        notes="Smaller than adverse (markets expect companies to defend successfully).",
    ),

    # ═══ Competitive / sector ═══
    "competitive_threat": EventTemplate(
        type_id="competitive_threat",
        display_name="New competitive threat",
        direction="down",
        magnitude_min_pct=2.0, magnitude_max_pct=10.0,
        baseline_confidence=0.45, typical_horizon_months=24,
        notes="New entrant, substitute technology, major competitor pricing move.",
    ),
    "sector_tailwind": EventTemplate(
        type_id="sector_tailwind",
        display_name="Sector / macro tailwind",
        direction="up",
        magnitude_min_pct=1.0, magnitude_max_pct=5.0,
        baseline_confidence=0.40, typical_horizon_months=18,
        notes="Policy change, commodity move, end-market acceleration.",
    ),
    "sector_headwind": EventTemplate(
        type_id="sector_headwind",
        display_name="Sector / macro headwind",
        direction="down",
        magnitude_min_pct=1.0, magnitude_max_pct=5.0,
        baseline_confidence=0.40, typical_horizon_months=18,
        notes="Rate moves, regulatory shift, end-market softness.",
    ),

    # ═══ Capital / shareholder ═══
    "buyback_large": EventTemplate(
        type_id="buyback_large",
        display_name="Large buyback announced",
        direction="up",
        magnitude_min_pct=1.0, magnitude_max_pct=4.0,
        baseline_confidence=0.70, typical_horizon_months=9,
        notes=">5% of market cap. Signals capital discipline + undervaluation view.",
    ),
    "dividend_cut": EventTemplate(
        type_id="dividend_cut",
        display_name="Dividend cut / suspension",
        direction="down",
        magnitude_min_pct=5.0, magnitude_max_pct=15.0,
        baseline_confidence=0.90, typical_horizon_months=0,
        notes="Signals deteriorating cash generation. Sharp, immediate reprice.",
    ),

    # ═══ Moat / structural advantage (Chain 2) ═══
    "ip_moat_win": EventTemplate(
        type_id="ip_moat_win",
        display_name="IP / patent moat strengthened",
        direction="up",
        magnitude_min_pct=2.0, magnitude_max_pct=12.0,
        baseline_confidence=0.60, typical_horizon_months=24,
        notes="Key patent grant, litigation win protecting IP, blocking-patent coverage expansion. Larger magnitudes when IP protects core revenue stream.",
    ),
    "market_share_gain": EventTemplate(
        type_id="market_share_gain",
        display_name="Documented market share gain",
        direction="up",
        magnitude_min_pct=3.0, magnitude_max_pct=15.0,
        baseline_confidence=0.65, typical_horizon_months=18,
        notes="Verified share take from named incumbent (not just TAM growth). Larger when displacing monopoly or breaking duopoly.",
    ),
    "pricing_power_demonstrated": EventTemplate(
        type_id="pricing_power_demonstrated",
        display_name="Pricing power demonstrated",
        direction="up",
        magnitude_min_pct=2.0, magnitude_max_pct=8.0,
        baseline_confidence=0.65, typical_horizon_months=12,
        notes="Successful price increase without volume loss; ASP expansion; premium tier adoption. Signals structural moat, not just demand.",
    ),
    "switching_cost_deepening": EventTemplate(
        type_id="switching_cost_deepening",
        display_name="Switching-cost moat deepening",
        direction="up",
        magnitude_min_pct=2.0, magnitude_max_pct=10.0,
        baseline_confidence=0.55, typical_horizon_months=24,
        notes="Multi-year contracts, platform lock-in, certification / qualification cycles that raise exit cost. Common in specialty semis, enterprise SaaS.",
    ),
    "regulatory_moat": EventTemplate(
        type_id="regulatory_moat",
        display_name="Regulatory / certification moat",
        direction="up",
        magnitude_min_pct=3.0, magnitude_max_pct=12.0,
        baseline_confidence=0.70, typical_horizon_months=18,
        notes="Certifications that block competitors (FAA TC, FDA BLA, defense qual). Differs from regulatory_approval: this is about the barrier itself, not the product clearance.",
    ),
    "moat_erosion": EventTemplate(
        type_id="moat_erosion",
        display_name="Moat erosion (patent expiry, substitute tech)",
        direction="down",
        magnitude_min_pct=4.0, magnitude_max_pct=18.0,
        baseline_confidence=0.65, typical_horizon_months=18,
        notes="Patent cliff, credible substitute technology, commoditization evidence. Mirror of ip_moat_win / switching_cost_deepening.",
    ),
}


# Convenience lookups
ALL_TYPE_IDS = list(EVENT_TEMPLATES.keys())


def get_template(type_id: str) -> EventTemplate | None:
    """Return the template for a type_id, or None if unknown."""
    return EVENT_TEMPLATES.get(type_id)


def describe_taxonomy_for_prompt() -> str:
    """Render the taxonomy as a compact string block for LLM prompts."""
    lines = ["Event types available (pick one):"]
    for t in EVENT_TEMPLATES.values():
        sign = "+" if t.direction == "up" else "-"
        lines.append(
            f"  - {t.type_id:26s} ({t.display_name}) "
            f"baseline {sign}{t.magnitude_min_pct:.0f}–{t.magnitude_max_pct:.0f}%, "
            f"horizon ~{t.typical_horizon_months}mo"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe_taxonomy_for_prompt())
    print(f"\nTotal: {len(EVENT_TEMPLATES)} event types")
