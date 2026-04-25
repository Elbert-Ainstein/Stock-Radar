#!/usr/bin/env python3
"""
paper_trade.py — Alpaca paper-trading bridge for Stock Radar.

Translates Stock Radar model outputs (scenario prices, probabilities,
composite scores) into paper-trade orders on Alpaca's paper-trading API.

Position sizing uses fractional Kelly with a cap (default: half-Kelly,
max 10% per position). Positions are rebalanced daily after the pipeline
runs.

Required env vars:
    ALPACA_API_KEY       — Alpaca paper-trading API key
    ALPACA_SECRET_KEY    — Alpaca paper-trading secret
    ALPACA_BASE_URL      — (optional) defaults to paper-trading endpoint

Usage:
    # After pipeline run, rebalance paper portfolio
    python paper_trade.py --rebalance

    # Show current positions and P&L
    python paper_trade.py --status

    # Run a full cycle: pipeline → rebalance
    python paper_trade.py --cycle
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

ALPACA_BASE_URL = os.environ.get(
    "ALPACA_BASE_URL",
    "https://paper-api.alpaca.markets",
)

try:
    import requests
except ImportError:
    requests = None  # type: ignore


# ─── Data types ───────────────────────────────────────────────────────

@dataclass
class PositionTarget:
    """Desired position for a ticker."""
    ticker: str
    direction: str          # "long" | "flat"
    weight: float           # fraction of portfolio (0 to max_position)
    score: float            # composite score
    expected_return: float  # probability-weighted expected return %
    edge: float             # Kelly edge (p*b - q) / b
    reason: str             # why this sizing


@dataclass
class TradeOrder:
    """A trade to execute."""
    ticker: str
    side: str               # "buy" | "sell"
    qty: float              # number of shares (fractional OK on Alpaca)
    notional: float         # dollar value
    reason: str


@dataclass
class PaperTradeState:
    """Current paper-trading portfolio state."""
    timestamp: str
    equity: float
    cash: float
    positions: list[dict]
    pending_orders: list[dict]
    daily_pnl: float
    total_pnl: float


# ─── Alpaca client ────────────────────────────────────────────────────

class AlpacaClient:
    """Lightweight Alpaca paper-trading API client."""

    def __init__(self):
        self.api_key = os.environ.get("ALPACA_API_KEY", "")
        self.secret = os.environ.get("ALPACA_SECRET_KEY", "")
        self.base_url = ALPACA_BASE_URL.rstrip("/")

        if not self.api_key or not self.secret:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set. "
                "Get free paper-trading keys at https://alpaca.markets"
            )

    @property
    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret,
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> dict | list:
        resp = requests.get(f"{self.base_url}{path}", headers=self._headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        resp = requests.post(
            f"{self.base_url}{path}",
            headers=self._headers,
            json=data,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> None:
        resp = requests.delete(f"{self.base_url}{path}", headers=self._headers, timeout=15)
        resp.raise_for_status()

    def get_account(self) -> dict:
        return self._get("/v2/account")

    def get_positions(self) -> list[dict]:
        return self._get("/v2/positions")

    def get_position(self, ticker: str) -> dict | None:
        try:
            return self._get(f"/v2/positions/{ticker}")
        except Exception:
            return None

    def submit_order(
        self,
        ticker: str,
        qty: float | None = None,
        notional: float | None = None,
        side: str = "buy",
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> dict:
        order = {
            "symbol": ticker,
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if notional is not None:
            order["notional"] = round(notional, 2)
        elif qty is not None:
            order["qty"] = str(qty)
        return self._post("/v2/orders", order)

    def close_position(self, ticker: str) -> dict:
        resp = requests.delete(
            f"{self.base_url}/v2/positions/{ticker}",
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def close_all_positions(self) -> list[dict]:
        return self._delete("/v2/positions")

    def get_portfolio_history(self, period: str = "1M") -> dict:
        return self._get(f"/v2/account/portfolio/history?period={period}&timeframe=1D")


# ─── Position sizing (half-Kelly) ────────────────────────────────────

MAX_POSITION_WEIGHT = 0.10      # 10% max per position
KELLY_FRACTION = 0.5            # half-Kelly (more conservative)
MIN_SCORE_TO_TRADE = 6.0        # minimum composite score
MIN_EXPECTED_RETURN = 0.02      # minimum 2% expected return
MAX_POSITIONS = 15              # max concurrent positions


def compute_kelly_weight(
    prob_win: float,
    win_return: float,
    loss_return: float,
) -> float:
    """Compute Kelly fraction: f* = (p*b - q) / b.

    Parameters
    ----------
    prob_win : float
        Probability of winning (0-1).
    win_return : float
        Expected gain if win (as ratio, e.g. 0.30 = 30%).
    loss_return : float
        Expected loss if lose (as ratio, e.g. 0.15 = 15%, entered positive).
    """
    if win_return <= 0 or loss_return <= 0 or prob_win <= 0:
        return 0.0

    b = win_return / loss_return  # odds ratio
    q = 1 - prob_win
    kelly = (prob_win * b - q) / b

    # Apply half-Kelly and cap
    weight = max(0, kelly * KELLY_FRACTION)
    return min(weight, MAX_POSITION_WEIGHT)


def compute_position_targets(
    models: list[dict],
    scores: dict[str, float],
) -> list[PositionTarget]:
    """Convert model outputs + scores into position targets.

    Parameters
    ----------
    models : list[dict]
        Model configs from generate_model.py (one per ticker).
    scores : dict[str, float]
        Composite scores from analyst.py {ticker: score}.
    """
    targets: list[PositionTarget] = []

    for model in models:
        ticker = model.get("ticker", "")
        score = scores.get(ticker, 0)

        if score < MIN_SCORE_TO_TRADE:
            targets.append(PositionTarget(
                ticker=ticker, direction="flat", weight=0,
                score=score, expected_return=0, edge=0,
                reason=f"Score {score:.1f} below threshold {MIN_SCORE_TO_TRADE}",
            ))
            continue

        scenarios = model.get("scenarios", {})
        bull = scenarios.get("bull", {})
        base = scenarios.get("base", {})
        bear = scenarios.get("bear", {})

        current_price = model.get("current_price", 0)
        if not current_price or current_price <= 0:
            continue

        # Probability-weighted expected return
        p_bull = bull.get("probability", 0.25)
        p_base = base.get("probability", 0.50)
        p_bear = bear.get("probability", 0.25)

        r_bull = (bull.get("price", current_price) - current_price) / current_price
        r_base = (base.get("price", current_price) - current_price) / current_price
        r_bear = (bear.get("price", current_price) - current_price) / current_price

        expected_return = p_bull * r_bull + p_base * r_base + p_bear * r_bear

        if expected_return < MIN_EXPECTED_RETURN:
            targets.append(PositionTarget(
                ticker=ticker, direction="flat", weight=0,
                score=score, expected_return=expected_return, edge=0,
                reason=f"Expected return {expected_return:.1%} below {MIN_EXPECTED_RETURN:.0%}",
            ))
            continue

        # Kelly sizing: use bull/base as "win" scenarios, bear as "loss"
        prob_win = p_bull + p_base
        win_return = (p_bull * r_bull + p_base * r_base) / max(prob_win, 0.01)
        loss_return = abs(r_bear) if r_bear < 0 else 0.01

        weight = compute_kelly_weight(prob_win, win_return, loss_return)
        edge = (prob_win * (win_return / loss_return) - (1 - prob_win)) / (win_return / loss_return) if loss_return > 0 else 0

        targets.append(PositionTarget(
            ticker=ticker,
            direction="long" if weight > 0 else "flat",
            weight=weight,
            score=score,
            expected_return=expected_return,
            edge=edge,
            reason=f"Kelly={weight:.1%}, E[r]={expected_return:.1%}, score={score:.1f}",
        ))

    # Sort by expected return × score, take top MAX_POSITIONS
    targets.sort(key=lambda t: t.expected_return * t.score, reverse=True)
    active = [t for t in targets if t.direction == "long"][:MAX_POSITIONS]
    flat = [t for t in targets if t.direction == "flat"]

    # Normalize weights to sum ≤ 1
    total_weight = sum(t.weight for t in active)
    if total_weight > 1.0:
        for t in active:
            t.weight /= total_weight

    return active + flat


# ─── Rebalancing ──────────────────────────────────────────────────────

def rebalance(
    client: AlpacaClient,
    targets: list[PositionTarget],
    dry_run: bool = False,
) -> list[TradeOrder]:
    """Rebalance paper portfolio to match position targets.

    Returns list of orders executed (or that would be executed in dry_run).
    """
    account = client.get_account()
    equity = float(account["equity"])
    current_positions = {p["symbol"]: p for p in client.get_positions()}

    orders: list[TradeOrder] = []

    # Build target map
    target_map = {t.ticker: t for t in targets if t.direction == "long"}

    # Close positions not in targets
    for symbol, pos in current_positions.items():
        if symbol not in target_map:
            notional = abs(float(pos["market_value"]))
            orders.append(TradeOrder(
                ticker=symbol, side="sell", qty=float(pos["qty"]),
                notional=notional, reason="Not in target list",
            ))
            if not dry_run:
                try:
                    client.close_position(symbol)
                    print(f"  Closed {symbol} (${notional:,.0f})")
                except Exception as e:
                    print(f"  Failed to close {symbol}: {e}")

    # Adjust positions to target weights
    for ticker, target in target_map.items():
        target_notional = equity * target.weight
        current_notional = float(
            current_positions.get(ticker, {}).get("market_value", 0)
        )
        diff = target_notional - current_notional

        if abs(diff) < 50:  # skip tiny adjustments
            continue

        if diff > 0:
            orders.append(TradeOrder(
                ticker=ticker, side="buy", qty=0,
                notional=diff, reason=target.reason,
            ))
            if not dry_run:
                try:
                    client.submit_order(ticker, notional=diff, side="buy")
                    print(f"  Buy ${diff:,.0f} of {ticker} ({target.reason})")
                except Exception as e:
                    print(f"  Failed to buy {ticker}: {e}")
        elif diff < 0:
            sell_notional = abs(diff)
            orders.append(TradeOrder(
                ticker=ticker, side="sell", qty=0,
                notional=sell_notional, reason="Reduce to target weight",
            ))
            if not dry_run:
                try:
                    # Calculate shares to sell
                    current_price = float(current_positions[ticker]["current_price"])
                    shares_to_sell = sell_notional / current_price
                    client.submit_order(ticker, qty=round(shares_to_sell, 4), side="sell")
                    print(f"  Sell ${sell_notional:,.0f} of {ticker}")
                except Exception as e:
                    print(f"  Failed to sell {ticker}: {e}")

    return orders


# ─── Status / logging ────────────────────────────────────────────────

def get_status(client: AlpacaClient) -> PaperTradeState:
    """Get current paper portfolio state."""
    account = client.get_account()
    positions = client.get_positions()

    return PaperTradeState(
        timestamp=datetime.now(timezone.utc).isoformat(),
        equity=float(account["equity"]),
        cash=float(account["cash"]),
        positions=[
            {
                "ticker": p["symbol"],
                "qty": float(p["qty"]),
                "avg_entry": float(p["avg_entry_price"]),
                "current_price": float(p["current_price"]),
                "market_value": float(p["market_value"]),
                "unrealized_pnl": float(p["unrealized_pl"]),
                "unrealized_pnl_pct": float(p["unrealized_plpc"]) * 100,
            }
            for p in positions
        ],
        pending_orders=[],
        daily_pnl=float(account.get("equity", 0)) - float(account.get("last_equity", 0)),
        total_pnl=float(account["equity"]) - 100_000,  # Alpaca paper starts at $100k
    )


def log_state(state: PaperTradeState, log_dir: Path | None = None):
    """Append portfolio state to daily log file."""
    if log_dir is None:
        log_dir = Path(__file__).resolve().parent.parent / "data" / "paper_trade"
    log_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"portfolio_{date_str}.json"

    entry = {
        "timestamp": state.timestamp,
        "equity": state.equity,
        "cash": state.cash,
        "daily_pnl": state.daily_pnl,
        "total_pnl": state.total_pnl,
        "n_positions": len(state.positions),
        "positions": state.positions,
    }

    # Append to daily log
    logs = []
    if log_file.exists():
        try:
            logs = json.loads(log_file.read_text())
        except Exception:
            logs = []
    logs.append(entry)
    log_file.write_text(json.dumps(logs, indent=2))


# ─── CLI ──────────────────────────────────────────────────────────────

def _print_status(state: PaperTradeState):
    print(f"\nPaper Portfolio — {state.timestamp[:19]}")
    print(f"  Equity:    ${state.equity:,.2f}")
    print(f"  Cash:      ${state.cash:,.2f}")
    print(f"  Daily P&L: ${state.daily_pnl:,.2f}")
    print(f"  Total P&L: ${state.total_pnl:,.2f}")
    if state.positions:
        print(f"\n  {'Ticker':<8} {'Qty':>8} {'Entry':>10} {'Current':>10} {'P&L':>10} {'P&L%':>8}")
        print(f"  {'─'*56}")
        for p in sorted(state.positions, key=lambda x: -abs(x["unrealized_pnl"])):
            print(
                f"  {p['ticker']:<8} {p['qty']:>8.2f} "
                f"${p['avg_entry']:>9,.2f} ${p['current_price']:>9,.2f} "
                f"${p['unrealized_pnl']:>9,.2f} {p['unrealized_pnl_pct']:>7.1f}%"
            )
    else:
        print("  No positions")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stock Radar paper trading")
    parser.add_argument("--status", action="store_true", help="Show portfolio status")
    parser.add_argument("--rebalance", action="store_true", help="Rebalance portfolio")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument("--cycle", action="store_true", help="Full pipeline → rebalance")
    args = parser.parse_args()

    if not os.environ.get("ALPACA_API_KEY"):
        print("Set ALPACA_API_KEY and ALPACA_SECRET_KEY to use paper trading.")
        print("Get free keys at https://alpaca.markets")
        sys.exit(1)

    client = AlpacaClient()

    if args.status:
        state = get_status(client)
        _print_status(state)
        log_state(state)

    elif args.rebalance or args.cycle:
        if args.cycle:
            print("Running pipeline first...")
            os.system("python scripts/run_pipeline.py")

        # Load latest models and scores
        data_dir = Path(__file__).resolve().parent.parent / "data"
        models_file = data_dir / "models.json"
        analysis_file = data_dir / "analysis.json"

        if not models_file.exists():
            print("No models.json found — run the pipeline first")
            sys.exit(1)

        models = json.loads(models_file.read_text()) if models_file.exists() else []
        analysis = json.loads(analysis_file.read_text()) if analysis_file.exists() else {}
        scores = {}
        if isinstance(analysis, dict):
            for ticker, data in analysis.items():
                if isinstance(data, dict):
                    scores[ticker] = data.get("composite_score", 5.0)

        targets = compute_position_targets(models, scores)
        print(f"\nPosition targets ({len([t for t in targets if t.direction == 'long'])} active):")
        for t in targets:
            if t.direction == "long":
                print(f"  {t.ticker}: {t.weight:.1%} — {t.reason}")

        orders = rebalance(client, targets, dry_run=args.dry_run)

        if args.dry_run:
            print(f"\nDry run — {len(orders)} orders would execute:")
            for o in orders:
                print(f"  {o.side.upper()} {o.ticker}: ${o.notional:,.0f} ({o.reason})")
        else:
            print(f"\nExecuted {len(orders)} orders")

        state = get_status(client)
        _print_status(state)
        log_state(state)
    else:
        parser.print_help()
