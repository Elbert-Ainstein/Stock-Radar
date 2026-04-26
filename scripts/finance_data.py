#!/usr/bin/env python3
"""
finance_data.py — Historical financial actuals from 10-K/10-Q filings.

**This is the ONLY module that populates historical columns of the model.**
All financial model outputs (brief slider view, detailed page, Excel export)
ultimately trace their historical rows back to this fetcher.

**Hard-fail contract:** if the configured provider cannot return usable
quarterly data, raise EarningsFetchError. Do NOT silently fall back to
Perplexity estimates — a model built on estimated "historicals" is
worthless, and the user explicitly required this constraint on 2026-04-18.

**Provider architecture:** The data source is abstracted behind a
DataProvider protocol. Providers are selected via FINANCE_DATA_PROVIDER
env var (default: "yfinance"). Available providers:
  - yfinance  — scrapes Yahoo Finance / SEC filings (free, unreliable)
  - eodhd     — EODHD Fundamentals API (paid, reliable)
  - alpha_vantage — Alpha Vantage API (free tier, rate-limited)

The FinancialData dataclass is the contract between providers and the
engine. Providers must fill the same fields regardless of where the data
comes from.

Usage:
    from finance_data import fetch_financials, EarningsFetchError
    try:
        fin = fetch_financials("LITE")
    except EarningsFetchError as e:
        print(f"Cannot build model: {e}")
"""
from __future__ import annotations

import math
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class EarningsFetchError(Exception):
    """Raised when we cannot obtain historical earnings data for a ticker.
    Model generation MUST halt when this is raised — never silently estimate."""


# ---------------------------------------------------------------------------
# Shared constants and utilities (provider-agnostic)
# ---------------------------------------------------------------------------

# Minimum required line items. If any are missing in BOTH quarterly and annual
# views for a ticker, we cannot build a model.
REQUIRED_LINES = {
    "income_stmt": ["Total Revenue", "Operating Income", "Net Income"],
    "cashflow": ["Free Cash Flow", "Capital Expenditure"],
    "balance_sheet": ["Cash And Cash Equivalents", "Ordinary Shares Number"],
}

# Canonical line-item names used across all providers. Each provider maps its
# native field names to these canonical names so the rest of the system never
# cares which API the data came from.
IS_LINES = [
    "Total Revenue", "Cost Of Revenue", "Gross Profit",
    "Selling General And Administration", "Research And Development",
    "Operating Income", "EBITDA", "Normalized EBITDA",
    "Interest Expense", "Net Non Operating Interest Income Expense",
    "Pretax Income", "Tax Provision", "Net Income",
    "Diluted Average Shares", "Basic Average Shares",
    "Diluted EPS", "Basic EPS", "Tax Rate For Calcs",
]
CF_LINES = [
    "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
    "Stock Based Compensation", "Depreciation And Amortization",
    "Depreciation", "Amortization Of Intangibles",
    "Change In Working Capital", "Net Income From Continuing Operations",
]
BS_LINES = [
    "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments",
    "Current Assets", "Total Assets",
    "Current Debt", "Long Term Debt", "Total Debt",
    "Current Liabilities", "Total Liabilities Net Minority Interest",
    "Net PPE", "Goodwill And Other Intangible Assets",
    "Ordinary Shares Number", "Share Issued",
    "Stockholders Equity", "Total Equity Gross Minority Interest",
]


def _to_float(x: Any) -> float | None:
    """Convert cell to float, treating NaN / None / non-numeric as None."""
    if x is None:
        return None
    try:
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Ticker integrity rules — re-IPOs, delistings, data cutoffs
# ---------------------------------------------------------------------------
# Some tickers have known data contamination issues.  For example, SNDK
# re-IPO'd on Feb 24 2025 — any financial data dated before that belongs
# to the OLD SanDisk (acquired by WDC in 2016) and is misleading.
#
# TICKER_DATA_CUTOFFS maps ticker → earliest valid date (inclusive).
# Quarters whose period end-date falls before the cutoff are silently
# dropped after fetch, and a warning is attached to FinancialData.warnings.

TICKER_DATA_CUTOFFS: dict[str, datetime] = {
    # SNDK re-IPO'd 2025-02-24 — pre-2025 data is the old SanDisk Corp
    "SNDK": datetime(2025, 2, 1, tzinfo=timezone.utc),
}

# Tickers that are known delisted, merged, or otherwise no longer tradable.
# fetch_financials will raise EarningsFetchError immediately for these
# instead of wasting an API call and potentially ingesting stale data.
DELISTED_TICKERS: dict[str, str] = {
    # "EXAMPLE": "Acquired by XYZ on 2025-01-01 — use XYZ instead",
}


def _apply_data_cutoff(ticker: str, periods: list[dict], freq: str) -> tuple[list[dict], list[str]]:
    """Remove periods that fall before the ticker's data cutoff date.

    Returns (filtered_periods, warnings).
    """
    cutoff = TICKER_DATA_CUTOFFS.get(ticker.upper())
    if not cutoff or not periods:
        return periods, []

    warnings: list[str] = []
    filtered: list[dict] = []
    dropped = 0

    for p in periods:
        period_str = p.get("period", "")
        period_date = p.get("_date")  # Some providers set a raw date

        # Try to extract a date from the period label (e.g. "1Q25" → 2025-03)
        if period_date and hasattr(period_date, "year"):
            pdt = datetime(period_date.year, period_date.month, 1, tzinfo=timezone.utc)
        elif period_str:
            pdt = _parse_period_to_date(period_str)
        else:
            pdt = None

        if pdt and pdt < cutoff:
            dropped += 1
            continue
        filtered.append(p)

    if dropped:
        warnings.append(
            f"DATA_CUTOFF: Dropped {dropped} {freq} period(s) for {ticker} "
            f"before {cutoff.strftime('%Y-%m-%d')} (re-IPO/entity change)"
        )

    return filtered, warnings


def _parse_period_to_date(label: str) -> datetime | None:
    """Parse period labels like '1Q25', '2024', '2025-03' to a datetime."""
    import re
    # Quarterly: "1Q25" or "3Q2024"
    m = re.match(r"(\d)Q(\d{2,4})", label)
    if m:
        q, y = int(m.group(1)), int(m.group(2))
        if y < 100:
            y += 2000
        month = q * 3  # end of quarter month
        return datetime(y, month, 1, tzinfo=timezone.utc)
    # Annual: "2024" or "2025"
    m = re.match(r"^(20\d{2})$", label)
    if m:
        return datetime(int(m.group(1)), 12, 1, tzinfo=timezone.utc)
    # ISO-ish: "2025-03"
    m = re.match(r"(\d{4})-(\d{2})", label)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=timezone.utc)
    return None


def _period_label(ts, freq: str) -> str:
    """Convert timestamp to '1Q25'/'2024' style label."""
    if hasattr(ts, "year"):
        y = ts.year
        m = ts.month
    else:
        try:
            d = datetime.fromisoformat(str(ts))
            y, m = d.year, d.month
        except Exception:
            return str(ts)[:10]
    if freq == "annual":
        return str(y)
    q = (m - 1) // 3 + 1
    return f"{q}Q{str(y)[-2:]}"


def _validate_quarterly_revenue(periods: list[dict]) -> list[str]:
    """Detect quarters with suspicious revenue spikes.

    Checks two signals for each quarter:
    1. Revenue > Nx the trailing 4Q average (rolling anomaly)
    2. Revenue > Mx same-quarter-last-year (YoY anomaly)

    Thresholds are size-aware:
    - Large-cap (trailing avg ≥ $500M/Q): 2.0x trailing, 2.5x YoY
      → catches data-provider errors (MU-class: $23B vs $8.7B actual)
    - Mid-cap ($100M–$500M): 3.0x trailing, 4.0x YoY
      → moderate tolerance for business lumpiness
    - Micro/small-cap (< $100M/Q): 5.0x trailing, 6.0x YoY
      → high tolerance; $5M→$15M quarter swings are normal order
        lumpiness for semi-equipment, biotech, and niche industrials

    Returns a list of warning strings. Called AFTER period conversion so we can
    catch bad data before it poisons TTM calculations.

    This was added to catch the MU-class bug: yfinance returning a Q1 FY26
    revenue of $23.86B vs actual ~$8.7B, which inflated TTM revenue to ~$58B
    and produced a $1290 base target on a $455 stock.
    """
    warnings: list[str] = []
    if not periods:
        return warnings

    # Only check the most recent 8 quarters (2 years) — flagging ancient
    # data (e.g. ASML 2010) is noise, not signal.
    start_idx = max(0, len(periods) - 8)

    for i, p in enumerate(periods):
        if i < start_idx:
            continue
        rev = p.get("Total Revenue")
        if rev is None or rev <= 0:
            continue

        period_label = p.get("period", f"idx-{i}")

        # Check 1: trailing 4Q average (need at least 2 prior quarters)
        prior_revs = []
        for j in range(max(0, i - 4), i):
            r = periods[j].get("Total Revenue")
            if r is not None and r > 0:
                prior_revs.append(r)

        if len(prior_revs) >= 2:
            trailing_avg = sum(prior_revs) / len(prior_revs)

            # Size-aware thresholds: micro-caps have lumpy revenue by nature
            if trailing_avg >= 500e6:       # Large-cap: ≥$500M/Q
                trailing_thresh = 2.0
            elif trailing_avg >= 100e6:     # Mid-cap: $100M–$500M/Q
                trailing_thresh = 3.0
            else:                           # Micro/small-cap: <$100M/Q
                trailing_thresh = 5.0

            if trailing_avg > 0 and rev > trailing_thresh * trailing_avg:
                ratio = rev / trailing_avg
                warnings.append(
                    f"SUSPECT DATA: {period_label} revenue "
                    f"${rev/1e9:.2f}B is {ratio:.1f}x the trailing "
                    f"{len(prior_revs)}Q avg ${trailing_avg/1e9:.2f}B "
                    f"(threshold: {trailing_thresh:.0f}x for this revenue scale). "
                    f"Possible data error — cross-check against "
                    f"10-Q filing before trusting this quarter."
                )

        # Check 2: same-quarter-last-year (4 periods back in quarterly data)
        if i >= 4:
            yoy_rev = periods[i - 4].get("Total Revenue")
            if yoy_rev is not None and yoy_rev > 0:
                # Size-aware YoY thresholds
                if yoy_rev >= 500e6:
                    yoy_thresh = 2.5
                elif yoy_rev >= 100e6:
                    yoy_thresh = 4.0
                else:
                    yoy_thresh = 6.0

                if rev > yoy_thresh * yoy_rev:
                    ratio = rev / yoy_rev
                    warnings.append(
                        f"SUSPECT DATA: {period_label} revenue "
                        f"${rev/1e9:.2f}B is {ratio:.1f}x same-quarter-"
                        f"last-year ${yoy_rev/1e9:.2f}B "
                        f"(threshold: {yoy_thresh:.1f}x). Verify against filing."
                    )

    return warnings


def _check_required(periods: list[dict], category: str) -> list[str]:
    """Return a list of missing required lines across ALL periods.
    Empty list = OK."""
    if not periods:
        return REQUIRED_LINES[category]
    missing = []
    for line in REQUIRED_LINES[category]:
        # Consider missing if every period is None
        has_value = any(p.get(line) is not None for p in periods)
        if not has_value:
            missing.append(line)
    return missing


def _latest_non_null(periods: list[dict], key: str):
    """Return the latest (last) period's value for `key`, skipping None."""
    for p in reversed(periods):
        if p.get(key) is not None:
            return p[key]
    return None


def _derive_net_debt(bs_periods: list[dict]) -> float | None:
    """Compute net debt = total debt - cash (using latest period).
    Handles cases where Total Debt is None but we have Long Term + Current Debt."""
    if not bs_periods:
        return None
    last = bs_periods[-1]
    cash = last.get("Cash And Cash Equivalents") or last.get(
        "Cash Cash Equivalents And Short Term Investments"
    )
    debt = last.get("Total Debt")
    if debt is None:
        lt = last.get("Long Term Debt") or 0
        st = last.get("Current Debt") or 0
        debt = lt + st if (lt or st) else None
    if debt is None and cash is None:
        return None
    return (debt or 0) - (cash or 0)


def _derive_shares(bs_periods: list[dict], is_periods: list[dict]) -> float | None:
    """Latest diluted share count (in whole shares), preferring IS diluted
    average, falling back to BS ordinary shares."""
    v = _latest_non_null(is_periods, "Diluted Average Shares")
    if v is not None and v > 0:
        return v
    v = _latest_non_null(bs_periods, "Ordinary Shares Number")
    return v if v and v > 0 else None


def _validate_and_build(
    ticker: str,
    info: dict,
    q_inc: list[dict],
    q_cf: list[dict],
    q_bs: list[dict],
    a_inc: list[dict],
    a_cf: list[dict],
    a_bs: list[dict],
    source: str,
    min_quarters: int = 4,
    extra_warnings: list[str] | None = None,
) -> FinancialData:
    """Shared validation + FinancialData construction used by all providers.

    Takes the normalized period lists (already in canonical field names) and
    runs the standard validation pipeline: revenue sanity check, required
    line-item check, minimum coverage check, then builds the dataclass.
    """
    warnings: list[str] = list(extra_warnings or [])

    # Revenue sanity check
    rev_warnings = _validate_quarterly_revenue(q_inc)
    if rev_warnings:
        warnings.extend(rev_warnings)
        print(f"  [{ticker}] Revenue sanity check fired:", file=sys.stderr)
        for w in rev_warnings:
            print(f"    {w}", file=sys.stderr)

    # Enforce minimum coverage
    if len(q_inc) < min_quarters and len(a_inc) < 2:
        raise EarningsFetchError(
            f"{ticker}: insufficient earnings history. "
            f"Got {len(q_inc)} quarters + {len(a_inc)} years of income data "
            f"(need >= {min_quarters} quarters OR >= 2 years). "
            f"This ticker may be too newly public — no model can be built."
        )

    # Check required lines in quarterly; if missing, try annual
    def _validate(q_periods, a_periods, category):
        missing_q = _check_required(q_periods, category)
        if not missing_q:
            return
        missing_a = _check_required(a_periods, category)
        if not missing_a:
            warnings.append(
                f"{category}: {missing_q} missing in quarterly data; annual has them."
            )
            return
        raise EarningsFetchError(
            f"{ticker}: {category} is missing required line items in BOTH "
            f"quarterly and annual views: quarterly={missing_q}, annual={missing_a}. "
            f"Cannot build reliable model."
        )

    _validate(q_inc, a_inc, "income_stmt")
    _validate(q_cf, a_cf, "cashflow")
    _validate(q_bs, a_bs, "balance_sheet")

    # Scalar summary fields
    price = float(info.get("price") or info.get("currentPrice") or
                  info.get("regularMarketPrice") or 0.0)
    market_cap = info.get("marketCap") or info.get("market_cap")
    shares = _derive_shares(q_bs, q_inc) or info.get("sharesOutstanding") or info.get("shares")
    net_debt = _derive_net_debt(q_bs)

    if price <= 0:
        warnings.append(f"price is zero/missing from {source}")

    return FinancialData(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or info.get("name") or ticker,
        sector=info.get("sector") or "Unknown",
        currency=info.get("financialCurrency") or info.get("currency") or "USD",
        price=price,
        market_cap=_to_float(market_cap),
        shares_diluted=_to_float(shares),
        net_debt=_to_float(net_debt),
        quarterly_income=q_inc,
        quarterly_cashflow=q_cf,
        quarterly_balance=q_bs,
        annual_income=a_inc,
        annual_cashflow=a_cf,
        annual_balance=a_bs,
        source=source,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# FinancialData — the contract between providers and the engine
# ---------------------------------------------------------------------------

@dataclass
class FinancialData:
    ticker: str
    name: str
    sector: str
    currency: str
    price: float
    market_cap: float | None
    shares_diluted: float | None
    net_debt: float | None
    # time series, chronological (oldest first)
    quarterly_income: list[dict] = field(default_factory=list)
    quarterly_cashflow: list[dict] = field(default_factory=list)
    quarterly_balance: list[dict] = field(default_factory=list)
    annual_income: list[dict] = field(default_factory=list)
    annual_cashflow: list[dict] = field(default_factory=list)
    annual_balance: list[dict] = field(default_factory=list)
    source: str = "yfinance"
    fetched_at: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "sector": self.sector,
            "currency": self.currency,
            "price": self.price,
            "market_cap": self.market_cap,
            "shares_diluted": self.shares_diluted,
            "net_debt": self.net_debt,
            "quarterly_income": self.quarterly_income,
            "quarterly_cashflow": self.quarterly_cashflow,
            "quarterly_balance": self.quarterly_balance,
            "annual_income": self.annual_income,
            "annual_cashflow": self.annual_cashflow,
            "annual_balance": self.annual_balance,
            "source": self.source,
            "fetched_at": self.fetched_at,
            "warnings": self.warnings,
        }

    def latest_quarter_label(self) -> str | None:
        return self.quarterly_income[-1]["period"] if self.quarterly_income else None

    def ttm_revenue(self) -> float | None:
        """Trailing twelve months revenue from the last 4 quarters, if available."""
        revs = [p.get("Total Revenue") for p in self.quarterly_income[-4:]]
        revs = [r for r in revs if r is not None]
        if len(revs) < 4:
            return None
        return sum(revs)

    def ttm_gross_margin(self) -> float | None:
        """TTM gross profit / TTM revenue, or None if data missing."""
        rev = self.ttm_revenue()
        if not rev or rev <= 0:
            return None
        gps = [p.get("Gross Profit") for p in self.quarterly_income[-4:]]
        gps = [g for g in gps if g is not None]
        if len(gps) < 4:
            return None
        return sum(gps) / rev

    def ttm_operating_income(self) -> float | None:
        vals = [p.get("Operating Income") for p in self.quarterly_income[-4:]]
        vals = [v for v in vals if v is not None]
        if len(vals) < 4:
            return None
        return sum(vals)

    def ttm_fcf(self) -> float | None:
        vals = [p.get("Free Cash Flow") for p in self.quarterly_cashflow[-4:]]
        vals = [v for v in vals if v is not None]
        if len(vals) < 4:
            return None
        return sum(vals)

    def ttm_ebitda(self) -> float | None:
        """Prefer reported EBITDA; else OpIncome + D&A."""
        vals = [p.get("EBITDA") or p.get("Normalized EBITDA") for p in self.quarterly_income[-4:]]
        vals = [v for v in vals if v is not None]
        if len(vals) == 4:
            return sum(vals)
        # Fallback: op income + D&A
        oi = self.ttm_operating_income()
        if oi is None:
            return None
        dep = [p.get("Depreciation And Amortization") for p in self.quarterly_cashflow[-4:]]
        dep = [v for v in dep if v is not None]
        if len(dep) != 4:
            return oi
        return oi + sum(dep)


# ---------------------------------------------------------------------------
# Live price helper (Alpha Vantage GLOBAL_QUOTE)
# ---------------------------------------------------------------------------

def _fetch_live_price_av(ticker: str) -> dict[str, float | None]:
    """Fetch current price + market cap from Alpha Vantage GLOBAL_QUOTE.

    Returns {"price": float|None, "market_cap": float|None}.
    Used by EODHD provider since EODHD Fundamentals doesn't serve live quotes.
    Falls back gracefully — returns Nones if AV key is missing or call fails.
    """
    av_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not av_key:
        return {"price": None, "market_cap": None}

    try:
        import requests
        resp = requests.get(
            "https://www.alphavantage.co/query",
            params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": av_key},
            timeout=10,
        )
        resp.raise_for_status()
        gq = resp.json().get("Global Quote", {})
        price = _to_float(gq.get("05. price"))
        return {"price": price, "market_cap": None}  # AV GLOBAL_QUOTE doesn't include mcap
    except Exception as e:
        print(f"  [finance_data] Alpha Vantage live price failed for {ticker}: {e}", file=sys.stderr)
        return {"price": None, "market_cap": None}


# ---------------------------------------------------------------------------
# DataProvider — abstract interface for financial data sources
# ---------------------------------------------------------------------------

class DataProvider(ABC):
    """Abstract base class for financial data providers.

    Each provider must implement `fetch()` which returns a FinancialData
    dataclass populated with the provider's data. The canonical field names
    (IS_LINES, CF_LINES, BS_LINES) must be used so the engine doesn't need
    to know which provider generated the data.
    """

    @abstractmethod
    def fetch(self, ticker: str, min_quarters: int = 4) -> FinancialData:
        """Fetch financial data for a ticker.

        Raises EarningsFetchError if data is unavailable or insufficient.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name for logging and source attribution."""
        ...


# ---------------------------------------------------------------------------
# YFinanceProvider — original provider (free, scrapes Yahoo/SEC)
# ---------------------------------------------------------------------------

class YFinanceProvider(DataProvider):
    """Financial data from yfinance (scrapes Yahoo Finance / SEC EDGAR).

    Known issues:
      - Rate-limited, undocumented internal API
      - MU bug: Q1 FY26 returned $23.86B instead of ~$8.7B
      - Breaks without warning when Yahoo changes their internal API
      - No SLA or support

    Use as fallback only. Prefer EODHD for reliable data.
    """

    @property
    def name(self) -> str:
        return "yfinance (SEC filings)"

    def _ensure_yfinance(self):
        try:
            import yfinance  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "yfinance is required for the yfinance provider. Install with:\n"
                "  pip install yfinance --break-system-packages"
            ) from e

    @staticmethod
    def _df_to_periods(df, lines: list[str], freq: str) -> list[dict]:
        """Turn a yfinance financials DataFrame (rows=lines, cols=periods) into
        a list of per-period dicts in chronological order (oldest first)."""
        if df is None or df.empty:
            return []
        periods = []
        for col in sorted(df.columns):  # ascending date order
            pd_ = {"period": _period_label(col, freq), "date": str(col)[:10]}
            for line in lines:
                if line in df.index:
                    pd_[line] = _to_float(df.at[line, col])
                else:
                    pd_[line] = None
            periods.append(pd_)
        return periods

    def fetch(self, ticker: str, min_quarters: int = 4) -> FinancialData:
        self._ensure_yfinance()
        import yfinance as yf

        ticker = ticker.upper().strip()
        if not ticker:
            raise EarningsFetchError("empty ticker")

        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
        except Exception as e:
            raise EarningsFetchError(f"{ticker}: yfinance Ticker init failed: {e}") from e

        if not info or "marketCap" not in info:
            raise EarningsFetchError(
                f"{ticker}: yfinance returned no company info. Ticker may be delisted or invalid."
            )

        try:
            qis = t.quarterly_income_stmt
            qcf = t.quarterly_cashflow
            qbs = t.quarterly_balance_sheet
            ais = t.income_stmt
            acf = t.cashflow
            abs_ = t.balance_sheet
        except Exception as e:
            raise EarningsFetchError(f"{ticker}: failed to fetch financials: {e}") from e

        q_inc = self._df_to_periods(qis, IS_LINES, "quarterly")
        q_cf = self._df_to_periods(qcf, CF_LINES, "quarterly")
        q_bs = self._df_to_periods(qbs, BS_LINES, "quarterly")
        a_inc = self._df_to_periods(ais, IS_LINES, "annual")
        a_cf = self._df_to_periods(acf, CF_LINES, "annual")
        a_bs = self._df_to_periods(abs_, BS_LINES, "annual")

        return _validate_and_build(
            ticker=ticker,
            info=info,
            q_inc=q_inc, q_cf=q_cf, q_bs=q_bs,
            a_inc=a_inc, a_cf=a_cf, a_bs=a_bs,
            source=self.name,
            min_quarters=min_quarters,
        )


# ---------------------------------------------------------------------------
# EODHDProvider — reliable paid API ($50/mo Fundamentals Data Feed)
# ---------------------------------------------------------------------------

class EODHDProvider(DataProvider):
    """Financial data from EODHD Fundamentals API.

    Requires EODHD_API_KEY in environment. Uses the /fundamentals endpoint
    which returns quarterly + annual income statements, balance sheets, and
    cash flow statements for US equities.

    API docs: https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds
    """

    BASE_URL = "https://eodhd.com/api/fundamentals"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("EODHD_API_KEY", "")
        if not self._api_key:
            raise EarningsFetchError(
                "EODHD_API_KEY not set. Add it to .env or pass it to EODHDProvider()."
            )

    @property
    def name(self) -> str:
        return "EODHD Fundamentals API"

    # ── Field mapping: EODHD names → canonical names ──
    # EODHD uses camelCase field names. We map them to the canonical names
    # used throughout the engine (which match yfinance's naming convention).
    IS_MAP = {
        "totalRevenue": "Total Revenue",
        "costOfRevenue": "Cost Of Revenue",
        "grossProfit": "Gross Profit",
        "sellingGeneralAdministrative": "Selling General And Administration",
        "researchDevelopment": "Research And Development",
        "operatingIncome": "Operating Income",
        "ebitda": "EBITDA",
        "normalizedEBITDA": "Normalized EBITDA",
        "interestExpense": "Interest Expense",
        "netNonOperatingInterestIncomeExpense": "Net Non Operating Interest Income Expense",
        "incomeBeforeTax": "Pretax Income",
        "incomeTaxExpense": "Tax Provision",
        "netIncome": "Net Income",
        "dilutedAverageShares": "Diluted Average Shares",
        "basicAverageShares": "Basic Average Shares",
        "dilutedEPS": "Diluted EPS",
        "basicEPS": "Basic EPS",
    }
    CF_MAP = {
        "totalCashFromOperatingActivities": "Operating Cash Flow",
        "capitalExpenditures": "Capital Expenditure",
        "freeCashFlow": "Free Cash Flow",
        "stockBasedCompensation": "Stock Based Compensation",
        "depreciation": "Depreciation And Amortization",
        "changeInWorkingCapital": "Change In Working Capital",
        "netIncome": "Net Income From Continuing Operations",
    }
    BS_MAP = {
        "cash": "Cash And Cash Equivalents",
        "cashAndShortTermInvestments": "Cash Cash Equivalents And Short Term Investments",
        "totalCurrentAssets": "Current Assets",
        "totalAssets": "Total Assets",
        "shortTermDebt": "Current Debt",
        "longTermDebt": "Long Term Debt",
        "totalDebt": "Total Debt",
        "totalCurrentLiabilities": "Current Liabilities",
        "totalLiab": "Total Liabilities Net Minority Interest",
        "netTangibleAssets": "Net PPE",
        "goodWill": "Goodwill And Other Intangible Assets",
        "commonStockSharesOutstanding": "Ordinary Shares Number",
        "commonStock": "Share Issued",
        "totalStockholderEquity": "Stockholders Equity",
    }

    def _map_periods(
        self, raw: dict, field_map: dict, freq: str
    ) -> list[dict]:
        """Convert EODHD JSON periods to canonical format.

        EODHD returns: {"quarterly": {"2024-09-30": {...}, ...}}
        We convert to: [{"period": "3Q24", "date": "2024-09-30", "Total Revenue": 1.2e9, ...}]
        """
        section = raw.get("quarterly" if freq == "quarterly" else "yearly", {})
        if not section:
            return []

        periods = []
        for date_str in sorted(section.keys()):
            row = section[date_str]
            pd_ = {"period": _period_label(date_str, freq), "date": date_str[:10]}
            for eodhd_key, canonical_key in field_map.items():
                pd_[canonical_key] = _to_float(row.get(eodhd_key))
            periods.append(pd_)
        return periods

    def _derive_fcf(self, cf_periods: list[dict]) -> None:
        """Derive Free Cash Flow if EODHD doesn't provide it directly.
        FCF = Operating Cash Flow - abs(Capital Expenditure)."""
        for p in cf_periods:
            if p.get("Free Cash Flow") is None:
                ocf = p.get("Operating Cash Flow")
                capex = p.get("Capital Expenditure")
                if ocf is not None and capex is not None:
                    # capex is usually negative in EODHD; FCF = OCF + capex (if neg)
                    p["Free Cash Flow"] = ocf + capex if capex < 0 else ocf - abs(capex)

    def fetch(self, ticker: str, min_quarters: int = 4) -> FinancialData:
        import json
        try:
            import requests
        except ImportError as e:
            raise ImportError(
                "requests is required for EODHD provider. Install with:\n"
                "  pip install requests --break-system-packages"
            ) from e

        ticker = ticker.upper().strip()
        if not ticker:
            raise EarningsFetchError("empty ticker")

        # EODHD uses "TICKER.EXCHANGE" format.
        # If the ticker already contains an exchange suffix (.HK, .T, .TW, .L, etc.),
        # use it as-is. Otherwise, default to .US for US equities.
        if "." in ticker:
            eodhd_ticker = ticker  # Already has exchange suffix (e.g. 6082.HK, 7203.T)
        else:
            eodhd_ticker = f"{ticker}.US"
        url = f"{self.BASE_URL}/{eodhd_ticker}?api_token={self._api_key}&fmt=json"

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise EarningsFetchError(f"{ticker}: EODHD API request failed: {e}") from e
        except json.JSONDecodeError as e:
            raise EarningsFetchError(f"{ticker}: EODHD returned invalid JSON: {e}") from e

        if not data or isinstance(data, list):
            raise EarningsFetchError(
                f"{ticker}: EODHD returned empty/unexpected data. "
                f"Ticker may not be covered."
            )

        # Extract financials sections
        financials = data.get("Financials", {})
        income_stmt = financials.get("Income_Statement", {})
        cash_flow = financials.get("Cash_Flow", {})
        balance_sheet = financials.get("Balance_Sheet", {})

        # Convert to canonical format
        q_inc = self._map_periods(income_stmt, self.IS_MAP, "quarterly")
        a_inc = self._map_periods(income_stmt, self.IS_MAP, "annual")
        q_cf = self._map_periods(cash_flow, self.CF_MAP, "quarterly")
        a_cf = self._map_periods(cash_flow, self.CF_MAP, "annual")
        q_bs = self._map_periods(balance_sheet, self.BS_MAP, "quarterly")
        a_bs = self._map_periods(balance_sheet, self.BS_MAP, "annual")

        # If EODHD returned valid JSON but no actual financial periods,
        # treat it as a coverage gap so the yfinance fallback can retry.
        # Common for non-US tickers (e.g. .HK, .T) not covered by EODHD.
        if not q_inc and not a_inc:
            raise EarningsFetchError(
                f"{ticker}: EODHD returned empty financials (0 income statement "
                f"periods). Ticker may not be covered by EODHD."
            )

        # Derive FCF if not directly available
        self._derive_fcf(q_cf)
        self._derive_fcf(a_cf)

        # Build info dict from General section
        general = data.get("General", {})
        highlights = data.get("Highlights", {})
        info = {
            "name": general.get("Name") or ticker,
            "longName": general.get("Name"),
            "sector": general.get("Sector") or "Unknown",
            "currency": general.get("CurrencyCode") or "USD",
            "price": None,  # will be set from live quote below
            "marketCap": highlights.get("MarketCapitalization"),
            "sharesOutstanding": data.get("SharesStats", {}).get("SharesOutstanding"),
        }

        # EODHD Fundamentals doesn't serve live quotes — pull current price
        # from Alpha Vantage GLOBAL_QUOTE (lightweight, real-time).
        live = _fetch_live_price_av(ticker)
        if live["price"] and live["price"] > 0:
            info["price"] = live["price"]
            # Derive market cap from live price × shares if EODHD's is stale
            shares = data.get("SharesStats", {}).get("SharesOutstanding")
            if shares is not None:
                try:
                    s = float(shares)
                    if s > 0:
                        info["marketCap"] = live["price"] * s
                except (ValueError, TypeError):
                    pass
        else:
            # Fallback chain for live price:
            # 1. For non-US tickers (.HK, .T, .TW, etc.), try yfinance quick quote
            if "." in ticker:
                try:
                    import yfinance as _yf
                    _ytk = _yf.Ticker(ticker)
                    _yinfo = _ytk.info or {}
                    _yprice = _yinfo.get("currentPrice") or _yinfo.get("regularMarketPrice")
                    if _yprice and float(_yprice) > 0:
                        # Convert to USD if needed for consistency
                        _currency = _yinfo.get("currency", "USD")
                        info["price"] = float(_yprice)
                        info["currency"] = _currency
                        print(
                            f"  [finance_data] {ticker}: live price ${_yprice:.2f} "
                            f"({_currency}) via yfinance fallback",
                            file=sys.stderr,
                        )
                except Exception as _yfe:
                    print(
                        f"  [finance_data] WARNING: {ticker} yfinance price fallback failed: {_yfe}",
                        file=sys.stderr,
                    )

            # 2. 50DayMA is a rough approximation — NOT a live price.
            #    WallStreetTargetPrice is analyst consensus and must NEVER be used.
            if info["price"] is None or info["price"] == 0:
                last_price = highlights.get("50DayMA")
                if last_price and float(last_price) > 0:
                    info["price"] = float(last_price)
                    print(
                        f"  [finance_data] WARNING: {ticker} using 50DayMA "
                        f"(${last_price}) as price — all live quote sources failed",
                        file=sys.stderr,
                    )

        return _validate_and_build(
            ticker=ticker,
            info=info,
            q_inc=q_inc, q_cf=q_cf, q_bs=q_bs,
            a_inc=a_inc, a_cf=a_cf, a_bs=a_bs,
            source=self.name,
            min_quarters=min_quarters,
        )


# ---------------------------------------------------------------------------
# AlphaVantageProvider — free tier, rate-limited (5 calls/min, 500/day)
# ---------------------------------------------------------------------------

class AlphaVantageProvider(DataProvider):
    """Financial data from Alpha Vantage API.

    Requires ALPHA_VANTAGE_API_KEY in environment. Uses the
    INCOME_STATEMENT, BALANCE_SHEET, and CASH_FLOW functions.

    Note: free tier is severely rate-limited (5 API calls/min, 500/day).
    Each ticker requires 3 API calls (one per statement). Use primarily
    as a cross-validation source, not as the primary provider.
    """

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        if not self._api_key:
            raise EarningsFetchError(
                "ALPHA_VANTAGE_API_KEY not set. Add it to .env or pass it to AlphaVantageProvider()."
            )

    @property
    def name(self) -> str:
        return "Alpha Vantage"

    # Field mapping: Alpha Vantage → canonical
    IS_MAP = {
        "totalRevenue": "Total Revenue",
        "costOfRevenue": "Cost Of Revenue",
        "grossProfit": "Gross Profit",
        "sellingGeneralAndAdministrative": "Selling General And Administration",
        "researchAndDevelopment": "Research And Development",
        "operatingIncome": "Operating Income",
        "ebitda": "EBITDA",
        "interestExpense": "Interest Expense",
        "incomeBeforeTax": "Pretax Income",
        "incomeTaxExpense": "Tax Provision",
        "netIncome": "Net Income",
        "dilutedEPS": "Diluted EPS",
        "basicEPS": "Basic EPS",
    }
    CF_MAP = {
        "operatingCashflow": "Operating Cash Flow",
        "capitalExpenditures": "Capital Expenditure",
        "stockBasedCompensation": "Stock Based Compensation",
        "depreciationDepletionAndAmortization": "Depreciation And Amortization",
        "changeInWorkingCapital": "Change In Working Capital",
        "netIncome": "Net Income From Continuing Operations",
    }
    BS_MAP = {
        "cashAndCashEquivalentsAtCarryingValue": "Cash And Cash Equivalents",
        "cashAndShortTermInvestments": "Cash Cash Equivalents And Short Term Investments",
        "totalCurrentAssets": "Current Assets",
        "totalAssets": "Total Assets",
        "shortTermDebt": "Current Debt",
        "longTermDebt": "Long Term Debt",
        "totalCurrentLiabilities": "Current Liabilities",
        "totalLiabilities": "Total Liabilities Net Minority Interest",
        "propertyPlantEquipment": "Net PPE",
        "goodwill": "Goodwill And Other Intangible Assets",
        "commonStockSharesOutstanding": "Ordinary Shares Number",
        "commonStock": "Share Issued",
        "totalShareholderEquity": "Stockholders Equity",
    }

    def _fetch_statement(self, function: str, ticker: str) -> dict:
        """Fetch one financial statement from Alpha Vantage."""
        import requests
        params = {
            "function": function,
            "symbol": ticker,
            "apikey": self._api_key,
        }
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise EarningsFetchError(
                f"{ticker}: Alpha Vantage {function} request failed: {e}"
            ) from e

    def _map_av_periods(
        self, reports: list[dict], field_map: dict, freq: str
    ) -> list[dict]:
        """Convert Alpha Vantage report list to canonical format."""
        periods = []
        for report in reports:
            date_str = report.get("fiscalDateEnding", "")
            pd_ = {"period": _period_label(date_str, freq), "date": date_str}
            for av_key, canonical_key in field_map.items():
                val = report.get(av_key)
                pd_[canonical_key] = _to_float(val) if val != "None" else None
            periods.append(pd_)
        # Alpha Vantage returns most recent first; reverse to chronological
        periods.reverse()
        return periods

    def fetch(self, ticker: str, min_quarters: int = 4) -> FinancialData:
        import time

        ticker = ticker.upper().strip()
        if not ticker:
            raise EarningsFetchError("empty ticker")

        # Fetch all three statements (3 API calls)
        is_data = self._fetch_statement("INCOME_STATEMENT", ticker)
        time.sleep(12.5)  # respect 5 calls/min rate limit
        cf_data = self._fetch_statement("CASH_FLOW", ticker)
        time.sleep(12.5)
        bs_data = self._fetch_statement("BALANCE_SHEET", ticker)

        # Check for error responses
        for name, d in [("income", is_data), ("cashflow", cf_data), ("balance", bs_data)]:
            if "Error Message" in d or "Note" in d:
                msg = d.get("Error Message") or d.get("Note", "rate limited")
                raise EarningsFetchError(f"{ticker}: Alpha Vantage {name}: {msg}")

        q_inc = self._map_av_periods(
            is_data.get("quarterlyReports", []), self.IS_MAP, "quarterly"
        )
        a_inc = self._map_av_periods(
            is_data.get("annualReports", []), self.IS_MAP, "annual"
        )
        q_cf = self._map_av_periods(
            cf_data.get("quarterlyReports", []), self.CF_MAP, "quarterly"
        )
        a_cf = self._map_av_periods(
            cf_data.get("annualReports", []), self.CF_MAP, "annual"
        )
        q_bs = self._map_av_periods(
            bs_data.get("quarterlyReports", []), self.BS_MAP, "quarterly"
        )
        a_bs = self._map_av_periods(
            bs_data.get("annualReports", []), self.BS_MAP, "annual"
        )

        # Derive FCF (Alpha Vantage doesn't always provide it directly)
        for cf_list in (q_cf, a_cf):
            for p in cf_list:
                if p.get("Free Cash Flow") is None:
                    ocf = p.get("Operating Cash Flow")
                    capex = p.get("Capital Expenditure")
                    if ocf is not None and capex is not None:
                        p["Free Cash Flow"] = ocf + capex if capex < 0 else ocf - abs(capex)

        # Total Debt derivation
        for bs_list in (q_bs, a_bs):
            for p in bs_list:
                if p.get("Total Debt") is None:
                    lt = p.get("Long Term Debt") or 0
                    st = p.get("Current Debt") or 0
                    if lt or st:
                        p["Total Debt"] = lt + st

        # Alpha Vantage OVERVIEW endpoint for company info
        overview = self._fetch_statement("OVERVIEW", ticker)
        info = {
            "name": overview.get("Name") or ticker,
            "longName": overview.get("Name"),
            "sector": overview.get("Sector") or "Unknown",
            "currency": overview.get("Currency") or "USD",
            "marketCap": overview.get("MarketCapitalization"),
            "sharesOutstanding": overview.get("SharesOutstanding"),
            "price": None,  # Alpha Vantage OVERVIEW doesn't include current price
        }

        return _validate_and_build(
            ticker=ticker,
            info=info,
            q_inc=q_inc, q_cf=q_cf, q_bs=q_bs,
            a_inc=a_inc, a_cf=a_cf, a_bs=a_bs,
            source=self.name,
            min_quarters=min_quarters,
        )


# ---------------------------------------------------------------------------
# Provider selection and public API
# ---------------------------------------------------------------------------

# Registry of available providers
_PROVIDER_REGISTRY: dict[str, type[DataProvider]] = {
    "yfinance": YFinanceProvider,
    "eodhd": EODHDProvider,
    "alpha_vantage": AlphaVantageProvider,
}


def _ensure_env_loaded():
    """Load .env if not already loaded (idempotent)."""
    if os.environ.get("_FINANCE_DATA_ENV_LOADED"):
        return
    try:
        from utils import load_env
        load_env()
    except Exception:
        pass  # utils may not be on path; env vars set externally
    os.environ["_FINANCE_DATA_ENV_LOADED"] = "1"


def get_provider(name: str | None = None) -> DataProvider:
    """Get a data provider instance by name.

    Precedence:
      1. Explicit `name` argument
      2. FINANCE_DATA_PROVIDER env var
      3. Auto-detect: try EODHD (if key present), else yfinance

    Returns an instantiated DataProvider ready to call .fetch().
    """
    _ensure_env_loaded()
    provider_name = name or os.environ.get("FINANCE_DATA_PROVIDER", "").strip().lower()

    if provider_name:
        cls = _PROVIDER_REGISTRY.get(provider_name)
        if cls is None:
            available = ", ".join(_PROVIDER_REGISTRY.keys())
            raise ValueError(
                f"Unknown provider '{provider_name}'. Available: {available}"
            )
        return cls()

    # Auto-detect: prefer EODHD if key is set, else fall back to yfinance
    eodhd_key = os.environ.get("EODHD_API_KEY", "").strip()
    if eodhd_key:
        print("  [finance_data] Auto-selected EODHD provider (EODHD_API_KEY present)", file=sys.stderr)
        return EODHDProvider(api_key=eodhd_key)

    return YFinanceProvider()


def fetch_financials(ticker: str, min_quarters: int = 4) -> FinancialData:
    """Fetch historical financials for `ticker` using the configured provider.

    This is the public API that all downstream consumers call. The provider
    is selected via get_provider() — see its docstring for precedence rules.

    If the primary provider (EODHD) fails and yfinance is available as a
    fallback, it retries with yfinance automatically. This ensures the
    pipeline doesn't halt due to transient EODHD API issues.

    Parameters
    ----------
    ticker : str
        Stock symbol (e.g. "LITE").
    min_quarters : int
        Minimum quarterly periods required. Default 4 (one year of history).

    Raises
    ------
    EarningsFetchError
        If ALL providers fail. The last error is raised.
    """
    # ── Check for known delisted tickers ──
    upper = ticker.upper()
    if upper in DELISTED_TICKERS:
        raise EarningsFetchError(
            f"{ticker} is delisted/inactive: {DELISTED_TICKERS[upper]}"
        )

    provider = get_provider()
    try:
        result = provider.fetch(ticker, min_quarters=min_quarters)
    except EarningsFetchError as primary_err:
        # If the primary provider is not yfinance, try yfinance as fallback
        if provider.name != "yfinance":
            print(
                f"  [finance_data] {provider.name} failed for {ticker}: {primary_err}",
                file=sys.stderr,
            )
            print(
                f"  [finance_data] Falling back to yfinance for {ticker}...",
                file=sys.stderr,
            )
            try:
                fallback = YFinanceProvider()
                result = fallback.fetch(ticker, min_quarters=min_quarters)
                result.warnings.append(
                    f"FALLBACK: Used yfinance instead of {provider.name} "
                    f"(primary error: {primary_err})"
                )
            except EarningsFetchError:
                raise primary_err  # fallback also failed — raise the original
        else:
            raise

    # ── Apply data cutoffs for re-IPO'd / entity-change tickers ──
    if upper in TICKER_DATA_CUTOFFS:
        for attr, freq in [
            ("quarterly_income", "quarterly"), ("quarterly_cashflow", "quarterly"),
            ("quarterly_balance", "quarterly"), ("annual_income", "annual"),
            ("annual_cashflow", "annual"), ("annual_balance", "annual"),
        ]:
            periods = getattr(result, attr, [])
            filtered, cutoff_warnings = _apply_data_cutoff(upper, periods, freq)
            setattr(result, attr, filtered)
            result.warnings.extend(cutoff_warnings)

    return result


# ---------------------------------------------------------------------------
# Cross-validation utility
# ---------------------------------------------------------------------------

# Severity thresholds for cross-validation discrepancies.
# A 5% revenue discrepancy compounds multiplicatively through 5-year forecasts
# (~27% at Year 5), flowing into EBITDA, FCF, and terminal value.
CROSS_VALIDATION_WARN_THRESHOLD = 0.03   # >3% → WARNING in engine warnings
CROSS_VALIDATION_HALT_THRESHOLD = 0.10   # >10% → HALT (raise, don't silently use bad data)


def cross_validate(ticker: str, primary: str = "eodhd", secondary: str = "yfinance",
                   warn_threshold: float = CROSS_VALIDATION_WARN_THRESHOLD,
                   halt_threshold: float = CROSS_VALIDATION_HALT_THRESHOLD) -> dict:
    """Run both providers and compare key metrics.

    Returns a dict with comparison results, severity-tiered discrepancies,
    and resolution logic documentation.

    Severity tiers:
      - match:   discrepancy ≤ warn_threshold (3%) — expected noise from
                 fiscal-year alignment, FX translation, stock splits
      - warning: warn_threshold < discrepancy ≤ halt_threshold (3–10%) —
                 surface in engine warnings; use primary provider's value
      - halt:    discrepancy > halt_threshold (10%) — data quality is
                 unreliable; caller should not trust either source blindly

    Resolution logic: the PRIMARY provider's data is always used for the
    engine. The secondary is a sanity check. When sources disagree:
      - Revenue, EBITDA, FCF: common causes are fiscal-year alignment
        (EODHD uses calendar quarters, yfinance uses company fiscal quarters),
        FX translation differences, and stock-split adjustments.
      - Market cap, shares: timing differences (yesterday's close vs today's).
    """
    results: dict[str, Any] = {"ticker": ticker, "primary": primary, "secondary": secondary}

    _ensure_env_loaded()

    try:
        p1 = _PROVIDER_REGISTRY[primary]()
        fin1 = p1.fetch(ticker)
    except Exception as e:
        results["primary_error"] = str(e)
        return results

    try:
        p2 = _PROVIDER_REGISTRY[secondary]()
        fin2 = p2.fetch(ticker)
    except Exception as e:
        results["secondary_error"] = str(e)
        return results

    # Compare key metrics
    metrics = {
        "ttm_revenue": (fin1.ttm_revenue(), fin2.ttm_revenue()),
        "ttm_ebitda": (fin1.ttm_ebitda(), fin2.ttm_ebitda()),
        "ttm_fcf": (fin1.ttm_fcf(), fin2.ttm_fcf()),
        "ttm_operating_income": (fin1.ttm_operating_income(), fin2.ttm_operating_income()),
        "market_cap": (fin1.market_cap, fin2.market_cap),
        "shares_diluted": (fin1.shares_diluted, fin2.shares_diluted),
        "net_debt": (fin1.net_debt, fin2.net_debt),
    }

    warnings_list: list[dict] = []
    halts: list[dict] = []
    matches: list[str] = []

    for name, (v1, v2) in metrics.items():
        if v1 is None or v2 is None:
            warnings_list.append({"metric": name, "primary": v1, "secondary": v2,
                                  "severity": "warning", "note": "one source missing"})
            continue
        if v2 == 0:
            if v1 != 0:
                warnings_list.append({"metric": name, "primary": v1, "secondary": v2,
                                      "severity": "warning", "note": "secondary=0"})
            else:
                matches.append(name)
            continue
        pct_diff = abs(v1 - v2) / abs(v2)
        if pct_diff > halt_threshold:
            halts.append({
                "metric": name,
                "primary": round(v1, 2),
                "secondary": round(v2, 2),
                "pct_diff": round(pct_diff * 100, 1),
                "severity": "halt",
            })
        elif pct_diff > warn_threshold:
            warnings_list.append({
                "metric": name,
                "primary": round(v1, 2),
                "secondary": round(v2, 2),
                "pct_diff": round(pct_diff * 100, 1),
                "severity": "warning",
            })
        else:
            matches.append(name)

    results["match"] = len(warnings_list) == 0 and len(halts) == 0
    results["warnings"] = warnings_list
    results["halts"] = halts
    results["matched_metrics"] = matches
    results["quarterly_periods"] = {
        primary: len(fin1.quarterly_income),
        secondary: len(fin2.quarterly_income),
    }
    # Backward-compat: combine for callers expecting flat "discrepancies"
    results["discrepancies"] = warnings_list + halts
    return results


# ---------------------------------------------------------------------------
# Standalone CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    tk = (args[0] if args else "LITE").upper()

    # Optional: --provider=eodhd / --cross-validate
    provider_name = None
    do_cross_validate = False
    for a in args[1:]:
        if a.startswith("--provider="):
            provider_name = a.split("=", 1)[1]
        elif a == "--cross-validate":
            do_cross_validate = True

    if do_cross_validate:
        import json
        result = cross_validate(tk)
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result.get("match") else 1)

    try:
        provider = get_provider(provider_name)
        print(f"Using provider: {provider.name}")
        f = provider.fetch(tk)
    except EarningsFetchError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    print(f"=== {f.ticker} ({f.name}) — {f.sector} ===")
    print(f"Source:     {f.source}")
    print(f"Price:      ${f.price:,.2f}")
    print(f"Market cap: ${(f.market_cap or 0)/1e9:,.2f}B")
    print(f"Shares:     {(f.shares_diluted or 0)/1e6:,.1f}M diluted")
    print(f"Net debt:   ${(f.net_debt or 0)/1e9:,.2f}B")
    print(f"TTM revenue:${(f.ttm_revenue() or 0)/1e9:,.2f}B")
    print(f"TTM OpInc:  ${(f.ttm_operating_income() or 0)/1e9:,.2f}B")
    print(f"TTM FCF:    ${(f.ttm_fcf() or 0)/1e9:,.2f}B")
    print(f"TTM EBITDA: ${(f.ttm_ebitda() or 0)/1e9:,.2f}B")
    print(f"\nQuarterly history ({len(f.quarterly_income)} periods):")
    for p in f.quarterly_income:
        rev = (p.get("Total Revenue") or 0) / 1e9
        oi = (p.get("Operating Income") or 0) / 1e9
        print(f"  {p['period']} ({p['date']}): rev=${rev:.2f}B, opinc=${oi:.2f}B")
    print(f"\nAnnual history ({len(f.annual_income)} periods):")
    for p in f.annual_income:
        rev = (p.get("Total Revenue") or 0) / 1e9
        oi = (p.get("Operating Income") or 0) / 1e9
        print(f"  {p['period']} ({p['date']}): rev=${rev:.2f}B, opinc=${oi:.2f}B")
    if f.warnings:
        print(f"\nWarnings:")
        for w in f.warnings:
            print(f"  {w}")
