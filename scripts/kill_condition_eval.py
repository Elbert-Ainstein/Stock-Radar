#!/usr/bin/env python3
"""
kill_condition_eval.py — Evaluate whether a stock's kill condition is approaching or triggered.

Each stock in the watchlist has a kill_condition: a plain-English description of the
scenario that would break the investment thesis. This module takes that text plus the
current signals/quant data and asks Claude to evaluate the status.

Output per stock:
  {
    "status": "safe" | "warning" | "triggered",
    "confidence": 0.0-1.0,
    "reasoning": "...",
    "evidence": ["signal 1", "signal 2"],
    "checked_at": "2026-04-20T..."
  }

Usage:
    from kill_condition_eval import evaluate_kill_condition
    result = evaluate_kill_condition(
        ticker="AMD",
        kill_condition="Instinct GPU revenue stalls below $10B...",
        quant_data={...},
        signals=[...],
        news_data={...},
    )
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-opus-4-6"
REQUEST_TIMEOUT = 30

_EVAL_PROMPT = """\
You are a risk analyst evaluating whether a stock's investment kill condition is being triggered.

STOCK: {ticker}
KILL CONDITION: {kill_condition}

CURRENT DATA:
- Price: ${price}
- Market cap: ${market_cap_b:.1f}B
- Revenue growth YoY: {rev_growth}%
- Operating margin: {op_margin}%
- Earnings growth: {earnings_growth}%

RECENT NEWS/SIGNALS:
{signals_summary}

TASK: Evaluate whether the kill condition above is currently:
- "safe" — no evidence the condition is materializing
- "warning" — early signs or partial evidence that it COULD trigger within 1-2 quarters
- "triggered" — clear evidence the condition has been met or is actively materializing NOW

Respond with ONLY valid JSON (no markdown, no explanation outside the JSON):
{{
  "status": "safe" | "warning" | "triggered",
  "confidence": <0.0-1.0 how confident you are in this assessment>,
  "reasoning": "<2-3 sentences explaining your assessment>",
  "evidence": ["<specific data point or signal supporting your assessment>", ...]
}}
"""


def evaluate_kill_condition(
    ticker: str,
    kill_condition: str,
    quant_data: dict | None = None,
    signals: list[dict] | None = None,
    news_data: dict | None = None,
) -> dict:
    """Evaluate a single stock's kill condition against current data.

    Returns a structured assessment dict. On failure, returns a safe-default
    with a note about the failure — never raises.
    """
    if not kill_condition or not kill_condition.strip():
        return {
            "status": "safe",
            "confidence": 0.0,
            "reasoning": "No kill condition defined for this stock.",
            "evidence": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    if not ANTHROPIC_API_KEY:
        return {
            "status": "safe",
            "confidence": 0.0,
            "reasoning": "Kill condition evaluation requires ANTHROPIC_API_KEY.",
            "evidence": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    quant_data = quant_data or {}
    signals = signals or []
    news_data = news_data or {}

    # Build a compact summary of recent signals for the prompt
    signal_lines = []
    for s in signals[:15]:  # Cap at 15 to stay within prompt limits
        scout = s.get("scout", "?")
        signal = s.get("signal", "neutral")
        summary = (s.get("summary") or "")[:200]
        if summary:
            signal_lines.append(f"  [{scout}] ({signal}) {summary}")
    if news_data.get("headlines"):
        for h in news_data["headlines"][:5]:
            signal_lines.append(f"  [News] {h}")
    if not signal_lines:
        signal_lines.append("  (No recent signals available)")

    prompt = _EVAL_PROMPT.format(
        ticker=ticker,
        kill_condition=kill_condition,
        price=quant_data.get("price", "?"),
        market_cap_b=quant_data.get("market_cap_b", 0) or 0,
        rev_growth=quant_data.get("revenue_growth_pct", "?"),
        op_margin=quant_data.get("operating_margin_pct", "?"),
        earnings_growth=quant_data.get("earnings_growth_pct", "?"),
        signals_summary="\n".join(signal_lines),
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
                "max_tokens": 500,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [{}])[0].get("text", "")

        # Clean markdown fences if present
        clean = re.sub(r'^```(?:json)?\s*', '', content.strip())
        clean = re.sub(r'\s*```$', '', clean)
        parsed = json.loads(clean)

        status = parsed.get("status", "safe")
        if status not in ("safe", "warning", "triggered"):
            status = "safe"

        return {
            "status": status,
            "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            "reasoning": str(parsed.get("reasoning", ""))[:500],
            "evidence": [str(e)[:200] for e in (parsed.get("evidence") or [])[:5]],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        print(f"  [{ticker}] Kill condition eval failed: {e}")
        return {
            "status": "safe",
            "confidence": 0.0,
            "reasoning": f"Evaluation failed: {e}",
            "evidence": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


def evaluate_watchlist_kill_conditions(
    watchlist: list[dict],
    all_signals: dict[str, list[dict]],
    all_quant: dict[str, dict],
) -> dict[str, dict]:
    """Evaluate kill conditions for all stocks in the watchlist.

    Args:
        watchlist: list of stock config dicts from get_watchlist()
        all_signals: {ticker: [signal_dicts]} from the current run
        all_quant: {ticker: quant_data_dict} from the current run

    Returns:
        {ticker: evaluation_dict}
    """
    results = {}
    for stock in watchlist:
        ticker = stock.get("ticker", "")
        kill_condition = stock.get("kill_condition", "")
        if not kill_condition:
            continue

        quant = all_quant.get(ticker, {})
        sigs = all_signals.get(ticker, [])

        # Extract news data from signals if present
        news_data = {}
        for s in sigs:
            if (s.get("scout") or "").lower() == "news":
                news_data = s.get("data", {})
                break

        print(f"  [{ticker}] Evaluating kill condition...")
        result = evaluate_kill_condition(
            ticker=ticker,
            kill_condition=kill_condition,
            quant_data=quant,
            signals=sigs,
            news_data=news_data,
        )
        results[ticker] = result

        status_emoji = {"safe": "✅", "warning": "⚠️", "triggered": "🚨"}.get(result["status"], "?")
        print(f"    {status_emoji} {result['status']} (conf: {result['confidence']:.0%}) — {result['reasoning'][:100]}")

    return results


if __name__ == "__main__":
    # Quick test with AMD's kill condition
    from utils import load_env
    load_env()

    result = evaluate_kill_condition(
        ticker="AMD",
        kill_condition="Instinct GPU revenue stalls below $10B annual run rate by end of FY2026, AND server CPU share gains plateau or reverse for two consecutive quarters.",
        quant_data={"price": 104, "market_cap_b": 168, "revenue_growth_pct": 34, "operating_margin_pct": 5.4, "earnings_growth_pct": 25},
    )
    print(json.dumps(result, indent=2))
