#!/usr/bin/env python3
"""
Target Price Model Generator
Uses Perplexity (research) + Claude (analysis) to auto-generate:
  - Model defaults (revenue, margin, tax, shares, multiple)
  - 8-12 measurable criteria mapped to R/M/T/S/P variables
  - Bear/Base/Bull scenarios with probabilities
  - Valuation method selection (P/E vs P/S)

Reads the analyst_prompt.md guideline and produces structured output
that feeds directly into the interactive model UI.

Usage:
    python scripts/generate_model.py --ticker LITE
    python scripts/generate_model.py --ticker LITE --target 1500
    python scripts/generate_model.py --all          # all watchlist
"""
import os
import json
import re
import sys
import time
import functools
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import load_env, get_watchlist, timestamp
from registries import ALL_ARCHETYPES, LLM_VALUATION_METHODS, ALL_LIFECYCLE_STAGES, ALL_MOAT_WIDTHS

# Force unbuffered output so status lines appear immediately
print = functools.partial(print, flush=True)

load_env()

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CONFIG_DIR = Path(__file__).parent.parent / "config"
ANALYST_PROMPT_PATH = CONFIG_DIR / "analyst_prompt.md"


# ── Structured Outputs JSON Schema ──────────────────────────────────────────
# Anthropic Structured Outputs (GA) guarantees the response conforms to this
# schema, eliminating the need for multi-layer JSON repair.  The schema mirrors
# the MODEL_GEN_PROMPT template exactly.  See:
# https://docs.anthropic.com/en/docs/build-with-claude/structured-outputs

_SCENARIO_SCHEMA = {
    "type": "object",
    "properties": {
        "probability": {"type": "number"},
        "price": {"type": "number"},
        "trigger": {"type": "string"},
    },
    "required": ["probability", "price", "trigger"],
    "additionalProperties": False,
}

MODEL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thesis": {"type": "string"},
        "sector": {"type": "string"},
        "kill_condition": {"type": "string"},
        "archetype": {
            "type": "object",
            "properties": {
                "primary": {
                    "type": "string",
                    "enum": ALL_ARCHETYPES,
                },
                "secondary": {
                    "anyOf": [
                        {"type": "string", "enum": ALL_ARCHETYPES},
                        {"type": "null"},
                    ],
                },
                "justification": {"type": "string"},
                "lifecycle_stage": {
                    "type": "string",
                    "enum": ALL_LIFECYCLE_STAGES,
                },
                "moat_width": {
                    "type": "string",
                    "enum": ALL_MOAT_WIDTHS,
                },
            },
            "required": ["primary", "secondary", "justification",
                         "lifecycle_stage", "moat_width"],
            "additionalProperties": False,
        },
        "valuation_method": {"type": "string", "enum": LLM_VALUATION_METHODS},
        "valuation_justification": {"type": "string"},
        "model_defaults": {
            "type": "object",
            "properties": {
                "revenue_b": {"type": "number"},
                "op_margin": {"type": "number"},
                "tax_rate": {"type": "number"},
                "shares_m": {"type": "number"},
                "pe_multiple": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "ps_multiple": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "valuation_method": {"type": "string", "enum": LLM_VALUATION_METHODS},
            },
            "required": ["revenue_b", "op_margin", "tax_rate", "shares_m",
                         "pe_multiple", "ps_multiple", "valuation_method"],
            "additionalProperties": False,
        },
        "scenarios": {
            "type": "object",
            "properties": {
                "bull": _SCENARIO_SCHEMA,
                "base": _SCENARIO_SCHEMA,
                "bear": _SCENARIO_SCHEMA,
            },
            "required": ["bull", "base", "bear"],
            "additionalProperties": False,
        },
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "detail": {"type": "string"},
                    "variable": {"type": "string", "enum": ["R", "M", "P", "S", "E"]},
                    "weight": {"type": "string", "enum": ["critical", "important", "monitoring"]},
                    "status": {"type": "string", "enum": ["not_yet", "met", "failed"]},
                    "eval_hint": {"type": "string"},
                    "price_impact_pct": {"type": "number"},
                    "price_impact_direction": {"type": "string", "enum": ["up", "down_if_failed"]},
                },
                "required": ["id", "label", "detail", "variable", "weight",
                             "status", "eval_hint", "price_impact_pct",
                             "price_impact_direction"],
                "additionalProperties": False,
            },
        },
        "target_notes": {"type": "string"},
        "divergence_note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": [
        "thesis", "sector", "kill_condition", "archetype",
        "valuation_method", "valuation_justification",
        "model_defaults", "scenarios", "criteria", "target_notes",
        "divergence_note",
    ],
    "additionalProperties": False,
}


def load_analyst_guideline() -> str:
    """Load the analyst prompt guideline."""
    if ANALYST_PROMPT_PATH.exists():
        return ANALYST_PROMPT_PATH.read_text(encoding="utf-8")
    return ""


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_quant_data(ticker: str) -> dict:
    """Load quant scout data for a ticker.

    Primary source: Supabase latest_signals view (same as analyst.py).
    Fallback: local quant_signals.json (may be stale — save_signals returns
    after a successful Supabase insert without writing JSON).

    This provides hard financial facts from quant scout that should NOT be
    re-fetched via Perplexity.
    """
    # ── Supabase first (source of truth) ──
    try:
        from supabase_helper import get_client
        sb = get_client()
        resp = (
            sb.table("latest_signals")
            .select("data")
            .eq("ticker", ticker.upper())
            .eq("scout", "quant")
            .maybe_single()
            .execute()
        )
        if resp.data and resp.data.get("data"):
            print(f"  [{ticker}] Loaded quant data from Supabase")
            return resp.data["data"]
    except Exception as e:
        print(f"  [{ticker}] Supabase quant lookup failed ({e}) — trying JSON fallback")

    # ── JSON fallback (only when DB is unreachable) ──
    try:
        signals_file = DATA_DIR / "quant_signals.json"
        if signals_file.exists():
            data = json.loads(signals_file.read_text(encoding="utf-8"))
            for sig in data.get("signals", []):
                if sig.get("ticker") == ticker:
                    print(f"  [{ticker}] Loaded quant data from JSON fallback (may be stale)")
                    return sig.get("data", {})
    except Exception:
        pass
    return {}


def format_quant_facts(ticker: str, quant_data: dict) -> str:
    """Format quant data as hard facts for the Claude prompt.
    These numbers come from quant scout and should be treated as ground truth."""
    if not quant_data:
        return f"[No quant scout data available for {ticker} — rely on Perplexity research below]"

    price = quant_data.get("price") or 0
    market_cap_b = quant_data.get("market_cap_b") or 0
    ps_ratio = quant_data.get("ps_ratio")
    pe_ratio = quant_data.get("pe_ratio")
    forward_pe = quant_data.get("forward_pe")
    rev_growth = quant_data.get("revenue_growth_pct") or 0
    earn_growth = quant_data.get("earnings_growth_pct") or 0
    gross_margin = quant_data.get("gross_margin_pct") or 0
    op_margin = quant_data.get("operating_margin_pct") or 0
    beta = quant_data.get("beta")
    short_pct = quant_data.get("short_pct") or 0
    fcf = quant_data.get("free_cash_flow") or 0

    # TTM revenue: prefer direct quant scout value, fall back to market_cap / P/S
    ttm_rev = quant_data.get("ttm_revenue")
    current_rev_b = ttm_rev if ttm_rev and ttm_rev > 0 else (round(market_cap_b / ps_ratio, 2) if ps_ratio and ps_ratio > 0 else None)
    rev_source = "TTM" if (ttm_rev and ttm_rev > 0) else "derived from mktcap/PS"

    # Shares: prefer direct quant scout value, fall back to market_cap / price
    shares_direct = quant_data.get("shares_outstanding_m")
    shares_m = shares_direct if shares_direct and shares_direct > 0 else (round((market_cap_b * 1000) / price) if price > 0 else None)
    shares_source = "reported" if (shares_direct and shares_direct > 0) else "derived from mktcap/price"

    lines = [
        f"HARD FINANCIAL DATA (from quant scout — treat as ground truth, do NOT override with estimates):",
        f"  Stock price: ${price:.2f}",
        f"  Market cap: ${market_cap_b:.1f}B",
    ]
    if current_rev_b:
        lines.append(f"  {rev_source} revenue: ${current_rev_b:.1f}B")
    if shares_m:
        lines.append(f"  Diluted shares ({shares_source}): ~{shares_m}M")
    lines.append(f"  Revenue growth: {rev_growth:.1f}% YoY")
    lines.append(f"  Earnings growth: {earn_growth:.1f}% YoY")
    lines.append(f"  Gross margin: {gross_margin:.1f}%")
    lines.append(f"  Operating margin: {op_margin:.1f}%")
    if pe_ratio:
        lines.append(f"  Trailing P/E: {pe_ratio:.1f}")
    if forward_pe:
        lines.append(f"  Forward P/E: {forward_pe:.1f}")
    if ps_ratio:
        lines.append(f"  P/S ratio: {ps_ratio:.1f}")
    if beta:
        lines.append(f"  Beta: {beta:.2f}")
    lines.append(f"  Short interest: {short_pct:.1f}%")
    if fcf:
        lines.append(f"  Free cash flow: ${fcf / 1e9:.2f}B")

    return "\n".join(lines)


def research_financials(ticker: str, name: str, sector: str) -> str:
    """Use Perplexity for FORWARD-LOOKING data only.
    Hard financials (revenue, margins, P/E) come from quant scout via quant scout.
    Perplexity fills in: guidance, analyst targets, catalysts, industry dynamics."""
    if not PERPLEXITY_API_KEY:
        return ""

    # Focus Perplexity on what quant scout CAN'T provide
    # Dynamically compute fiscal years so queries stay relevant
    from datetime import datetime as _dt
    _now = _dt.now()
    fy_current = _now.year
    fy_next = fy_current + 1
    fy_after = fy_current + 2

    queries = [
        f"{ticker} {name} FY{fy_current} FY{fy_next} FY{fy_after} revenue guidance analyst consensus estimates forward outlook",
        f"{ticker} {name} management guidance targets long-term margin goals TAM market share competitive moat",
        f"{ticker} {name} bull case bear case risks catalysts price target analyst ratings recent upgrades downgrades",
        # Industry cycle — critical for cyclical stocks
        f"{sector} industry supply demand cycle outlook {fy_current} {fy_next} pricing trends capacity expansion risks competitors",
    ]

    query_labels = ["guidance/consensus", "moat/TAM", "bull-bear/catalysts", "industry cycle"]
    system_msg = (
        "You are an equity research analyst. Provide factual, data-rich responses "
        "with specific numbers, percentages, and dollar amounts. "
        "Focus on FORWARD estimates, guidance, catalysts, and industry dynamics. "
        "Do NOT repeat basic financial data like current revenue or margins — "
        "those are already available from another source. "
        "No disclaimers."
    )

    def _fetch_query(args):
        idx, query = args
        label = query_labels[idx] if idx < len(query_labels) else f"query {idx+1}"
        try:
            resp = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": query},
                    ],
                    "max_tokens": 800,
                    "temperature": 0.1,
                    "web_search": True,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"    ✓ {label} ({len(content)} chars)")
            return idx, content
        except requests.exceptions.Timeout:
            print(f"    ✗ {label} — TIMEOUT (Perplexity took >30s)")
            return idx, None
        except Exception as e:
            err_msg = str(e)[:100]
            print(f"    ✗ {label} — {err_msg}")
            return idx, None

    # Run all 4 Perplexity queries concurrently (was sequential with 1.5s sleep)
    results = [None] * len(queries)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for idx, content in pool.map(_fetch_query, enumerate(queries)):
            if content:
                results[idx] = content

    research_parts = [r for r in results if r]
    success = len(research_parts)
    total = len(queries)
    if success < total:
        print(f"    Research: {success}/{total} queries succeeded{' — proceeding with partial data' if success > 0 else ' — NO research data'}")

    return "\n\n---\n\n".join(research_parts)


def repair_truncated_json(text: str) -> str | None:
    """Attempt to repair JSON that was truncated mid-stream (hit max_tokens).

    Strategy:
    1. Find the outermost opening brace
    2. Walk the string tracking open/close braces and brackets
    3. Strip the last incomplete key-value pair
    4. Close all remaining open braces/brackets
    """
    first = text.find('{')
    if first == -1:
        return None

    text = text[first:]

    # Strip trailing incomplete string/value — find last complete key:value
    # by looking for the last comma or opening brace that's followed by valid JSON
    # Simple approach: strip back to last comma or opening brace at depth > 0
    stack = []
    in_string = False
    escape = False
    last_good = 0

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch in '{[':
            stack.append(ch)
        elif ch == '}' and stack and stack[-1] == '{':
            stack.pop()
            last_good = i + 1
        elif ch == ']' and stack and stack[-1] == '[':
            stack.pop()
            last_good = i + 1
        elif ch == ',' and stack:
            last_good = i + 1

    if not stack:
        # JSON is already complete — just parse it
        return text[:last_good] if last_good > 0 else text

    # Truncated — cut back to last_good and close the stack
    result = text[:last_good] if last_good > 0 else text.rstrip()

    # Remove any trailing comma
    result = result.rstrip().rstrip(',')

    # Close remaining open braces/brackets in reverse order
    for opener in reversed(stack):
        result += ']' if opener == '[' else '}'

    return result


MODEL_GEN_PROMPT = """You are a senior equity research analyst building a target price model.

COMPANY: {ticker} ({name}), {sector} sector
INVESTMENT HORIZON: {timeline} years
CURRENT THESIS: {thesis}
KILL CONDITION: {kill_condition}

{quant_facts}

FORWARD-LOOKING RESEARCH (from Perplexity — guidance, analyst targets, catalysts, industry dynamics):
{research}

─── STEP 0: ARCHETYPE CLASSIFICATION (do this FIRST) ───

Before deriving any inputs, classify this stock into its PRIMARY investment archetype.
The archetype determines which analytical questions matter most, which valuation
framework to emphasize, and how to interpret drawdowns and kill conditions.

ARCHETYPES:
  "garp" — Growth at a Reasonable Price (Lynch). Revenue growing 10-30%, positive
    earnings, moderate P/E. The DEFAULT mode. Forecast growth, ramp margins, apply
    growth-adjusted multiple. Exit when PEG exceeds sector median substantially.

  "cyclical" — Normalized Earnings (Damodaran). Company's value is driven by where
    it sits in the industry cycle, not just its execution. TTM EBITDA may be
    unsustainably high (peak) or depressed (trough). CRITICAL: do NOT extrapolate
    peak-cycle margins forward — use normalized (mid-cycle average) margins for the
    base case. Bear case must model the cycle turning. Criteria should track cycle
    indicators (inventory/sales, capacity utilization, order backlog, commodity pricing).
    A 40% drawdown at peak cycle is the EXPECTED bear case, not a kill condition.

  "transformational" — Right-Tail Optionality (Baillie Gifford). Revenue growing >30%,
    negative or minimal EBITDA, large TAM, platform/network effects. Widen the scenario
    spread significantly — bear and bull should NOT be symmetric around base. Criteria
    should track TAM penetration, network density, unit economics trajectory, NOT
    sequential revenue beats. A 50% price drawdown with intact structural thesis is a
    buying opportunity, not a kill condition.

  "compounder" — Quality Earnings Power (Buffett/Munger). Durable moat, ROIC
    consistently >15%, stable margins. The right question is NOT "what's the 3-year
    target?" but "how long can this company sustain above-WACC returns?" (the
    Competitive Advantage Period). Criteria should track moat health: customer
    retention, pricing power, ROIC stability. Exit trigger is moat deterioration,
    not price target.

  "special_situation" — Event-Driven. Value depends on a specific catalyst (spin-off,
    merger, regulatory approval, activist campaign). The primary valuation is
    P(event) × value-if-succeeds + (1-P) × value-if-fails. Criteria should be
    entirely event-specific. Exit is binary: the event resolves.

Choose based on the financial data and research above. A company can have secondary
characteristics (e.g., LITE = GARP primary + Cyclical secondary), but the PRIMARY
archetype determines the analytical framework. Include secondary if relevant.

ALSO classify the company's position on two additional dimensions:

LIFECYCLE STAGE (Damodaran corporate lifecycle):
  "startup" — pre-revenue or minimal revenue, burning cash, product-market fit unproven
  "high_growth" — revenue growing >25%, negative or slim profits, reinvesting heavily
  "mature_growth" — revenue growing 10-25%, positive and expanding margins
  "mature_stable" — revenue growing <10%, stable margins, returning cash to shareholders
  "decline" — revenue shrinking, business in structural decline

MOAT WIDTH (Morningstar-style competitive advantage assessment):
  "none" — no sustainable competitive advantage; commodity business
  "narrow" — competitive advantage exists but is not durable (5-10 years)
  "wide" — durable competitive advantage with 10+ year runway (brand, network, IP, switching costs)

METHODOLOGY:
Your outputs feed into a 5-year DCF engine that computes:
  EV = Terminal EBITDA × EV/EBITDA (blended with FCF-SBC leg)
  Equity = PV(EV) − Net Debt
  Price = Equity / Diluted Shares
Your job is to provide grounded inputs (revenue, margins, multiples, scenarios).
Derive each input INDEPENDENTLY from base rates, then adjust with evidence.
Do NOT reverse-engineer from a target price — that operationalizes anchoring bias.

Based on the guideline and research, produce a STRUCTURED JSON model configuration.
Return ONLY valid JSON — no markdown fences, no commentary.

{{
  "thesis": "1-2 sentence investment thesis: what makes this stock worth owning, the core growth driver, and the expected catalyst timeline. Must be specific — not generic bullish language.",
  "sector": "<correct sector classification — e.g. Semiconductors, Software, Internet, Biotech, Industrials, Consumer, Financials, Energy, etc.>",
  "kill_condition": "1 sentence: the specific, measurable condition that would invalidate the thesis and trigger an exit (e.g. 'Revenue growth below 10% for 2 consecutive quarters' or 'Loss of >20% market share in GPU accelerators').",

  "archetype": {{
    "primary": "garp" | "cyclical" | "transformational" | "compounder" | "special_situation",
    "secondary": null or one of the above (if the stock has meaningful hybrid characteristics),
    "justification": "1-2 sentences explaining why this archetype was chosen and what it means for the analysis",
    "lifecycle_stage": "startup" | "high_growth" | "mature_growth" | "mature_stable" | "decline",
    "moat_width": "none" | "narrow" | "wide"
  }},

  "valuation_method": "pe" or "ps",
  "valuation_justification": "1-2 sentences explaining why this method was chosen",

  "model_defaults": {{
    "revenue_b": <TTM or forward annual revenue in billions — see REVENUE RULE below>,
    "op_margin": <target operating margin as decimal, e.g. 0.40>,
    "tax_rate": <effective tax rate as decimal, e.g. 0.17>,
    "shares_m": <diluted shares in millions, e.g. 74>,
    "pe_multiple": <target P/E multiple if method=pe, else null — must pair with Net Income, never NOPAT>,
    "ps_multiple": <target P/S multiple if method=ps, else null>,
    "valuation_method": "pe" or "ps"
  }},

  "scenarios": {{
    "bull": {{
      "probability": <state-contingent, typically 0.15-0.30 — see SCENARIO RULES>,
      "price": <bull case price — derived bottom-up, not target × 1.3>,
      "trigger": "2-3 sentences: what causes this, when it happens, and industry conditions required"
    }},
    "base": {{
      "probability": <1 minus bull minus bear>,
      "price": <base case price — derived from consensus/guidance>,
      "trigger": "2-3 sentences: expected path, timeline, and key assumptions"
    }},
    "bear": {{
      "probability": <state-contingent — see SCENARIO RULES>,
      "price": <bear case price — must model specific downside, not a token haircut>,
      "trigger": "2-3 sentences: what goes wrong, when, and how bad it gets"
    }}
  }},

  "criteria": [
    {{
      "id": "snake_case_unique_id",
      "label": "Human-readable criterion name",
      "detail": "1-2 sentences: what specific driver assumption changes if this criterion is met/fails, and what that means for the target. Criteria in the same driver group (e.g., multiple R criteria) collectively inform ONE revenue trajectory — they are not additive price increments.",
      "variable": "R, M, P, S, or E",
      "weight": "critical" or "important" or "monitoring",
      "status": "not_yet",
      "eval_hint": "How to verify (include specific threshold AND timeframe, e.g. 'Revenue >= $8B by FY2027')",
      "price_impact_pct": <how much the TOTAL target changes if this driver group deviates from base — NOT stackable across criteria in same group>,
      "price_impact_direction": "up" or "down_if_failed"
    }}
  ],

  "target_notes": "3-5 sentence explanation: (1) the derivation: what revenue, margin, and multiple assumptions produce the target price through the DCF engine, (2) WHEN this target is achievable (specific quarter/year), (3) what industry conditions must hold. Flag any assumption that deviates >20% from sector median with [DEVIATION] and justification."
}}

─── RULES ───

REVENUE RULE (CRITICAL):
  revenue_b must be ANNUAL revenue in billions, NOT quarterly.
  Use TRAILING TWELVE MONTHS (TTM = sum of last 4 reported quarters) as the anchor.
  TTM cancels seasonal patterns and is the Bloomberg/FactSet/Capital IQ standard.
  If management guides a quarterly run rate for a NON-SEASONAL business (quarterly
  revenue CV < 5%), annualizing ×4 is acceptable as a supplement.
  For SEASONAL businesses (retail, tax software, agriculture), NEVER use Q×4.
  Intuit Q3×4 overstates annual revenue by ~66%. Macy's Q4×4 overstates by ~41%.
  When in doubt, use TTM.

BOTTOM-UP DERIVATION RULE (CRITICAL):
  Do NOT start from a target price and reverse-engineer inputs to match.
  Instead, derive each input independently:
  1. Revenue: Start from TTM, apply growth rate grounded in guidance + consensus
  2. Margins: Start from current operating margin, justify any expansion/compression
  3. Multiple: Start from sector median, adjust for growth differential and quality
  4. Shares: Start from current diluted count, apply historical dilution rate
  Each deviation from the base rate requires explicit justification.
  The target price EMERGES from the inputs — it is not predetermined.

  PER-SHARE PRICE FORMULA (use this exact chain for each scenario):
    If method = "pe":
      Net Income = Revenue × op_margin × (1 − tax_rate)
      Price = Net Income × pe_multiple ÷ (shares_m / 1000)
    If method = "ps":
      Price = Revenue × ps_multiple ÷ (shares_m / 1000)
    ⚠️ shares_m is in MILLIONS. Divide by 1000 to convert to billions before dividing.
    Cross-check: does your scenario price × shares_m ≈ implied market cap? If not, fix it.

INDUSTRY & CYCLE AWARENESS (CRITICAL):
  Many stocks are driven by industry cycles, not just company execution.
  You MUST consider:
  - Where is the company in its industry cycle? (early, mid, peak, declining)
  - What EXTERNAL factors (supply/demand balance, competitor capacity expansion,
    commodity pricing, regulatory changes) could move the stock regardless of execution?
  - Is there a sector-level risk that could drag this stock down even if fundamentals hold?
  Include at least 2 criteria with variable="E" (External/Macro), covering:
  - Supply/demand dynamics for the company's key market
  - Competitor or sector-level risks (e.g. "DRAM oversupply doesn't trigger sector selloff")
  - Macro conditions (e.g. "AI capex sustained by 2+ hyperscalers")
  These should be "critical" or "important" weight with "down_if_failed" direction.

TIMELINE AWARENESS:
  - The timeline_years from the stock config tells you the investment horizon
  - For CYCLICAL companies (semis, commodities, energy): target should reflect the CURRENT
    cycle position, not a theoretical peak state years away. If the cycle peaks in 6-12 months,
    the target should reflect that — don't project a 3-year bull case.
  - For SECULAR GROWTH companies (SaaS, platform, AI infra): longer timelines are appropriate
    if the growth thesis is structural, not cyclical.
  - target_notes MUST specify WHEN the target is achievable (e.g. "achievable by Q4 FY2027")

SCENARIO RULES (CRITICAL):
  Probabilities must be STATE-CONTINGENT based on current conditions, not fixed ranges.
  Bear probability guidance by regime:
  - Late-cycle (falling PMI, curve inversion, peak multiples): 0.30-0.45
  - Mid-cycle (stable growth, normal multiples): 0.20-0.30
  - Early-cycle (trough valuations, improving fundamentals): 0.10-0.20
  For cyclical stocks, EVERY semiconductor upcycle since 1996 ended with 30%+ correction.
  Bear case must model what happens when the cycle turns, not just a token discount.
  Bull case should reflect specific upside catalysts, not base × 1.3.
  Avoid round probabilities (0.25, 0.35) — these are anchoring artifacts. Be precise.
  Scenarios must sum to probability 1.0.

CRITERIA MECE RULE:
  The 5 driver groups are: Revenue (R), Margins (M), Multiples (P),
  Capital Structure (S), External/Macro (E).
  Multiple criteria can map to the same group, but they describe DIFFERENT FACETS
  of that driver — they are NOT additive. Three criteria on Revenue collectively
  inform one revenue forecast, not three stacked +X% increments.
  price_impact_pct is the impact if the ENTIRE driver group deviates from base.

GENERAL:
- Generate 8-12 criteria covering driver groups R, M, P, S, and E
- At least 2 criteria must be "critical" weight
- At least 2 criteria must be External/Macro (variable="E")
- Each criterion must have a specific, measurable threshold AND timeframe in eval_hint
- If the company is pre-profit or high-growth with no meaningful earnings, use "ps" method
- For ps method, set pe_multiple to null and provide ps_multiple instead
- If using pe_multiple, it must correspond to Net Income (after interest and tax),
  NOT NOPAT. P/E is an equity-level multiple and must pair with equity-level earnings.
- Be specific with numbers — no placeholders or TBD values
- All financial figures (revenue, income, etc.) should be ANNUAL, not quarterly

POST-DERIVATION CHECK (do this AFTER completing the JSON above):
  The existing price hypothesis for this stock is {target_price_display}.
  If your independently-derived base case price diverges from this by more than 20%,
  add a "divergence_note" field to your JSON explaining which assumption drives the
  gap and whether your derivation or the prior hypothesis is more likely correct.
  Do NOT adjust your derived inputs to close the gap — the whole point is independent
  derivation. If your model says $800 and the hypothesis says $1500, report $800 and
  explain why.

OUTPUT SIZE RULES (CRITICAL — responses that exceed the token limit get truncated and fail):
- target_notes: MAX 3 sentences. No preambles, no restating what the JSON already shows.
- criteria detail: MAX 2 sentences per criterion.
- scenario trigger: MAX 2 sentences per scenario.
- valuation_justification: MAX 2 sentences.
- archetype justification: MAX 2 sentences.
- Do NOT include fields not in the schema above (no sensitivity_table, time_path,
  confidence_mapping, decision_framework, expected_value, or divergence_note unless
  the 20% divergence check actually triggers).
- Return ONLY the JSON object. No markdown, no commentary before or after.
"""


def generate_model_with_claude(
    ticker: str, name: str, sector: str, thesis: str,
    kill_condition: str, target_price: float, timeline: int,
    research: str, quant_data: dict | None = None,
    retry: bool = False,
) -> dict | None:
    """Use Claude to generate a complete target price model configuration.

    Returns a dict with the model config plus an extra '_gen_meta' key containing:
      tokens_used, repair_attempts, repair_method, archetype
    The '_gen_meta' key is stripped before saving to Supabase but used for observability.
    """
    if not ANTHROPIC_API_KEY:
        print(f"  [{ticker}] ANTHROPIC_API_KEY not set — cannot generate model")
        return None

    target_price_display = f"${target_price}" if target_price else "UNKNOWN — estimate a realistic 10x target from the research data"
    quant_facts = format_quant_facts(ticker, quant_data or {})

    prompt = MODEL_GEN_PROMPT.format(
        ticker=ticker,
        name=name,
        sector=sector,
        target_price_display=target_price_display,
        timeline=timeline,
        thesis=thesis or "High-growth company with potential for significant appreciation",
        kill_condition=kill_condition or "Fundamental thesis break — management missteps or market share loss",
        research=research[:6000],  # Trim to fit context
        quant_facts=quant_facts,
    )

    if retry:
        prompt = (
            "RETRY — your previous response was truncated. Be MAXIMALLY CONCISE. "
            "Every text field must be 1-2 sentences max. No extra fields.\n\n"
            + prompt
        )

    content = ""
    stop_reason = "unknown"
    tokens_used = 0
    repair_attempts = 0
    repair_method = None

    def _attach_meta(result: dict | None) -> dict | None:
        """Attach generation metadata to the result dict."""
        if result is None:
            return None
        archetype_info = result.get("archetype", {})
        arch_primary = archetype_info.get("primary") if isinstance(archetype_info, dict) else None
        result["_gen_meta"] = {
            "tokens_used": tokens_used,
            "repair_attempts": repair_attempts,
            "repair_method": repair_method,
            "archetype": arch_primary,
        }
        return result

    try:
        label = "Retrying" if retry else "Generating"
        print(f"  [{ticker}] {label} model via Claude (structured output)...")
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6" if retry else "claude-opus-4-6",
                "max_tokens": 32000,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
                # Structured Outputs — guarantees schema-conformant JSON
                "output_config": {
                    "format": {
                        "type": "json_schema",
                        "schema": MODEL_OUTPUT_SCHEMA,
                    },
                },
            },
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [{}])[0].get("text", "")
        stop_reason = data.get("stop_reason", "unknown")

        # Extract token usage from Claude API response
        usage = data.get("usage", {})
        tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        if stop_reason == "max_tokens":
            print(f"  [{ticker}] WARNING: response truncated (hit max_tokens)")

        # ── Primary parse — structured output should always be valid JSON ──
        try:
            result = json.loads(content)
            if result.get("model_defaults") and result.get("scenarios"):
                repair_method = "structured_output"
                return _attach_meta(result)
            else:
                print(f"  [{ticker}] Structured output parsed but missing required fields")
        except json.JSONDecodeError:
            print(f"  [{ticker}] UNEXPECTED: structured output was not valid JSON")

        # ── Legacy fallback — should rarely fire with structured outputs ──
        # Kept as a safety net; if this fires, it's a defect to investigate.
        repair_attempts += 1
        print(f"  [{ticker}] Falling back to legacy JSON repair (this is a defect — please investigate)")

        # Brace extraction + trailing comma fix
        first_brace = content.find('{')
        last_brace = content.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            extracted = content[first_brace:last_brace + 1]
            repaired = re.sub(r',\s*([}\]])', r'\1', extracted)
            try:
                repair_method = "legacy_brace_extraction"
                return _attach_meta(json.loads(repaired))
            except json.JSONDecodeError:
                pass

        # Truncation repair as last resort
        if stop_reason == "max_tokens":
            repair_attempts += 1
            repaired = repair_truncated_json(content)
            if repaired:
                try:
                    result = json.loads(repaired)
                    if result.get("model_defaults") and result.get("scenarios"):
                        repair_method = "legacy_truncation_repair"
                        return _attach_meta(result)
                except json.JSONDecodeError:
                    pass

        # Retry with compact prompt if truncated
        if stop_reason == "max_tokens" and not retry:
            print(f"  [{ticker}] Retrying with compact prompt...")
            return generate_model_with_claude(
                ticker, name, sector, thesis, kill_condition,
                target_price, timeline,
                research[:3000],
                quant_data,
                retry=True,
            )

        print(f"  [{ticker}] All JSON parse attempts failed")
        print(f"  Start: {content[:200]}")
        print(f"  End: ...{content[-200:]}")
        return None

    except json.JSONDecodeError as e:
        print(f"  [{ticker}] Claude returned non-JSON: {e}")
        print(f"  Raw: {content[:300]}")
        return None
    except Exception as e:
        print(f"  [{ticker}] Claude API error: {e}")
        return None


def update_stock_in_supabase(ticker: str, model_config: dict, research_text: str = "", quant_data: dict | None = None, stock_name: str = "") -> bool:
    """Upsert the stock's model config in Supabase, including cached research."""
    try:
        from supabase_helper import get_client
        from datetime import datetime, timezone
        sb = get_client()

        update = {
            "valuation_method": model_config.get("valuation_method", "pe"),
            "model_defaults": model_config.get("model_defaults", {}),
            "scenarios": model_config.get("scenarios", {}),
            "criteria": model_config.get("criteria", []),
            "target_notes": model_config.get("target_notes", ""),
            "archetype": model_config.get("archetype", {}),
        }

        # Save thesis, sector, kill_condition if generated by Claude
        if model_config.get("thesis"):
            update["thesis"] = model_config["thesis"]
        if model_config.get("sector") and model_config["sector"] != "Unknown":
            update["sector"] = model_config["sector"]
        if model_config.get("kill_condition"):
            update["kill_condition"] = model_config["kill_condition"]

        # Derive target_price from base scenario
        base_price = model_config.get("scenarios", {}).get("base", {}).get("price")
        if base_price and isinstance(base_price, (int, float)) and base_price > 0:
            update["target_price"] = round(float(base_price), 2)

        # Cache research data so models are auditable and reproducible
        if research_text or quant_data:
            update["research_cache"] = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "perplexity_research": research_text[:10000] if research_text else "",
                "quant_snapshot": quant_data or {},
                "sources": ["Quant Scout (financials)", "Perplexity Sonar (guidance/catalysts)"],
            }

        # Ensure ticker + name + active are present for upsert (in case row doesn't exist yet)
        update["ticker"] = ticker
        update["name"] = stock_name or model_config.get("name") or ticker
        update.setdefault("active", True)

        # Try upsert; if column doesn't exist, strip it and retry (loop for multiple missing)
        stripped = []
        for attempt in range(5):  # max 5 missing columns before giving up
            try:
                resp = sb.table("stocks").upsert(update, on_conflict="ticker").execute()
                if stripped:
                    print(f"  [{ticker}] Saved (stripped missing columns: {', '.join(stripped)})")
                return bool(resp.data)
            except Exception as col_err:
                err_msg = str(col_err)
                if "column" in err_msg:
                    import re as _re
                    match = _re.search(r"['\"](\w+)['\"].*column", err_msg) or _re.search(r"column[^'\"]*['\"](\w+)['\"]", err_msg)
                    if match and match.group(1) in update:
                        missing_col = match.group(1)
                        stripped.append(missing_col)
                        print(f"  [{ticker}] Column '{missing_col}' missing in DB — stripping")
                        update.pop(missing_col)
                        if not update:
                            print(f"  [{ticker}] No columns left to save!")
                            return False
                        continue
                raise

    except Exception as e:
        print(f"  [{ticker}] Supabase update failed: {e}")
        return False


def process_stock(stock: dict, metrics=None) -> dict | None:
    """Full pipeline for one stock: load quant -> research -> generate -> save.

    Args:
        stock: Stock dict from watchlist/DB.
        metrics: Optional PipelineMetrics instance for observability.
    """
    ticker = stock["ticker"]
    name = stock["name"]
    sector = stock.get("sector", "Unknown")
    thesis = stock.get("thesis", "")
    kill_condition = stock.get("kill_condition", "")
    target = stock.get("target", {})
    target_price = (target.get("price") or 0) if target else 0
    timeline = target.get("timeline_years", 3) if target else 3

    if not target_price:
        print(f"  [{ticker}] No target price set — will estimate from research")

    print(f"\n  {'='*55}")
    print(f"  MODEL GENERATOR: {ticker} ({name}) → ${target_price}")
    print(f"  {'='*55}")

    # Stage 0: Load quant data (hard financials from quant scout — ground truth)
    quant_data = load_quant_data(ticker)
    if quant_data:
        price = quant_data.get("price") or 0
        mcap = quant_data.get("market_cap_b") or 0
        print(f"  Stage 0: Loaded quant scout data — ${price:.2f}, ${mcap:.1f}B market cap")
    else:
        print(f"  Stage 0: No quant scout data available — Perplexity will be primary source")

    # Stage 1: Research (forward-looking only — guidance, catalysts, industry)
    print(f"  Stage 1: Researching forward guidance via Perplexity...")
    research = research_financials(ticker, name, sector)
    if not research and not quant_data:
        print(f"  [{ticker}] No research data AND no quant data — aborting")
        return None

    # Stage 2: Generate model via Claude (with quant facts + Perplexity research)
    # Self-consistency: sample N times if SELF_CONSISTENCY_N > 1
    from self_consistency import sample_model_generation, DEFAULT_N as SC_N
    gen_start = time.monotonic()

    def _generate():
        return generate_model_with_claude(
            ticker, name, sector, thesis, kill_condition,
            target_price, timeline, research, quant_data,
        )

    if SC_N > 1:
        print(f"  Stage 2: Generating model via Claude (N={SC_N} self-consistency samples)...")
        sc_result = sample_model_generation(_generate, n=SC_N)
        model_config = sc_result.best_result
        if sc_result.n_success > 1:
            print(f"  {sc_result.summary()}")
            # Attach consistency metadata to the model config
            if model_config:
                model_config["_consistency"] = {
                    "n_samples": sc_result.n_samples,
                    "n_success": sc_result.n_success,
                    "mean_prices": sc_result.mean_prices,
                    "stderr_prices": sc_result.stderr_prices,
                    "high_variance": sc_result.high_variance,
                    "archetype_votes": sc_result.archetype_votes,
                }
    else:
        model_config = _generate()

    gen_duration = time.monotonic() - gen_start

    # Extract and strip generation metadata before any further processing
    gen_meta = {}
    if model_config and "_gen_meta" in model_config:
        gen_meta = model_config.pop("_gen_meta")
    # Strip consistency metadata (observability only, not saved to DB)
    if model_config and "_consistency" in model_config:
        consistency_meta = model_config.pop("_consistency")
        gen_meta["consistency"] = consistency_meta

    if not model_config:
        # Record failed generation in metrics
        if metrics:
            try:
                metrics.record_model_gen(
                    ticker=ticker, duration_s=gen_duration, success=False,
                    tokens_used=gen_meta.get("tokens_used", 0),
                    repair_attempts=gen_meta.get("repair_attempts", 0),
                    repair_method=gen_meta.get("repair_method"),
                    archetype=None,
                )
            except Exception:
                pass
        print(f"  [{ticker}] ✗ Model generation failed")
        return None

    # Record successful generation in metrics
    if metrics:
        try:
            metrics.record_model_gen(
                ticker=ticker, duration_s=gen_duration, success=True,
                tokens_used=gen_meta.get("tokens_used", 0),
                repair_attempts=gen_meta.get("repair_attempts", 0),
                repair_method=gen_meta.get("repair_method"),
                archetype=gen_meta.get("archetype"),
            )
        except Exception:
            pass

    # Show what Claude produced
    arch = model_config.get("archetype", {})
    arch_primary = arch.get("primary", "?") if isinstance(arch, dict) else "?"
    arch_secondary = arch.get("secondary") if isinstance(arch, dict) else None
    val_method = model_config.get("valuation_method", "?")
    scenarios = model_config.get("scenarios", {})
    base_price = scenarios.get("base", {}).get("price", 0)
    bear_price = scenarios.get("bear", {}).get("price", 0)
    bull_price = scenarios.get("bull", {}).get("price", 0)
    n_criteria = len(model_config.get("criteria", []))
    arch_str = arch_primary.upper() + (f" + {arch_secondary}" if arch_secondary else "")
    print(f"  Stage 2: ✓ Claude response parsed")
    print(f"    Archetype: {arch_str}  |  Method: {val_method}  |  Criteria: {n_criteria}")
    print(f"    Scenarios: bear ${bear_price:,.0f} / base ${base_price:,.0f} / bull ${bull_price:,.0f}")

    # Stage 3: Save to Supabase (with cached research for auditability)
    print(f"  Stage 3: Saving to Supabase...")
    if update_stock_in_supabase(ticker, model_config, research, quant_data, stock_name=name):
        print(f"  [{ticker}] Model saved successfully!")
    else:
        print(f"  [{ticker}] Supabase save failed — dumping to stdout")
        print(json.dumps(model_config, indent=2))

    # Stage 4: Archetype stability tracking (4-run lookback window)
    archetype = model_config.get("archetype", {})
    if archetype.get("primary"):
        stability = check_archetype_stability(ticker, archetype)
        model_config["archetype_stability"] = stability
    else:
        print(f"  [{ticker}] No archetype in model output — Claude may not have included it")

    # Print summary
    defaults = model_config.get("model_defaults", {})
    scenarios = model_config.get("scenarios", {})
    criteria = model_config.get("criteria", [])
    method = model_config.get("valuation_method", "pe")

    arch_primary = archetype.get("primary", "?")
    arch_secondary = archetype.get("secondary")

    print(f"\n  Model Summary:")
    print(f"    Archetype: {arch_primary.upper()}{f' + {arch_secondary}' if arch_secondary else ''}")
    print(f"    Method: {method.upper()}")
    print(f"    Revenue: ${defaults.get('revenue_b', '?')}B | Margin: {defaults.get('op_margin', '?')}")
    print(f"    Multiple: {defaults.get('pe_multiple') or defaults.get('ps_multiple', '?')}x")
    print(f"    Scenarios: Bull ${scenarios.get('bull', {}).get('price', '?')} | Base ${scenarios.get('base', {}).get('price', '?')} | Bear ${scenarios.get('bear', {}).get('price', '?')}")
    print(f"    Criteria: {len(criteria)} generated")
    print(f"    Notes: {model_config.get('target_notes', '')[:100]}...")

    return model_config


ARCHETYPE_LOOKBACK = 4  # rolling window for stability tracking


def check_archetype_stability(ticker: str, current_archetype: dict) -> dict:
    """Track archetype classification stability over a rolling 4-run window.

    Returns:
      {
        "current": "garp",
        "history": ["garp", "cyclical", "garp", "garp"],
        "pattern": "stable" | "regime_change" | "unstable",
        "auto_hybrid": false,
        "note": "..."
      }

    Patterns:
      - stable: all runs in the window agree (or only 1 change that stuck)
      - regime_change: classification was consistent, then changed and stayed
        changed — the stock's narrative is shifting (real signal)
      - unstable: flipping back and forth — auto-flag as hybrid because the
        boundary is genuinely ambiguous for this stock
    """
    primary = (current_archetype.get("primary") or "garp").lower()

    # Load archetype history from Supabase
    history: list[str] = []
    try:
        from supabase_helper import get_client
        sb = get_client()
        resp = (
            sb.table("archetype_history")
            .select("archetype")
            .eq("ticker", ticker.upper())
            .order("created_at", desc=True)
            .limit(ARCHETYPE_LOOKBACK)
            .execute()
        )
        if resp.data:
            history = [r["archetype"] for r in reversed(resp.data)]
    except Exception as e:
        # Table may not exist yet — that's fine, treat as no history
        print(f"  [{ticker}] Archetype history lookup: {e} (OK if table doesn't exist yet)")

    # Save current classification
    try:
        from supabase_helper import get_client
        from datetime import datetime, timezone
        sb = get_client()
        sb.table("archetype_history").insert({
            "ticker": ticker.upper(),
            "archetype": primary,
            "secondary": current_archetype.get("secondary"),
            "justification": (current_archetype.get("justification") or "")[:500],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        print(f"  [{ticker}] Archetype history save: {e} (non-fatal)")

    # Determine pattern
    if len(history) < 2:
        return {
            "current": primary,
            "history": history + [primary],
            "pattern": "stable",
            "auto_hybrid": False,
            "note": "Insufficient history for stability analysis",
        }

    window = history[-(ARCHETYPE_LOOKBACK - 1):] + [primary]
    unique = set(window)

    if len(unique) == 1:
        pattern = "stable"
        auto_hybrid = False
        note = f"Consistent {primary} classification across {len(window)} runs"
    else:
        # Check if it's a regime change (old values agree, then switch to new)
        # vs. unstable (alternating back and forth)
        changes = sum(1 for i in range(1, len(window)) if window[i] != window[i - 1])
        if changes == 1:
            # Single transition — regime change
            pattern = "regime_change"
            auto_hybrid = False
            old = window[0]
            note = f"Classification shifted from {old} to {primary} — market narrative may be changing"
        else:
            # Multiple flips — genuinely ambiguous boundary
            pattern = "unstable"
            auto_hybrid = True
            archetypes_seen = sorted(unique)
            note = f"Classification alternating between {' and '.join(archetypes_seen)} — auto-flagged as hybrid"

    result = {
        "current": primary,
        "history": window,
        "pattern": pattern,
        "auto_hybrid": auto_hybrid,
        "note": note,
    }

    emoji = {"stable": "\u2705", "regime_change": "\u26A0\uFE0F", "unstable": "\U0001F504"}
    print(f"    {emoji.get(pattern, '?')} Archetype stability: {pattern} — {note}")

    return result


def generate_for_ticker(ticker: str, target_override: float | None = None, metrics=None) -> dict | None:
    """Generate model for a single ticker — callable from run_pipeline.py or external scripts."""
    watchlist = get_watchlist()
    stock = next((s for s in watchlist if s["ticker"].upper() == ticker.upper()), None)

    if not stock:
        # Stock might be newly added and not have full data yet — build minimal entry
        try:
            from supabase_helper import get_stock
            db_row = get_stock(ticker.upper())
            if db_row:
                stock = {
                    "ticker": db_row["ticker"],
                    "name": db_row["name"],
                    "sector": db_row.get("sector", "Unknown"),
                    "thesis": db_row.get("thesis", ""),
                    "kill_condition": db_row.get("kill_condition", ""),
                    "target": {
                        "price": db_row.get("target_price") or 0,
                        "timeline_years": db_row.get("timeline_years", 3),
                    },
                }
        except Exception:
            pass

    if not stock:
        print(f"  [{ticker}] Not found in watchlist or DB — cannot generate model")
        return None

    if target_override:
        stock.setdefault("target", {})["price"] = target_override

    return process_stock(stock, metrics=metrics)


def main():
    print("=" * 60)
    print("TARGET PRICE MODEL GENERATOR (Perplexity + Claude)")
    print("=" * 60)

    if not PERPLEXITY_API_KEY:
        print("\n  PERPLEXITY_API_KEY not set — needed for research")
        return

    if not ANTHROPIC_API_KEY:
        print("\n  ANTHROPIC_API_KEY not set — needed for model generation")
        print("  This script requires Claude to generate structured model configs.")
        return

    # Parse args
    run_all = "--all" in sys.argv
    specific_ticker = None
    target_override = None

    for i, arg in enumerate(sys.argv):
        if arg == "--ticker" and i + 1 < len(sys.argv):
            specific_ticker = sys.argv[i + 1].upper()
        if arg == "--target" and i + 1 < len(sys.argv):
            target_override = float(sys.argv[i + 1])

    watchlist = get_watchlist()

    if specific_ticker:
        watchlist = [s for s in watchlist if s["ticker"] == specific_ticker]
        if not watchlist:
            print(f"\n  Ticker {specific_ticker} not found in watchlist")
            return
        if target_override:
            watchlist[0].setdefault("target", {})["price"] = target_override
    elif not run_all:
        print("\n  Usage:")
        print("    python generate_model.py --ticker LITE")
        print("    python generate_model.py --ticker LITE --target 1500")
        print("    python generate_model.py --all")
        return

    # Parallelism: --parallel N (default 5 for --all, 1 for single ticker)
    max_workers = 1 if specific_ticker else 5
    for i, arg in enumerate(sys.argv):
        if arg == "--parallel" and i + 1 < len(sys.argv):
            max_workers = max(1, min(6, int(sys.argv[i + 1])))

    print(f"\n  Generating models for {len(watchlist)} stocks ({max_workers} parallel)")
    print(f"  Research: Perplexity Sonar")
    print(f"  Analysis: Claude Opus")
    print("-" * 60)

    results = []
    if max_workers == 1:
        # Sequential — simpler output, no interleaving
        for stock in watchlist:
            result = process_stock(stock)
            if result:
                results.append(result)
    else:
        # Parallel — run stocks concurrently with thread pool
        futures = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for stock in watchlist:
                f = pool.submit(process_stock, stock)
                futures[f] = stock["ticker"]
            for f in as_completed(futures):
                ticker = futures[f]
                try:
                    result = f.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    print(f"  [{ticker}] ✗ Unhandled error: {e}")

    print(f"\n{'='*60}")
    print(f"  COMPLETE: Generated {len(results)}/{len(watchlist)} models")
    print(f"{'='*60}")

    return results


if __name__ == "__main__":
    main()
