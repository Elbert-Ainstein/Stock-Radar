#!/usr/bin/env python3
"""
research_memo.py — Auto-generate a 2-minute research memo per stock.

Produces a concise, actionable memo that covers:
  1. What the company does (1 sentence)
  2. Why it's on the watchlist (thesis)
  3. Key numbers (revenue, margins, valuation)
  4. Bull/base/bear scenarios with probabilities
  5. Top 3 criteria to watch
  6. Kill condition
  7. Model confidence (if self-consistency data available)

Output: Markdown file per stock in data/memos/, plus a combined daily digest.

Usage:
    python research_memo.py --ticker LITE          # Single stock
    python research_memo.py --all                  # All watchlist
    python research_memo.py --digest               # Combined daily digest
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_env, get_watchlist

load_env()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMO_DIR = DATA_DIR / "memos"
MEMO_DIR.mkdir(parents=True, exist_ok=True)


def load_stock_data(ticker: str) -> dict | None:
    """Load model data for a stock from Supabase."""
    try:
        from supabase_helper import get_stock
        return get_stock(ticker)
    except Exception as e:
        print(f"  [{ticker}] Could not load from Supabase: {e}")
        return None


def generate_memo(stock: dict) -> str:
    """Generate a 2-minute research memo as Markdown."""
    ticker = stock.get("ticker", "???")
    name = stock.get("name", "Unknown")
    sector = stock.get("sector", "Unknown")
    thesis = stock.get("thesis", "No thesis available.")
    kill_condition = stock.get("kill_condition", "Not specified.")

    # Model data
    model = stock.get("model_defaults") or {}
    scenarios = stock.get("scenarios") or {}
    criteria = stock.get("criteria") or []
    archetype = stock.get("archetype") or {}
    valuation_method = stock.get("valuation_method", "pe")
    target_price = stock.get("target_price")
    target_notes = stock.get("target_notes", "")

    # Extract scenario data
    bull = scenarios.get("bull", {})
    base = scenarios.get("base", {})
    bear = scenarios.get("bear", {})

    # Current price from research cache if available
    cache = stock.get("research_cache") or {}
    quant = cache.get("quant_snapshot") or {}
    current_price = quant.get("price", 0)
    market_cap_b = quant.get("market_cap_b", 0)

    # Archetype info
    arch_primary = archetype.get("primary", "unclassified") if isinstance(archetype, dict) else "unclassified"
    arch_secondary = archetype.get("secondary") if isinstance(archetype, dict) else None
    arch_just = archetype.get("justification", "") if isinstance(archetype, dict) else ""

    # Model defaults for key metrics display
    revenue_b = model.get("revenue_b", 0)
    op_margin = model.get("op_margin", 0)
    pe = model.get("pe_multiple")
    ps = model.get("ps_multiple")
    shares_m = model.get("shares_m", 0)

    # Build the memo
    lines = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines.append(f"# {ticker} — {name}")
    lines.append(f"*{sector} | {arch_primary.upper()}"
                 + (f" / {arch_secondary}" if arch_secondary else "")
                 + f" | Generated {now}*")
    lines.append("")

    # ── Thesis ──
    lines.append("## Thesis")
    lines.append(thesis)
    lines.append("")

    # ── Key Numbers ──
    lines.append("## Key Numbers")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    if current_price:
        lines.append(f"| Current Price | ${current_price:,.2f} |")
    if market_cap_b:
        lines.append(f"| Market Cap | ${market_cap_b:,.1f}B |")
    if revenue_b:
        lines.append(f"| Revenue (model) | ${revenue_b:,.1f}B |")
    if op_margin:
        lines.append(f"| Op Margin (target) | {op_margin*100:.0f}% |")
    if valuation_method == "pe" and pe:
        lines.append(f"| P/E Multiple | {pe:.0f}x |")
    elif valuation_method == "ps" and ps:
        lines.append(f"| P/S Multiple | {ps:.1f}x |")
    if shares_m:
        lines.append(f"| Shares (diluted) | {shares_m:,.0f}M |")
    if target_price:
        lines.append(f"| **Target Price** | **${target_price:,.0f}** |")
        if current_price and current_price > 0:
            upside = ((target_price / current_price) - 1) * 100
            lines.append(f"| Upside | {upside:+.0f}% |")
    lines.append("")

    # ── Scenarios ──
    lines.append("## Scenarios")
    lines.append(f"| Scenario | Price | Probability | Trigger |")
    lines.append(f"|----------|-------|-------------|---------|")
    for label, s in [("Bull", bull), ("Base", base), ("Bear", bear)]:
        price = s.get("price", 0)
        prob = s.get("probability", 0)
        trigger = s.get("trigger", "—")
        # Truncate trigger for table
        if len(trigger) > 80:
            trigger = trigger[:77] + "..."
        lines.append(f"| {label} | ${price:,.0f} | {prob*100:.0f}% | {trigger} |")
    lines.append("")

    # ── Probability-Weighted Target ──
    if bull.get("price") and base.get("price") and bear.get("price"):
        pw = (bull["price"] * bull.get("probability", 0)
              + base["price"] * base.get("probability", 0)
              + bear["price"] * bear.get("probability", 0))
        lines.append(f"**Probability-weighted target: ${pw:,.0f}**")
        lines.append("")

    # ── Top Criteria ──
    if criteria:
        # Sort by weight priority, take top 3
        weight_order = {"critical": 0, "important": 1, "monitoring": 2}
        sorted_criteria = sorted(criteria, key=lambda c: weight_order.get(c.get("weight", "monitoring"), 3))
        top = sorted_criteria[:3]

        lines.append("## Top Criteria to Watch")
        for i, c in enumerate(top, 1):
            weight_icon = {"critical": "🔴", "important": "🟡", "monitoring": "⚪"}.get(c.get("weight", ""), "⚪")
            status = c.get("status", "not_yet")
            status_icon = {"met": "✅", "failed": "❌", "not_yet": "⏳"}.get(status, "⏳")
            lines.append(f"{i}. {weight_icon} **{c.get('label', 'Unknown')}** {status_icon}")
            lines.append(f"   {c.get('detail', '')}")
            lines.append(f"   *Eval: {c.get('eval_hint', 'N/A')}*")
            lines.append("")

    # ── Kill Condition ──
    lines.append("## Kill Condition")
    lines.append(f"⛔ {kill_condition}")
    lines.append("")

    # ── Notes ──
    if target_notes:
        lines.append("## Model Notes")
        lines.append(target_notes)
        lines.append("")

    return "\n".join(lines)


def generate_digest(stocks: list[dict]) -> str:
    """Generate a combined daily digest across all stocks."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# Stock Radar — Daily Digest ({now})", ""]

    # Summary table
    lines.append("## Watchlist Overview")
    lines.append("| Ticker | Name | Archetype | Target | Current | Upside |")
    lines.append("|--------|------|-----------|--------|---------|--------|")

    sorted_stocks = []
    for s in stocks:
        target = s.get("target_price", 0) or 0
        cache = (s.get("research_cache") or {}).get("quant_snapshot") or {}
        price = cache.get("price", 0) or 0
        upside = ((target / price) - 1) * 100 if price > 0 and target > 0 else 0
        arch = (s.get("archetype") or {}).get("primary", "—") if isinstance(s.get("archetype"), dict) else "—"
        sorted_stocks.append((s, target, price, upside, arch))

    # Sort by upside descending
    sorted_stocks.sort(key=lambda x: -x[3])

    for s, target, price, upside, arch in sorted_stocks:
        ticker = s.get("ticker", "?")
        name = s.get("name", "?")
        t_str = f"${target:,.0f}" if target else "—"
        p_str = f"${price:,.2f}" if price else "—"
        u_str = f"{upside:+.0f}%" if price > 0 and target > 0 else "—"
        lines.append(f"| {ticker} | {name} | {arch} | {t_str} | {p_str} | {u_str} |")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by Stock Radar on {now}*")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate research memos")
    parser.add_argument("--ticker", help="Single ticker to generate memo for")
    parser.add_argument("--all", action="store_true", help="Generate memos for all watchlist stocks")
    parser.add_argument("--digest", action="store_true", help="Generate combined daily digest")
    args = parser.parse_args()

    if args.ticker:
        stock = load_stock_data(args.ticker.upper())
        if not stock:
            print(f"No data found for {args.ticker}")
            sys.exit(1)
        memo = generate_memo(stock)
        out_path = MEMO_DIR / f"{args.ticker.upper()}_memo.md"
        out_path.write_text(memo, encoding="utf-8")
        print(f"Memo written to {out_path}")
        print(f"\n{memo}")

    elif args.all or args.digest:
        watchlist = get_watchlist()
        stocks_data = []
        for entry in watchlist:
            ticker = entry["ticker"]
            data = load_stock_data(ticker)
            if data:
                stocks_data.append(data)
                if args.all:
                    memo = generate_memo(data)
                    out_path = MEMO_DIR / f"{ticker}_memo.md"
                    out_path.write_text(memo, encoding="utf-8")
                    print(f"  ✓ {ticker}")

        if args.all:
            print(f"\nGenerated {len(stocks_data)} memos in {MEMO_DIR}")

        if args.digest or args.all:
            digest = generate_digest(stocks_data)
            digest_path = MEMO_DIR / f"digest_{datetime.now().strftime('%Y%m%d')}.md"
            digest_path.write_text(digest, encoding="utf-8")
            print(f"Digest written to {digest_path}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
