#!/usr/bin/env python3
"""
regime_detection.py — Market regime detection & macro overlay for Stock Radar.

Uses a Hidden Markov Model (Hamilton 1989) on semiconductor index (SOX/SMH)
returns to identify market regimes:

  - **Risk-On** (high growth, low vol): Typical bull market
  - **Risk-Off** (negative returns, high vol): Bear market / correction
  - **Transition** (mixed signals): Regime change underway

The detected regime adjusts:
  - Bear case probabilities (higher in risk-off)
  - Position sizing (reduce exposure in risk-off)
  - Event impact magnitudes (amplified in high-vol regimes)

Also monitors macro indicators:
  - VIX level and term structure
  - Yield curve (10Y-2Y spread)
  - Credit spreads (HY-IG)
  - USD strength (DXY)

Usage:
    python regime_detection.py                # Detect current regime
    python regime_detection.py --history 252  # Show regime history
    python regime_detection.py --overlay       # Full macro overlay
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

try:
    import numpy as np
    import pandas as pd
except ImportError:
    np = pd = None  # type: ignore

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore

try:
    from hmmlearn.hmm import GaussianHMM
    HAS_HMM = True
except ImportError:
    HAS_HMM = False


# ─── Constants ────────────────────────────────────────────────────────

REGIME_NAMES = {0: "risk_off", 1: "risk_on", 2: "transition"}

# Macro indicator tickers
MACRO_TICKERS = {
    "sox": "^SOX",       # Philadelphia Semiconductor Index
    "smh": "SMH",        # Semiconductor ETF (backup)
    "vix": "^VIX",       # CBOE Volatility Index
    "tnx": "^TNX",       # 10-Year Treasury Yield
    "irx": "^IRX",       # 13-Week Treasury Bill
    "hyg": "HYG",        # High Yield Corporate Bond ETF
    "lqd": "LQD",        # Investment Grade Corporate Bond ETF
    "dxy": "DX-Y.NYB",   # US Dollar Index
    "spy": "SPY",        # S&P 500 ETF
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ─── Data types ───────────────────────────────────────────────────────

@dataclass
class RegimeState:
    """Current detected market regime."""
    regime: str             # "risk_on" | "risk_off" | "transition"
    confidence: float       # probability of current regime (0-1)
    timestamp: str
    # Regime-specific adjustments
    bear_prob_adj: float    # additive adjustment to bear probability
    position_scale: float   # multiplier for position sizes (0-1)
    vol_regime: str         # "low" | "normal" | "high" | "extreme"
    # Historical context
    regime_duration_days: int  # how long current regime has persisted
    transition_prob: float     # probability of switching regimes soon


@dataclass
class MacroOverlay:
    """Full macro environment assessment."""
    timestamp: str
    regime: RegimeState
    indicators: dict[str, Any]
    # Summary signals
    risk_appetite: str      # "strong" | "moderate" | "weak" | "very_weak"
    yield_curve: str        # "normal" | "flat" | "inverted"
    credit_stress: str      # "low" | "moderate" | "elevated" | "high"
    dollar_trend: str       # "strengthening" | "neutral" | "weakening"
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Macro Overlay — {self.timestamp[:19]}",
            f"  Regime: {self.regime.regime} ({self.regime.confidence:.0%} confidence)",
            f"  Vol regime: {self.regime.vol_regime}",
            f"  Risk appetite: {self.risk_appetite}",
            f"  Yield curve: {self.yield_curve}",
            f"  Credit stress: {self.credit_stress}",
            f"  USD trend: {self.dollar_trend}",
            f"  Adjustments: bear_prob {self.regime.bear_prob_adj:+.0%}, "
            f"position_scale {self.regime.position_scale:.0%}",
        ]
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


# ─── HMM regime detection ────────────────────────────────────────────

def _fetch_sox_returns(days: int = 504) -> pd.DataFrame | None:
    """Fetch SOX (semiconductor index) daily returns."""
    if not yf or not pd:
        return None

    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))

    for ticker in ["^SOX", "SMH"]:
        try:
            data = yf.download(ticker, start=start, end=end, progress=False)
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                returns = data["Close"].pct_change().dropna()
                vol = returns.rolling(21).std() * np.sqrt(252)
                df = pd.DataFrame({
                    "return": returns,
                    "vol": vol,
                })
                return df.dropna().iloc[-days:]
        except Exception:
            continue
    return None


def detect_regime(days: int = 504) -> RegimeState:
    """Detect current market regime using HMM on SOX returns.

    Falls back to a simple volatility-based heuristic if hmmlearn
    is not installed.
    """
    returns_df = _fetch_sox_returns(days)
    if returns_df is None or len(returns_df) < 60:
        return RegimeState(
            regime="transition",
            confidence=0.5,
            timestamp=datetime.now().isoformat(),
            bear_prob_adj=0.0,
            position_scale=1.0,
            vol_regime="normal",
            regime_duration_days=0,
            transition_prob=0.5,
        )

    recent_vol = returns_df["vol"].iloc[-1]
    vol_percentile = (returns_df["vol"] < recent_vol).mean()

    if HAS_HMM:
        return _hmm_regime(returns_df, recent_vol, vol_percentile)
    else:
        return _heuristic_regime(returns_df, recent_vol, vol_percentile)


def _hmm_regime(
    df: pd.DataFrame,
    recent_vol: float,
    vol_percentile: float,
) -> RegimeState:
    """Regime detection via 3-state Gaussian HMM."""
    X = df[["return", "vol"]].values

    model = GaussianHMM(
        n_components=3,
        covariance_type="full",
        n_iter=200,
        random_state=42,
    )
    model.fit(X)

    # Predict states
    states = model.predict(X)
    state_probs = model.predict_proba(X)

    current_state = states[-1]
    current_prob = state_probs[-1]

    # Identify which state is which by mean return
    state_means = model.means_
    state_order = np.argsort(state_means[:, 0])  # sort by mean return

    # Map: lowest return = risk_off (0), highest = risk_on (1), middle = transition (2)
    state_map = {}
    state_map[state_order[0]] = "risk_off"
    state_map[state_order[2]] = "risk_on"
    state_map[state_order[1]] = "transition"

    regime = state_map[current_state]
    confidence = float(current_prob[current_state])

    # Regime duration
    duration = 1
    for i in range(len(states) - 2, -1, -1):
        if states[i] == current_state:
            duration += 1
        else:
            break

    # Transition probability (from transition matrix)
    transmat = model.transmat_
    transition_prob = float(1 - transmat[current_state, current_state])

    # Compute adjustments
    vol_regime = _classify_vol(vol_percentile)
    bear_adj, pos_scale = _compute_adjustments(regime, vol_regime)

    return RegimeState(
        regime=regime,
        confidence=confidence,
        timestamp=datetime.now().isoformat(),
        bear_prob_adj=bear_adj,
        position_scale=pos_scale,
        vol_regime=vol_regime,
        regime_duration_days=duration,
        transition_prob=transition_prob,
    )


def _heuristic_regime(
    df: pd.DataFrame,
    recent_vol: float,
    vol_percentile: float,
) -> RegimeState:
    """Simple heuristic regime detection (no HMM required)."""
    # 21-day return and volatility
    ret_21d = df["return"].iloc[-21:].sum()
    ret_63d = df["return"].iloc[-63:].sum()

    if vol_percentile > 0.8 and ret_21d < -0.05:
        regime = "risk_off"
        confidence = min(0.9, vol_percentile)
    elif vol_percentile < 0.4 and ret_63d > 0.05:
        regime = "risk_on"
        confidence = min(0.9, 1 - vol_percentile)
    else:
        regime = "transition"
        confidence = 0.5

    # Duration (simple — count consecutive days in same vol regime)
    duration = 1
    threshold = 0.5
    for i in range(len(df) - 2, max(0, len(df) - 120), -1):
        vol_p = (df["vol"].iloc[:i] < df["vol"].iloc[i]).mean()
        if regime == "risk_off" and vol_p > 0.7:
            duration += 1
        elif regime == "risk_on" and vol_p < 0.4:
            duration += 1
        else:
            break

    vol_regime = _classify_vol(vol_percentile)
    bear_adj, pos_scale = _compute_adjustments(regime, vol_regime)

    return RegimeState(
        regime=regime,
        confidence=confidence,
        timestamp=datetime.now().isoformat(),
        bear_prob_adj=bear_adj,
        position_scale=pos_scale,
        vol_regime=vol_regime,
        regime_duration_days=duration,
        transition_prob=0.3,  # default for heuristic
    )


def _classify_vol(vol_percentile: float) -> str:
    if vol_percentile > 0.9:
        return "extreme"
    elif vol_percentile > 0.7:
        return "high"
    elif vol_percentile > 0.3:
        return "normal"
    else:
        return "low"


def _compute_adjustments(regime: str, vol_regime: str) -> tuple[float, float]:
    """Compute bear probability adjustment and position scale.

    Returns (bear_prob_adj, position_scale).
    """
    # Bear probability adjustment
    bear_adj = {
        "risk_off": 0.10,    # +10% to bear probability
        "transition": 0.03,  # +3%
        "risk_on": -0.05,    # -5% (more optimistic)
    }.get(regime, 0.0)

    # Vol overlay
    vol_adj = {
        "extreme": 0.05,
        "high": 0.02,
        "normal": 0.0,
        "low": -0.02,
    }.get(vol_regime, 0.0)

    bear_adj += vol_adj

    # Position scale
    pos_scale = {
        "risk_off": 0.5,     # half positions
        "transition": 0.75,  # 3/4 positions
        "risk_on": 1.0,      # full positions
    }.get(regime, 0.75)

    if vol_regime == "extreme":
        pos_scale *= 0.5     # further reduce in extreme vol

    return bear_adj, pos_scale


# ─── Macro indicators ────────────────────────────────────────────────

def fetch_macro_indicators() -> dict[str, Any]:
    """Fetch current macro indicator values."""
    if not yf or not pd:
        return {}

    indicators = {}
    end = datetime.now()
    start = end - timedelta(days=30)

    for name, ticker in MACRO_TICKERS.items():
        try:
            data = yf.download(ticker, start=start, end=end, progress=False)
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                close = data["Close"]
                indicators[name] = {
                    "current": float(close.iloc[-1]),
                    "change_1d": float(close.pct_change().iloc[-1]) if len(close) > 1 else 0,
                    "change_5d": float((close.iloc[-1] / close.iloc[-5] - 1)) if len(close) > 5 else 0,
                    "change_21d": float((close.iloc[-1] / close.iloc[0] - 1)) if len(close) > 5 else 0,
                }
        except Exception:
            continue

    return indicators


def build_macro_overlay() -> MacroOverlay:
    """Build a full macro environment assessment."""
    regime = detect_regime()
    indicators = fetch_macro_indicators()

    warnings = []

    # VIX analysis
    vix = indicators.get("vix", {}).get("current", 20)
    if vix > 30:
        warnings.append(f"VIX elevated at {vix:.1f} — high fear")
    elif vix > 25:
        warnings.append(f"VIX above average at {vix:.1f}")

    # Risk appetite
    if regime.regime == "risk_on" and vix < 20:
        risk_appetite = "strong"
    elif regime.regime == "risk_on" or vix < 22:
        risk_appetite = "moderate"
    elif regime.regime == "risk_off" and vix > 30:
        risk_appetite = "very_weak"
    else:
        risk_appetite = "weak"

    # Yield curve (10Y - 3M proxy via TNX - IRX)
    tnx = indicators.get("tnx", {}).get("current")
    irx = indicators.get("irx", {}).get("current")
    if tnx is not None and irx is not None:
        spread = tnx - irx
        if spread < -0.5:
            yield_curve = "inverted"
            warnings.append(f"Yield curve inverted ({spread:.2f}%) — recession signal")
        elif spread < 0.25:
            yield_curve = "flat"
        else:
            yield_curve = "normal"
    else:
        yield_curve = "normal"

    # Credit stress (HY - IG spread proxy)
    hyg_chg = indicators.get("hyg", {}).get("change_21d", 0)
    lqd_chg = indicators.get("lqd", {}).get("change_21d", 0)
    credit_diff = hyg_chg - lqd_chg  # If HY underperforming IG, stress rising
    if credit_diff < -0.03:
        credit_stress = "high"
        warnings.append("Credit stress elevated — HY underperforming IG")
    elif credit_diff < -0.01:
        credit_stress = "elevated"
    elif credit_diff > 0.01:
        credit_stress = "low"
    else:
        credit_stress = "moderate"

    # Dollar trend
    dxy_chg = indicators.get("dxy", {}).get("change_21d", 0)
    if dxy_chg > 0.02:
        dollar_trend = "strengthening"
        warnings.append("Strong dollar headwind for multinational earnings")
    elif dxy_chg < -0.02:
        dollar_trend = "weakening"
    else:
        dollar_trend = "neutral"

    return MacroOverlay(
        timestamp=datetime.now().isoformat(),
        regime=regime,
        indicators=indicators,
        risk_appetite=risk_appetite,
        yield_curve=yield_curve,
        credit_stress=credit_stress,
        dollar_trend=dollar_trend,
        warnings=warnings,
    )


# ─── Persistence ──────────────────────────────────────────────────────

def save_regime(regime: RegimeState):
    """Save regime state to data directory."""
    regime_file = DATA_DIR / "regime.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    regime_file.write_text(json.dumps({
        "regime": regime.regime,
        "confidence": regime.confidence,
        "timestamp": regime.timestamp,
        "bear_prob_adj": regime.bear_prob_adj,
        "position_scale": regime.position_scale,
        "vol_regime": regime.vol_regime,
        "regime_duration_days": regime.regime_duration_days,
        "transition_prob": regime.transition_prob,
    }, indent=2))


def load_regime() -> dict | None:
    """Load last saved regime state."""
    regime_file = DATA_DIR / "regime.json"
    if regime_file.exists():
        try:
            return json.loads(regime_file.read_text())
        except Exception:
            return None
    return None


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Market regime detection")
    parser.add_argument("--overlay", action="store_true", help="Full macro overlay")
    parser.add_argument("--history", type=int, default=0, help="Show regime history (days)")
    args = parser.parse_args()

    if args.overlay:
        print("Building macro overlay (fetching market data)...")
        overlay = build_macro_overlay()
        print(overlay.summary())
        save_regime(overlay.regime)
    else:
        print("Detecting market regime...")
        regime = detect_regime()
        print(f"\nRegime: {regime.regime} ({regime.confidence:.0%} confidence)")
        print(f"Vol regime: {regime.vol_regime}")
        print(f"Duration: {regime.regime_duration_days} days")
        print(f"Transition probability: {regime.transition_prob:.0%}")
        print(f"Bear prob adjustment: {regime.bear_prob_adj:+.0%}")
        print(f"Position scale: {regime.position_scale:.0%}")
        save_regime(regime)
