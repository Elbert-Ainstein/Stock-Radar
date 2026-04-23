#!/usr/bin/env python3
"""
Event reasoner — turns raw events extracted by scouts into structured
impact records with a 3-level causal chain and compounded confidence.

Inputs:  list of raw events (dict with summary/type/direction/etc)
Outputs: list of reasoned events with magnitude_pct, probability,
         compounded_confidence, expected_contribution_pct, chain[]

Two modes:
  - LLM mode (requires ANTHROPIC_API_KEY): one Claude call per event,
    picks magnitude within template range with justification and
    walks the causal chain.
  - Fallback mode (no key): uses template midpoint with a flat
    probability of 0.5 and a one-line chain. Safe degradation; the
    system still produces event_impacts, just without LLM nuance.

Design notes:
  - We NEVER let the LLM invent event types. Raw events already carry
    a valid `type`; reasoner only fills magnitudes and chains.
  - Magnitudes are clamped to the template range. LLM overruns get
    cut back to the bounds — prevents a rogue call from inflating.
  - Confidence compounds multiplicatively across levels, which is
    realistic: each inferential hop adds uncertainty.

See docs/event_target_plan.md §5, §6 for the design.
"""
from __future__ import annotations
import os
import re
import json
import math
import hashlib
import requests
from datetime import datetime, timezone
from event_templates import EVENT_TEMPLATES, EventTemplate, get_template

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-opus-4-6"
REQUEST_TIMEOUT = 45


# ─── Decay / cap constants (tune here) ───
RECENCY_HALF_LIFE_DAYS = 62  # ≈ 90-day effective window, 62-day half-life
MAX_SINGLE_EVENT_PCT = 10.0  # no single event contributes more than ±10% to target
MAX_TOTAL_EVENT_PCT = 15.0   # total event adjustment capped at ±15%

# Per-event-type stack cap: when N events of the same type fire (e.g. 5
# `market_share_gain` events all reflecting the same "AMD takes share"
# story), the strongest evidence keeps full weight and additional facets
# get diminishing weight. Without this, conceptually-correlated events
# stack like independent stories. The series caps the effective count
# below ~2 distinct events per type even with many noisy duplicates.
TYPE_STACK_WEIGHTS = [1.0, 0.45, 0.20, 0.10, 0.05]
TYPE_STACK_TAIL_WEIGHT = 0.03  # weight for any event beyond the 5th in a type


def _event_id(ticker: str, summary: str) -> str:
    """Deterministic event ID from ticker + normalized summary.
    Same summary from different runs maps to the same ID → stable dedup.
    """
    norm = re.sub(r'\s+', ' ', summary.lower()).strip()
    norm = re.sub(r'[^\w\s$%]', '', norm)
    h = hashlib.md5(f"{ticker}|{norm}".encode()).hexdigest()[:12]
    return f"{ticker.lower()}_{h}"


def _days_since(date_str: str | None) -> float:
    """Return days since the given ISO date, or 30 if unknown.

    Default to 30 days (not 0) for undated events so they get moderate
    recency weight instead of maximum freshness. An undated event is NOT
    a brand-new event — it's one where we don't know the date.
    """
    if not date_str:
        return 30.0
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            d = datetime.strptime(date_str[:len(fmt.replace('%', ''))], fmt)
            return max(0.0, (datetime.now(timezone.utc) - d.replace(tzinfo=timezone.utc)).total_seconds() / 86400.0)
        except (ValueError, TypeError):
            continue
    return 0.0


def _recency_weight(days_old: float) -> float:
    """Exponential decay, 62-day half-life."""
    return math.exp(-days_old / RECENCY_HALF_LIFE_DAYS)


def _clamp_magnitude(magnitude_pct: float, template: EventTemplate) -> float:
    """Clamp LLM-picked magnitude into the template's allowed range."""
    lo, hi = template.signed_magnitude_range
    return max(lo, min(hi, magnitude_pct))


# ─── Fallback reasoner (no LLM) ───

def _fallback_reason(event: dict, template: EventTemplate) -> dict:
    """Produce a reasoned event without calling an LLM.
    Uses template midpoint, 0.5 probability, single-line chain.
    """
    # Use signed_magnitude_range midpoint instead of raw midpoint_pct * sign.
    # This correctly handles templates like ma_acquirer where direction="up"
    # but magnitude_min is negative (dilutive deals): midpoint_pct would be 0
    # with sign=+1 giving 0, but signed_magnitude_range gives (-5, 5) → mid=0.
    # For asymmetric templates, signed range is more accurate.
    lo, hi = template.signed_magnitude_range
    magnitude = (lo + hi) / 2.0
    return {
        "magnitude_pct": magnitude,
        "probability": 0.5,
        "chain": [
            {
                "level": 1,
                "claim": (
                    f"Template baseline for {template.display_name.lower()}: "
                    f"~{template.midpoint_pct:.1f}% target Δ over ~{template.typical_horizon_months}mo"
                ),
                "confidence": template.baseline_confidence,
                "reasoning": "Fallback midpoint — LLM reasoning unavailable.",
            }
        ],
        "time_horizon_months": template.typical_horizon_months,
        "reasoner": "fallback",
    }


# ─── Claude reasoner ───

REASONER_PROMPT = """You are an equity research reasoner. Given a news event for a stock, you estimate how much it SHOULD move the 12–18 month price target, and walk through the causal chain.

STOCK: {ticker} ({sector} sector)
STOCK THESIS (for context): {thesis}

EVENT:
  Summary: {summary}
  Type: {type_id} — {type_display}
  Direction (as extracted): {extracted_direction}
  Date: {date}
  Rationale (from scout): {rationale}

TEMPLATE ANCHORS for this event type:
  Baseline magnitude range: {sign}{mag_min:.1f}% to {sign}{mag_max:.1f}%  (target price Δ)
  Typical time horizon: {horizon} months
  Baseline confidence: {base_conf}
  Notes: {notes}

Your task:
1. Pick a magnitude IN PERCENTAGE POINTS within the template's range. You may pick either end or anywhere between. Think about this company's specific situation (size of the move relative to company revenue, execution risk, sector dynamics).
2. Write a 3-level causal chain:
   Level 1: Direct operational effect  (e.g., "adds X% to production capacity")
   Level 2: Financial implication       (e.g., "raises revenue ceiling by ~Y% over Z months")
   Level 3: Valuation implication       (e.g., "translates to W% target price Δ at current multiple")
   Each level has a confidence 0.0–1.0 — how certain is THIS specific inferential hop?
3. Estimate overall probability the chain plays out as described (0.0–1.0). Consider: execution risk, demand-side dependencies, macro contingencies.

Return ONLY valid JSON (no markdown fences, no commentary):

{{
  "magnitude_pct": <signed number in the template range>,
  "probability": <0.0 to 1.0>,
  "time_horizon_months": <integer>,
  "chain": [
    {{"level": 1, "claim": "...", "confidence": 0.0-1.0, "reasoning": "one-sentence why"}},
    {{"level": 2, "claim": "...", "confidence": 0.0-1.0, "reasoning": "one-sentence why"}},
    {{"level": 3, "claim": "...", "confidence": 0.0-1.0, "reasoning": "one-sentence why"}}
  ]
}}"""


def _llm_reason(event: dict, template: EventTemplate, stock_context: dict) -> dict | None:
    """Call Claude to reason about one event. Returns None on failure."""
    if not ANTHROPIC_API_KEY:
        return None

    sign = "+" if template.direction == "up" else "-"
    prompt = REASONER_PROMPT.format(
        ticker=stock_context.get("ticker", ""),
        sector=stock_context.get("sector", "Unknown"),
        thesis=(stock_context.get("thesis") or "")[:300],
        summary=event.get("summary", ""),
        type_id=template.type_id,
        type_display=template.display_name,
        extracted_direction=event.get("direction") or template.direction,
        date=event.get("date") or "unknown",
        rationale=(event.get("rationale") or "")[:300],
        sign=sign,
        mag_min=template.magnitude_min_pct,
        mag_max=template.magnitude_max_pct,
        horizon=template.typical_horizon_months,
        base_conf=template.baseline_confidence,
        notes=template.notes,
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1000,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [{}])[0].get("text", "")
        clean = re.sub(r'^```(?:json)?\s*', '', content.strip())
        clean = re.sub(r'\s*```$', '', clean)
        parsed = json.loads(clean)

        # Validate + clamp
        magnitude = float(parsed.get("magnitude_pct", template.midpoint_pct))
        magnitude = _clamp_magnitude(magnitude, template)
        probability = max(0.0, min(1.0, float(parsed.get("probability", 0.5))))
        horizon = int(parsed.get("time_horizon_months") or template.typical_horizon_months)

        chain = []
        for link in parsed.get("chain", []) or []:
            if not isinstance(link, dict):
                continue
            chain.append({
                "level": int(link.get("level", 0)),
                "claim": str(link.get("claim", ""))[:300],
                "confidence": max(0.0, min(1.0, float(link.get("confidence", 0.5)))),
                "reasoning": str(link.get("reasoning", ""))[:300],
            })
        if not chain:
            return None

        return {
            "magnitude_pct": magnitude,
            "probability": probability,
            "time_horizon_months": horizon,
            "chain": chain,
            "reasoner": "claude",
        }

    except (json.JSONDecodeError, ValueError) as e:
        print(f"    [reasoner] JSON/value error: {e}")
        return None
    except Exception as e:
        print(f"    [reasoner] Claude error: {e}")
        return None


# ─── Per-type stack-cap dedup ───

def _apply_type_stack_cap(reasoned: list[dict]) -> list[dict]:
    """Rebalance expected_contribution_pct so multiple events of the same
    type can't stack like fully-independent stories.

    For each event type:
      1. Sort events of that type by abs(pre_dedup_contribution) desc.
      2. Apply TYPE_STACK_WEIGHTS to scale each event's contribution.
         Best evidence keeps 100%, 2nd gets 45%, 3rd 20%, 4th 10%, 5th 5%,
         remainder 3% each.
      3. Cap the total per-type contribution at the template's magnitude_max
         (no event-type cluster can exceed what a single best-case event of
         that type would add).

    Mutates `reasoned` in place: sets `expected_contribution_pct` to the
    de-stacked value and adds `pre_dedup_contribution_pct` + `dedup_weight`
    fields for audit transparency.
    """
    by_type: dict[str, list[dict]] = {}
    for e in reasoned:
        # Stash the original for audit before we mutate.
        e["pre_dedup_contribution_pct"] = e.get("expected_contribution_pct", 0)
        e["dedup_weight"] = 1.0
        by_type.setdefault(e.get("type", "?"), []).append(e)

    for type_id, group in by_type.items():
        if len(group) <= 1:
            continue  # nothing to dedup

        template = get_template(type_id)
        # Sort by strongest pre-dedup contribution (best evidence first).
        group.sort(key=lambda x: abs(x["pre_dedup_contribution_pct"]), reverse=True)

        # Apply diminishing weights.
        for i, e in enumerate(group):
            w = TYPE_STACK_WEIGHTS[i] if i < len(TYPE_STACK_WEIGHTS) else TYPE_STACK_TAIL_WEIGHT
            e["dedup_weight"] = w
            e["expected_contribution_pct"] = round(
                e["pre_dedup_contribution_pct"] * w, 2
            )

        # Cap the per-type cluster total at the template's max single-event size.
        if template is not None:
            cap = template.magnitude_max_pct
            cluster_sum = sum(e["expected_contribution_pct"] for e in group)
            if abs(cluster_sum) > cap:
                scale = cap / abs(cluster_sum)
                for e in group:
                    e["expected_contribution_pct"] = round(
                        e["expected_contribution_pct"] * scale, 2
                    )
                    e["dedup_weight"] = round(e["dedup_weight"] * scale, 3)

    return reasoned


# ─── Public API ───

def reason_events(events: list[dict], stock_context: dict) -> list[dict]:
    """
    Turn raw events into reasoned events with full impact metadata.

    `stock_context`: {ticker, sector, thesis} — used by the LLM for context.
    Returns list sorted by |expected_contribution_pct| descending.
    """
    if not events:
        return []

    ticker = stock_context.get("ticker", "")
    reasoned = []

    for ev in events:
        etype = ev.get("type") or ""
        template = get_template(etype)
        if not template:
            continue  # unknown type — skip rather than invent

        # Get chain + magnitude + probability (LLM or fallback)
        result = _llm_reason(ev, template, stock_context) or _fallback_reason(ev, template)

        # Compute compounded confidence = product of level confidences
        compounded_conf = 1.0
        for link in result["chain"]:
            compounded_conf *= link.get("confidence", 0.5)

        # Recency decay
        days_old = _days_since(ev.get("date"))
        recency = _recency_weight(days_old)

        # Expected contribution = magnitude × probability × compounded_confidence × recency
        expected = result["magnitude_pct"] * result["probability"] * compounded_conf * recency

        # Cap single event
        sign = 1 if expected >= 0 else -1
        capped = sign * min(abs(expected), MAX_SINGLE_EVENT_PCT)

        reasoned.append({
            "event_id": _event_id(ticker, ev.get("summary", "")),
            "type": template.type_id,
            "type_display": template.display_name,
            "summary": ev.get("summary", ""),
            "rationale": ev.get("rationale", ""),
            "direction": "up" if result["magnitude_pct"] >= 0 else "down",
            "magnitude_pct": round(result["magnitude_pct"], 2),
            "probability": round(result["probability"], 2),
            "compounded_confidence": round(compounded_conf, 3),
            "recency_weight": round(recency, 3),
            "expected_contribution_pct": round(capped, 2),
            "time_horizon_months": result["time_horizon_months"],
            "chain": result["chain"],
            "reasoner": result["reasoner"],
            "evidence": [{
                "date": ev.get("date"),
                "source": ev.get("source"),
                "url": ev.get("url"),
                "headline": ev.get("summary", ""),
            }] if ev.get("url") or ev.get("source") or ev.get("date") else [],
            "detected_by": ev.get("detected_by", "unknown"),
            "first_seen": ev.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "status": "active",
        })

    # Apply per-type stack-cap dedup before final sort. Individual events
    # keep their full magnitude/probability/confidence data; only
    # expected_contribution_pct is rebalanced to reflect correlated facets.
    _apply_type_stack_cap(reasoned)

    reasoned.sort(key=lambda x: abs(x["expected_contribution_pct"]), reverse=True)
    return reasoned


def sum_adjustments(reasoned_events: list[dict]) -> dict:
    """Combine reasoned events into a total target adjustment.
    Applies total-saturation cap. Returns breakdown for audit.
    """
    raw_sum = sum(e["expected_contribution_pct"] for e in reasoned_events)
    capped = max(-MAX_TOTAL_EVENT_PCT, min(MAX_TOTAL_EVENT_PCT, raw_sum))
    return {
        "event_adjustment_pct": round(capped, 2),
        "raw_sum_pct": round(raw_sum, 2),
        "capped": abs(raw_sum) > MAX_TOTAL_EVENT_PCT,
        "event_count": len(reasoned_events),
        "up_count": sum(1 for e in reasoned_events if e["direction"] == "up"),
        "down_count": sum(1 for e in reasoned_events if e["direction"] == "down"),
    }


if __name__ == "__main__":
    # Demo run
    demo_events = [
        {
            "summary": "Lumentum acquires Ciena's Montreal photonics facility to expand datacom capacity",
            "type": "capacity_expansion",
            "direction": "up",
            "date": "2026-03-15",
            "source": "Reuters",
            "url": "https://example.com",
            "rationale": "Adds ~25% transceiver production capacity amid AI datacenter demand",
        }
    ]
    stock_ctx = {"ticker": "LITE", "sector": "Semiconductors", "thesis": "Datacom optical components beneficiary of AI capex"}
    reasoned = reason_events(demo_events, stock_ctx)
    print(json.dumps(reasoned, indent=2, default=str))
    print("\nSummary:", json.dumps(sum_adjustments(reasoned), indent=2))
