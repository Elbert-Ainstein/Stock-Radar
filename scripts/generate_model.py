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
import requests
from pathlib import Path
from utils import load_env, get_watchlist, timestamp

load_env()

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CONFIG_DIR = Path(__file__).parent.parent / "config"
ANALYST_PROMPT_PATH = CONFIG_DIR / "analyst_prompt.md"


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

    This provides hard financial facts from yfinance that should NOT be
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
    These numbers come from yfinance and should be treated as ground truth."""
    if not quant_data:
        return f"[No yfinance data available for {ticker} — rely on Perplexity research below]"

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

    # TTM revenue: prefer direct yfinance value, fall back to market_cap / P/S
    ttm_rev = quant_data.get("ttm_revenue")
    current_rev_b = ttm_rev if ttm_rev and ttm_rev > 0 else (round(market_cap_b / ps_ratio, 2) if ps_ratio and ps_ratio > 0 else None)
    rev_source = "TTM" if (ttm_rev and ttm_rev > 0) else "derived from mktcap/PS"

    # Shares: prefer direct yfinance value, fall back to market_cap / price
    shares_direct = quant_data.get("shares_outstanding_m")
    shares_m = shares_direct if shares_direct and shares_direct > 0 else (round((market_cap_b * 1000) / price) if price > 0 else None)
    shares_source = "reported" if (shares_direct and shares_direct > 0) else "derived from mktcap/price"

    lines = [
        f"HARD FINANCIAL DATA (from yfinance — treat as ground truth, do NOT override with estimates):",
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
    Hard financials (revenue, margins, P/E) come from yfinance via quant scout.
    Perplexity fills in: guidance, analyst targets, catalysts, industry dynamics."""
    if not PERPLEXITY_API_KEY:
        return ""

    # Focus Perplexity on what yfinance CAN'T provide
    queries = [
        f"{ticker} {name} FY2025 FY2026 FY2027 revenue guidance analyst consensus estimates forward outlook",
        f"{ticker} {name} management guidance targets long-term margin goals TAM market share competitive moat",
        f"{ticker} {name} bull case bear case risks catalysts price target analyst ratings recent upgrades downgrades",
        # Industry cycle — critical for cyclical stocks
        f"{sector} industry supply demand cycle outlook 2026 2027 pricing trends capacity expansion risks competitors",
    ]

    research_parts = []
    for q in queries:
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
                        {
                            "role": "system",
                            "content": (
                                "You are an equity research analyst. Provide factual, data-rich responses "
                                "with specific numbers, percentages, and dollar amounts. "
                                "Focus on FORWARD estimates, guidance, catalysts, and industry dynamics. "
                                "Do NOT repeat basic financial data like current revenue or margins — "
                                "those are already available from another source. "
                                "No disclaimers."
                            ),
                        },
                        {"role": "user", "content": q},
                    ],
                    "max_tokens": 800,
                    "temperature": 0.1,
                    "web_search": True,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            research_parts.append(content)
        except Exception as e:
            print(f"    Research query failed: {e}")
        time.sleep(1.5)

    return "\n\n---\n\n".join(research_parts)


MODEL_GEN_PROMPT = """You are a senior equity research analyst building a target price model.

GUIDELINE:
{guideline}

COMPANY: {ticker} ({name}), {sector} sector
INVESTMENT HORIZON: {timeline} years
CURRENT THESIS: {thesis}
KILL CONDITION: {kill_condition}

{quant_facts}

FORWARD-LOOKING RESEARCH (from Perplexity — guidance, analyst targets, catalysts, industry dynamics):
{research}

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
"""


def generate_model_with_claude(
    ticker: str, name: str, sector: str, thesis: str,
    kill_condition: str, target_price: float, timeline: int,
    research: str, quant_data: dict | None = None,
) -> dict | None:
    """Use Claude to generate a complete target price model configuration."""
    if not ANTHROPIC_API_KEY:
        print(f"  [{ticker}] ANTHROPIC_API_KEY not set — cannot generate model")
        return None

    guideline = load_analyst_guideline()

    target_price_display = f"${target_price}" if target_price else "UNKNOWN — estimate a realistic 10x target from the research data"
    quant_facts = format_quant_facts(ticker, quant_data or {})

    prompt = MODEL_GEN_PROMPT.format(
        guideline=guideline,
        ticker=ticker,
        name=name,
        sector=sector,
        target_price_display=target_price_display,
        timeline=timeline,
        thesis=thesis or "High-growth company with potential for significant appreciation",
        kill_condition=kill_condition or "Fundamental thesis break — management missteps or market share loss",
        research=research[:8000],  # Trim to fit context
        quant_facts=quant_facts,
    )

    try:
        print(f"  [{ticker}] Generating model via Claude...")
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-6",
                "max_tokens": 4000,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [{}])[0].get("text", "")

        # Parse JSON — robust extraction handles preambles/postambles
        clean = content.strip()
        # First try: strip markdown fences
        clean = re.sub(r'^```(?:json)?\s*', '', clean)
        clean = re.sub(r'\s*```$', '', clean)
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # Fallback: find first '{' and last '}' — handles Claude adding text
            first_brace = content.find('{')
            last_brace = content.rfind('}')
            if first_brace != -1 and last_brace > first_brace:
                return json.loads(content[first_brace:last_brace + 1])

    except json.JSONDecodeError as e:
        print(f"  [{ticker}] Claude returned non-JSON: {e}")
        print(f"  Raw: {content[:300]}")
        return None
    except Exception as e:
        print(f"  [{ticker}] Claude API error: {e}")
        return None


def update_stock_in_supabase(ticker: str, model_config: dict, research_text: str = "", quant_data: dict | None = None) -> bool:
    """Update the stock's model config in Supabase, including cached research."""
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
        }

        # Cache research data so models are auditable and reproducible
        if research_text or quant_data:
            update["research_cache"] = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "perplexity_research": research_text[:10000] if research_text else "",
                "quant_snapshot": quant_data or {},
                "sources": ["yfinance (financials)", "Perplexity Sonar (guidance/catalysts)"],
            }

        resp = sb.table("stocks").update(update).eq("ticker", ticker).execute()
        return bool(resp.data)
    except Exception as e:
        print(f"  [{ticker}] Supabase update failed: {e}")
        return False


def process_stock(stock: dict) -> dict | None:
    """Full pipeline for one stock: load quant → research → generate → save."""
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

    # Stage 0: Load quant data (hard financials from yfinance — ground truth)
    quant_data = load_quant_data(ticker)
    if quant_data:
        price = quant_data.get("price") or 0
        mcap = quant_data.get("market_cap_b") or 0
        print(f"  Stage 0: Loaded yfinance data — ${price:.2f}, ${mcap:.1f}B market cap")
    else:
        print(f"  Stage 0: No yfinance data available — Perplexity will be primary source")

    # Stage 1: Research (forward-looking only — guidance, catalysts, industry)
    print(f"  Stage 1: Researching forward guidance via Perplexity...")
    research = research_financials(ticker, name, sector)
    if not research and not quant_data:
        print(f"  [{ticker}] No research data AND no quant data — aborting")
        return None

    # Stage 2: Generate model via Claude (with quant facts + Perplexity research)
    model_config = generate_model_with_claude(
        ticker, name, sector, thesis, kill_condition,
        target_price, timeline, research, quant_data,
    )

    if not model_config:
        print(f"  [{ticker}] Model generation failed")
        return None

    # Stage 3: Save to Supabase (with cached research for auditability)
    print(f"  [{ticker}] Saving model config + research cache to Supabase...")
    if update_stock_in_supabase(ticker, model_config, research, quant_data):
        print(f"  [{ticker}] Model saved successfully!")
    else:
        print(f"  [{ticker}] Supabase save failed — dumping to stdout")
        print(json.dumps(model_config, indent=2))

    # Print summary
    defaults = model_config.get("model_defaults", {})
    scenarios = model_config.get("scenarios", {})
    criteria = model_config.get("criteria", [])
    method = model_config.get("valuation_method", "pe")

    print(f"\n  Model Summary:")
    print(f"    Method: {method.upper()}")
    print(f"    Revenue: ${defaults.get('revenue_b', '?')}B | Margin: {defaults.get('op_margin', '?')}")
    print(f"    Multiple: {defaults.get('pe_multiple') or defaults.get('ps_multiple', '?')}x")
    print(f"    Scenarios: Bull ${scenarios.get('bull', {}).get('price', '?')} | Base ${scenarios.get('base', {}).get('price', '?')} | Bear ${scenarios.get('bear', {}).get('price', '?')}")
    print(f"    Criteria: {len(criteria)} generated")
    print(f"    Notes: {model_config.get('target_notes', '')[:100]}...")

    return model_config


def generate_for_ticker(ticker: str, target_override: float | None = None) -> dict | None:
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

    return process_stock(stock)


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

    print(f"\n  Generating models for {len(watchlist)} stocks")
    print(f"  Research: Perplexity Sonar")
    print(f"  Analysis: Claude Sonnet")
    print("-" * 60)

    results = []
    for stock in watchlist:
        result = process_stock(stock)
        if result:
            results.append(result)
        time.sleep(3)  # Rate limiting between stocks

    print(f"\n{'='*60}")
    print(f"  COMPLETE: Generated {len(results)}/{len(watchlist)} models")
    print(f"{'='*60}")

    return results


if __name__ == "__main__":
    main()
