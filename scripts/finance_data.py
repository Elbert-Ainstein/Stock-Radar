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

import json
import math
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path as _Path
from typing import Any


class EarningsFetchError(Exception):
    """Raised when we cannot obtain historical earnings data for a ticker.
    Model generation MUST halt when this is raised — never silently estimate."""


# ---------------------------------------------------------------------------
# Shared constants and utilities (provider-agnostic)
# ---------------------------------------------------------------------------

# Number of trailing quarters used for TTM. Suspect-data hard-fails apply
# to this window because TTM corrupts the entire downstream model.
# IMPORTANT: keep this in sync with any other place that computes TTM.
TTM_QUARTERS = 4

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


_TICKER_ARCHETYPES_CACHE: dict | None = None
_TICKER_ARCHETYPES_CACHE_MTIME: float = 0.0


def _load_ticker_archetypes() -> dict:
    """Load and cache config/ticker_archetypes.json with mtime invalidation.

    Returns a dict mapping uppercase ticker → archetype string. Used by
    `_archetype_threshold_multiplier()` to relax sanity-check thresholds
    for cyclical tickers where 2-3x sequential revenue jumps are real
    (memory chips at HBM ramp, semis at cycle peak) — not data errors.

    Cache is invalidated when the JSON file's mtime changes so operator
    edits during a long-running process pick up automatically. Per
    red-team review 2026-05-09: previously module-global cache was set
    once and ignored config edits, silently dropping new ticker tags.

    Empty dict on missing/malformed config; archetype tagging is optional
    and a missing config should never break the default flow. Logs once
    on first-time load so operators can verify it loaded.
    """
    global _TICKER_ARCHETYPES_CACHE, _TICKER_ARCHETYPES_CACHE_MTIME
    cfg_path = _Path(__file__).resolve().parent.parent / "config" / "ticker_archetypes.json"
    # mtime-based cache invalidation
    try:
        mtime = cfg_path.stat().st_mtime
    except FileNotFoundError:
        if _TICKER_ARCHETYPES_CACHE is None:
            _TICKER_ARCHETYPES_CACHE = {}
        return _TICKER_ARCHETYPES_CACHE
    if _TICKER_ARCHETYPES_CACHE is not None and mtime == _TICKER_ARCHETYPES_CACHE_MTIME:
        return _TICKER_ARCHETYPES_CACHE
    # (re)load
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [finance_data] ticker_archetypes config load failed: {e}", file=sys.stderr)
        _TICKER_ARCHETYPES_CACHE = {}
        _TICKER_ARCHETYPES_CACHE_MTIME = mtime
        return _TICKER_ARCHETYPES_CACHE
    _TICKER_ARCHETYPES_CACHE = {
        k.upper(): v for k, v in raw.items()
        if not k.startswith("_") and isinstance(v, str)
    }
    _TICKER_ARCHETYPES_CACHE_MTIME = mtime
    print(f"  [finance_data] ticker_archetypes loaded: {len(_TICKER_ARCHETYPES_CACHE)} entries", file=sys.stderr)
    return _TICKER_ARCHETYPES_CACHE


# Threshold multipliers for the sanity check. Cyclicals legitimately ramp
# 2-3x at cycle peaks (memory: $13.6B Q1 FY26 → $23.86B Q2 FY26 was real,
# verified via Micron Q2 FY26 press release). Default 2.0x trailing / 2.5x
# YoY thresholds were calibrated on secular growers and over-flag cyclicals.
_ARCHETYPE_THRESHOLD_MULTIPLIER: dict = {
    "cyclical_tech":        1.5,   # memory chips, semis equipment, networking
    "cyclical_industrial":  1.4,   # autos, chemicals, materials
    "cyclical_normalized":  1.5,   # handled by engine but tagged here for completeness
    "secular_growth":       1.0,   # software, fintech (default behavior)
    "compounder":           1.0,   # stable margin business (default behavior)
}


def _archetype_threshold_multiplier(ticker: str | None) -> tuple[float, str | None]:
    """Look up the threshold multiplier for a ticker's archetype.

    Returns (multiplier, archetype_name). Default (1.0, None) if no
    archetype is configured for the ticker — equivalent to current behavior.
    """
    if not ticker:
        return 1.0, None
    archetypes = _load_ticker_archetypes()
    arch = archetypes.get(ticker.upper())
    if not arch:
        return 1.0, None
    mult = _ARCHETYPE_THRESHOLD_MULTIPLIER.get(arch, 1.0)
    return mult, arch


def _validate_quarterly_revenue(periods: list[dict], ticker: str | None = None) -> tuple[list[str], set[int]]:
    """Detect quarters with suspicious revenue spikes.

    Checks two signals for each quarter:
    1. Revenue > Nx the trailing 4Q average (rolling anomaly)
    2. Revenue > Mx same-quarter-last-year (YoY anomaly)

    Thresholds are size-aware AND archetype-aware:
    - Large-cap (trailing avg ≥ $500M/Q): 2.0x trailing, 2.5x YoY
      → catches data-provider errors
    - Mid-cap ($100M–$500M): 3.0x trailing, 4.0x YoY
      → moderate tolerance for business lumpiness
    - Micro/small-cap (< $100M/Q): 5.0x trailing, 6.0x YoY
      → high tolerance; $5M→$15M quarter swings are normal order
        lumpiness for semi-equipment, biotech, and niche industrials
    - Cyclical archetypes (cyclical_tech, cyclical_industrial,
      cyclical_normalized) get a 1.4-1.5x multiplier on top, so a
      memory company doing $13.6B → $23.86B (real Q2 FY26 ramp) doesn't
      false-positive while still catching the genuine $40B → $80B
      provider bugs. Configured via config/ticker_archetypes.json.

    Returns a list of warning strings + suspect indices. Called AFTER period
    conversion so we can catch bad data before it poisons TTM calculations.

    Pre-2026-05-09: this check fired on real cyclical ramps and blocked
    valid model rendering (the MU misdiagnosis). The archetype multiplier
    is the architectural fix.
    """
    warnings: list[str] = []
    suspect_indices: set[int] = set()
    if not periods:
        return warnings, suspect_indices

    # Archetype-aware multiplier: relax thresholds for cyclical tickers
    # whose real revenue swings can hit 2-3x at cycle inflections.
    arch_mult, arch_name = _archetype_threshold_multiplier(ticker)
    if arch_name and arch_mult != 1.0:
        print(f"  [{ticker}] archetype={arch_name}, applying {arch_mult}x sanity-check multiplier", file=sys.stderr)

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

            # Size-aware thresholds: micro-caps have lumpy revenue by nature.
            # Two thresholds computed: base (no multiplier) and applied
            # (with archetype multiplier). Lets us distinguish "real cyclical
            # ramp accommodated by multiplier" from "actual suspect data."
            if trailing_avg >= 500e6:       # Large-cap: ≥$500M/Q
                trailing_thresh_base = 2.0
            elif trailing_avg >= 100e6:     # Mid-cap: $100M–$500M/Q
                trailing_thresh_base = 3.0
            else:                           # Micro/small-cap: <$100M/Q
                trailing_thresh_base = 5.0
            trailing_thresh = trailing_thresh_base * arch_mult

            if trailing_avg > 0 and rev > trailing_thresh * trailing_avg:
                # Exceeds the applied threshold (with multiplier) — real suspect.
                ratio = rev / trailing_avg
                warnings.append(
                    f"SUSPECT DATA: {period_label} revenue "
                    f"${rev/1e9:.2f}B is {ratio:.1f}x the trailing "
                    f"{len(prior_revs)}Q avg ${trailing_avg/1e9:.2f}B "
                    f"(threshold: {trailing_thresh:.1f}x for this revenue scale"
                    f"{', archetype=' + arch_name if arch_name else ''}). "
                    f"Possible data error — cross-check against "
                    f"10-Q filing before trusting this quarter."
                )
                suspect_indices.add(i)
            elif (arch_mult > 1.0 and trailing_avg > 0
                  and rev > trailing_thresh_base * trailing_avg):
                # Would have fired without the archetype multiplier — but the
                # multiplier is the architectural fix for legitimate cyclical
                # ramps. Emit a CYCLICAL_RAMP_NOTE (informational, distinct
                # prefix) rather than SUSPECT DATA so operators don't habituate
                # to ignoring real warnings later.
                ratio = rev / trailing_avg
                warnings.append(
                    f"CYCLICAL_RAMP_NOTE: {period_label} revenue "
                    f"${rev/1e9:.2f}B is {ratio:.1f}x the trailing "
                    f"{len(prior_revs)}Q avg ${trailing_avg/1e9:.2f}B — "
                    f"within archetype={arch_name} relaxed threshold "
                    f"({trailing_thresh:.1f}x), would have flagged at base "
                    f"({trailing_thresh_base:.1f}x). Real cyclical ramp; not "
                    f"a data error. Verify only if other warnings co-fire."
                )

        # Check 2: same-quarter-last-year (4 periods back in quarterly data)
        if i >= 4:
            yoy_rev = periods[i - 4].get("Total Revenue")
            if yoy_rev is not None and yoy_rev > 0:
                # Size-aware YoY thresholds (archetype multiplier applied).
                if yoy_rev >= 500e6:
                    yoy_thresh_base = 2.5
                elif yoy_rev >= 100e6:
                    yoy_thresh_base = 4.0
                else:
                    yoy_thresh_base = 6.0
                yoy_thresh = yoy_thresh_base * arch_mult

                if rev > yoy_thresh * yoy_rev:
                    ratio = rev / yoy_rev
                    warnings.append(
                        f"SUSPECT DATA: {period_label} revenue "
                        f"${rev/1e9:.2f}B is {ratio:.1f}x same-quarter-"
                        f"last-year ${yoy_rev/1e9:.2f}B "
                        f"(threshold: {yoy_thresh:.1f}x"
                        f"{', archetype=' + arch_name if arch_name else ''}). "
                        f"Verify against filing."
                    )
                    suspect_indices.add(i)
                elif arch_mult > 1.0 and rev > yoy_thresh_base * yoy_rev:
                    ratio = rev / yoy_rev
                    warnings.append(
                        f"CYCLICAL_RAMP_NOTE: {period_label} revenue "
                        f"${rev/1e9:.2f}B is {ratio:.1f}x YoY "
                        f"${yoy_rev/1e9:.2f}B — within archetype={arch_name} "
                        f"relaxed threshold ({yoy_thresh:.1f}x), would have "
                        f"flagged at base ({yoy_thresh_base:.1f}x). Real "
                        f"cycle YoY; not a data error."
                    )

    return warnings, suspect_indices


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


_MANUAL_QUARTERLY_OVERRIDES_CACHE: dict | None = None


def _load_manual_quarterly_overrides() -> dict:
    """Load and cache config/manual_quarterly_overrides.json.

    Returns operator-verified per-period overrides used when ALL upstream
    providers report the same wrong number for a quarter (typically a
    syndication-layer bug — e.g. MU 1Q26 where yfinance, EODHD, and
    AlphaVantage all returned $23.86B vs the 10-Q's $13.643B).

    Returns an empty dict if the file is missing or malformed — manual
    overrides are optional and a missing config should never break the
    default flow.
    """
    global _MANUAL_QUARTERLY_OVERRIDES_CACHE
    if _MANUAL_QUARTERLY_OVERRIDES_CACHE is not None:
        return _MANUAL_QUARTERLY_OVERRIDES_CACHE
    cfg_path = _Path(__file__).resolve().parent.parent / "config" / "manual_quarterly_overrides.json"
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _MANUAL_QUARTERLY_OVERRIDES_CACHE = {}
        return _MANUAL_QUARTERLY_OVERRIDES_CACHE
    except Exception as e:
        print(f"  [finance_data] manual overrides config load failed: {e}", file=sys.stderr)
        _MANUAL_QUARTERLY_OVERRIDES_CACHE = {}
        return _MANUAL_QUARTERLY_OVERRIDES_CACHE
    _MANUAL_QUARTERLY_OVERRIDES_CACHE = {
        k.upper(): v for k, v in raw.items()
        if not k.startswith("_") and isinstance(v, dict)
    }
    return _MANUAL_QUARTERLY_OVERRIDES_CACHE


# Numeric fields the override layer is allowed to patch. Anything else in the
# JSON config is treated as metadata (source, verified_by, note, etc.).
_OVERRIDABLE_NUMERIC_FIELDS = {
    # Income statement
    "Total Revenue", "Operating Income", "Net Income", "EBITDA",
    "Cost Of Revenue", "Gross Profit", "Research And Development",
    "Selling General And Administration", "Operating Expense",
    # Cash flow statement (patched in q_cf, not q_inc)
    "Depreciation", "Operating Cash Flow", "Capital Expenditure",
    "Free Cash Flow", "Amortization Of Intangibles",
}
_OVERRIDE_META_KEYS = {"source", "verified_by", "verified_on", "note"}


def _apply_manual_overrides(ticker: str, *period_lists: list[dict]) -> list[str]:
    """Patch one or more quarterly statements using
    config/manual_quarterly_overrides.json.

    Each positional arg is a quarterly statement list (q_inc, q_cf, etc.).
    The override applies field-by-field across whichever statement(s) contain
    the matching period and field name. Income-statement fields like
    "Total Revenue" land in q_inc; cash-flow fields like "Operating Cash Flow"
    land in q_cf. The same period dict in q_inc and q_cf is matched by its
    "period" string (e.g. "1Q26"), so a single config entry can patch the
    whole income + cash-flow row for a quarter.

    Mutates the period lists in place. Returns a list of warning strings
    describing each applied patch, so the user can see exactly what changed
    in the model warnings panel.

    CRITICAL: cumulative-mislabel bugs (FactSet/CapIQ syndication labeling
    FY-cumulative as Q1) inflate every flow row, not just revenue. Patching
    only revenue while leaving op income / D&A / OCF inflated produces wrong
    margins (the bug Hume caught: revenue patched but EBITDA margin reading
    77% vs real 61%). Always pull the full income statement AND cash flow.
    """
    overrides = _load_manual_quarterly_overrides()
    ticker_overrides = overrides.get(ticker.upper(), {})
    if not ticker_overrides:
        return []

    patches: list[str] = []
    for period_label, period_overrides in ticker_overrides.items():
        if period_label.startswith("_") or not isinstance(period_overrides, dict):
            continue

        # Collect every (period_dict, statement_index) where this period exists.
        # The same logical quarter typically has separate dicts in q_inc and q_cf.
        targets: list[dict] = []
        for stmt in period_lists:
            for p in stmt:
                if p.get("period") == period_label:
                    targets.append(p)
                    break  # one match per statement

        if not targets:
            patches.append(
                f"MANUAL_OVERRIDE: {ticker} {period_label} configured but period "
                f"not present in provider data — config may be stale."
            )
            continue

        # For each numeric field in the override, write it to whichever
        # statement(s) already have that field present. Falls back to the
        # FIRST statement (typically q_inc) if no statement has the field
        # yet — this handles the case where the provider didn't report a
        # specific line item and we want the override to provide it.
        applied_fields: list[str] = []
        for field_name, new_value in period_overrides.items():
            if field_name in _OVERRIDE_META_KEYS:
                continue
            if not isinstance(new_value, (int, float)) or isinstance(new_value, bool):
                continue

            wrote_to: list[str] = []
            had_field = False
            for t in targets:
                if field_name in t:
                    had_field = True
                    old_value = t.get(field_name)
                    t[field_name] = float(new_value)
                    if old_value is not None:
                        try:
                            diff_pct = abs(float(new_value) - float(old_value)) / max(1.0, abs(float(old_value))) * 100
                            wrote_to.append(f"was ${float(old_value)/1e9:.2f}B → ${float(new_value)/1e9:.2f}B ({diff_pct:.0f}%)")
                        except Exception:
                            wrote_to.append(f"was {old_value} → {new_value}")
                    else:
                        wrote_to.append(f"set ${float(new_value)/1e9:.2f}B (was null)")
            if not had_field:
                # Provider didn't have this field — write to the first target
                # so it shows up downstream.
                targets[0][field_name] = float(new_value)
                wrote_to.append(f"set ${float(new_value)/1e9:.2f}B (was missing)")

            applied_fields.append(f"{field_name} ({'; '.join(wrote_to)})")

        if applied_fields:
            src = period_overrides.get("source", "manual override")
            patches.append(
                f"MANUAL_OVERRIDE: {ticker} {period_label}: "
                f"{'; '.join(applied_fields)} — source: {src}"
            )

    return patches


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
    override_suspect_recent: bool = False,
) -> FinancialData:
    """Shared validation + FinancialData construction used by all providers.

    Takes the normalized period lists (already in canonical field names) and
    runs the standard validation pipeline: revenue sanity check, required
    line-item check, minimum coverage check, then builds the dataclass.
    """
    warnings: list[str] = list(extra_warnings or [])

    # Apply manual quarterly overrides BEFORE sanity check.
    # When upstream providers (yfinance, EODHD, AlphaVantage) all return the
    # same wrong number — typically a syndication-layer bug — the operator
    # can patch specific (ticker, period) cells from a verified 10-Q via
    # config/manual_quarterly_overrides.json. This way the sanity check
    # runs against corrected data and the model can render.
    manual_patches = _apply_manual_overrides(ticker, q_inc, q_cf)
    if manual_patches:
        warnings.extend(manual_patches)
        print(f"  [{ticker}] Manual quarterly overrides applied:", file=sys.stderr)
        for patch in manual_patches:
            print(f"    {patch}", file=sys.stderr)

    # Revenue sanity check (runs against post-override data)
    rev_warnings, suspect_indices = _validate_quarterly_revenue(q_inc, ticker=ticker)
    if rev_warnings:
        warnings.extend(rev_warnings)
        print(f"  [{ticker}] Revenue sanity check fired:", file=sys.stderr)
        for w in rev_warnings:
            print(f"    {w}", file=sys.stderr)

    # HARD-FAIL when a suspect quarter is in the most-recent TTM_QUARTERS:
    # those quarters drive TTM revenue and bad TTM corrupts every downstream
    # number. Per earnings-as-source-of-truth contract: never silently fall
    # back to estimates. Operator must verify against the 10-Q filing.
    # Override path: pass override_suspect_recent=True after manual verification
    # for legitimate large jumps (M&A, post-IPO, post-spinoff like SNDK).
    if suspect_indices and q_inc:
        n = len(q_inc)
        recent_window = set(range(max(0, n - TTM_QUARTERS), n))
        recent_suspects = sorted(suspect_indices & recent_window)
        if recent_suspects:
            recent_labels = [q_inc[i].get("period", f"idx-{i}") for i in recent_suspects]
            recent_warnings = [w for w in rev_warnings
                               if any(lbl in w for lbl in recent_labels)]
            if override_suspect_recent:
                warnings.append(
                    f"OVERRIDE_SUSPECT_RECENT: {ticker} {recent_labels} flagged "
                    f"by sanity check; operator override applied. Verify against 10-Q."
                )
                print(f"  [{ticker}] override_suspect_recent=True — building model "
                      f"despite sanity-check failure on {recent_labels}", file=sys.stderr)
            else:
                _arch_mult, _arch_name = _archetype_threshold_multiplier(ticker)
                _arch_note = (
                    f"archetype={_arch_name}, multiplier={_arch_mult}x applied"
                    if _arch_name else
                    "no archetype configured (default thresholds used)"
                )
                raise EarningsFetchError(
                    f"{ticker}: revenue sanity check FAILED on recent quarter(s) "
                    f"{recent_labels} (within last {TTM_QUARTERS}Q used for TTM). "
                    f"Thresholds applied: 2.0x trailing-avg / 2.5x YoY (large-cap base) "
                    f"× {_arch_mult}x ({_arch_note}). Cannot build a reliable model. "
                    f"Operator must verify against 10-Q. If data is genuinely correct "
                    f"(M&A, post-IPO, post-spinoff, or cyclical ramp beyond multiplier), "
                    f"pass override_suspect_recent=True to fetch_financials. To tag the "
                    f"ticker as cyclical going forward, add it to "
                    f"config/ticker_archetypes.json. Details:\n  "
                    + "\n  ".join(recent_warnings)
                )

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
    def fetch(self, ticker: str, min_quarters: int = 4,
              override_suspect_recent: bool = False) -> FinancialData:
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

    def fetch(self, ticker: str, min_quarters: int = 4,
              override_suspect_recent: bool = False) -> FinancialData:
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
            override_suspect_recent=override_suspect_recent,
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

    def fetch(self, ticker: str, min_quarters: int = 4,
              override_suspect_recent: bool = False) -> FinancialData:
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
            override_suspect_recent=override_suspect_recent,
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

    def fetch(self, ticker: str, min_quarters: int = 4,
              override_suspect_recent: bool = False) -> FinancialData:
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
            override_suspect_recent=override_suspect_recent,
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


# ---------------------------------------------------------------------------
# Per-ticker provider overrides
# ---------------------------------------------------------------------------
# yfinance has known per-ticker bugs (e.g. MU Q1 FY26 returns $23.86B vs the
# real ~$8.7B per the 10-Q — a 3x inflation). When the sanity check catches
# this, the model API can't render and the watchlist becomes unusable.
#
# This module loads `config/data_provider_overrides.json` (keyed by ticker)
# and builds a per-ticker provider chain. fetch_financials() walks the chain,
# trying each provider until one returns data that survives the sanity check.
# Providers in the `skip` list are never tried for that ticker.

_OVERRIDES_CACHE: dict | None = None

def _load_provider_overrides() -> dict:
    """Load and cache config/data_provider_overrides.json.

    Returns an empty dict if the file is missing or malformed — overrides are
    optional and a missing config should never break the default flow.
    """
    global _OVERRIDES_CACHE
    if _OVERRIDES_CACHE is not None:
        return _OVERRIDES_CACHE
    cfg_path = _Path(__file__).resolve().parent.parent / "config" / "data_provider_overrides.json"
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _OVERRIDES_CACHE = {}
        return _OVERRIDES_CACHE
    except Exception as e:
        print(f"  [finance_data] overrides config load failed: {e}", file=sys.stderr)
        _OVERRIDES_CACHE = {}
        return _OVERRIDES_CACHE
    # Filter out non-ticker keys (e.g. "_README" notes block) and non-dict values
    _OVERRIDES_CACHE = {
        k.upper(): v for k, v in raw.items()
        if not k.startswith("_") and isinstance(v, dict)
    }
    return _OVERRIDES_CACHE


def _build_provider_chain(ticker: str) -> list[str]:
    """Build the ordered list of providers to try for `ticker`.

    Order:
      1. config[ticker].provider             (explicit primary)
      2. config[ticker].fallback             (explicit fallbacks, in order)
      3. Env / auto-detected default         (eodhd if key, else yfinance)
      4. yfinance                            (universal last resort)

    Any provider in config[ticker].skip is excluded everywhere — this lets us
    say "for MU, NEVER try yfinance" so the bad data never leaks in.
    """
    overrides = _load_provider_overrides()
    cfg = overrides.get(ticker.upper(), {})
    skip = set(cfg.get("skip", []) or [])

    chain: list[str] = []

    def add(name: str | None) -> None:
        if not name:
            return
        if name in skip:
            return
        if name in chain:
            return
        if name not in _PROVIDER_REGISTRY:
            return
        chain.append(name)

    # 1. Explicit primary
    add(cfg.get("provider"))
    # 2. Explicit fallbacks
    for f in cfg.get("fallback", []) or []:
        add(f)
    # 3. Env override / auto-detected default
    env_choice = os.environ.get("FINANCE_DATA_PROVIDER", "").strip().lower()
    if env_choice:
        add(env_choice)
    else:
        # Auto-detect: prefer EODHD if key is set
        eodhd_key = os.environ.get("EODHD_API_KEY", "").strip()
        add("eodhd" if eodhd_key else "yfinance")
    # 4. Universal fallback
    add("yfinance")

    return chain


def get_provider(name: str | None = None) -> DataProvider:
    """Get a data provider instance by name.

    Precedence:
      1. Explicit `name` argument
      2. FINANCE_DATA_PROVIDER env var
      3. Auto-detect: try EODHD (if key present), else yfinance

    Returns an instantiated DataProvider ready to call .fetch().

    NOTE: For per-ticker provider selection (e.g. force MU through EODHD),
    use fetch_financials() — it consults config/data_provider_overrides.json
    and walks a fallback chain. get_provider() returns ONE provider only.
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


def fetch_financials(ticker: str, min_quarters: int = 4,
                     override_suspect_recent: bool = False) -> FinancialData:
    """Fetch historical financials for `ticker` using a provider chain.

    Per-ticker chain logic (config/data_provider_overrides.json):
      1. Override primary (e.g. MU → eodhd)
      2. Override fallbacks (e.g. MU fallback → alpha_vantage)
      3. Env / auto-detected default
      4. yfinance as universal last resort

    Each provider in the chain is tried in order. If a provider raises
    EarningsFetchError (which fires for both API failures AND sanity check
    failures), we log it and try the next provider. This means a ticker
    with bad yfinance data (like MU's inflated Q1 FY26) automatically falls
    through to EODHD without the user knowing.

    The returned `FinancialData.source` field tells you which provider
    actually served the data, and any provider attempts that failed are
    appended to `warnings` so the user can see "we tried yfinance first,
    fell back to eodhd."

    Parameters
    ----------
    ticker : str
        Stock symbol (e.g. "LITE").
    min_quarters : int
        Minimum quarterly periods required. Default 4 (one year of history).
    override_suspect_recent : bool
        If True, allow data even if the sanity check flags recent quarters
        as anomalous. Use only after manually verifying against the 10-Q.

    Raises
    ------
    EarningsFetchError
        If ALL providers in the chain fail. The last error is included.
    """
    _ensure_env_loaded()
    upper = ticker.upper()

    # ── Check for known delisted tickers ──
    if upper in DELISTED_TICKERS:
        raise EarningsFetchError(
            f"{ticker} is delisted/inactive: {DELISTED_TICKERS[upper]}"
        )

    # ── Build per-ticker provider chain ──
    chain = _build_provider_chain(upper)
    if not chain:
        raise EarningsFetchError(
            f"No usable providers for {ticker} after applying overrides. "
            f"Check config/data_provider_overrides.json"
        )

    overrides = _load_provider_overrides()
    cfg = overrides.get(upper, {})
    if cfg:
        print(
            f"  [finance_data] {ticker}: per-ticker override active "
            f"(primary={cfg.get('provider')}, skip={cfg.get('skip', [])}, "
            f"reason={cfg.get('reason', '')[:60]}...)",
            file=sys.stderr,
        )

    last_err: Exception | None = None
    attempted: list[str] = []
    failures: list[tuple[str, str]] = []  # (provider_name, error_summary)

    for prov_name in chain:
        try:
            cls = _PROVIDER_REGISTRY[prov_name]
            provider = cls()
        except Exception as e:
            # e.g. EODHDProvider raises if EODHD_API_KEY is missing.
            # That's not a fatal error — just skip and try the next one.
            msg = str(e)[:120]
            print(f"  [finance_data] cannot instantiate {prov_name}: {msg}", file=sys.stderr)
            failures.append((prov_name, f"init: {msg}"))
            continue

        attempted.append(prov_name)
        print(f"  [finance_data] trying {prov_name} for {ticker}...", file=sys.stderr)
        try:
            result = provider.fetch(
                ticker, min_quarters=min_quarters,
                override_suspect_recent=override_suspect_recent,
            )
        except EarningsFetchError as e:
            msg = str(e)[:200]
            print(f"  [finance_data] {prov_name} failed: {msg}", file=sys.stderr)
            failures.append((prov_name, msg))
            last_err = e
            continue
        except Exception as e:
            # Unexpected error (network, library bug, etc) — try next
            msg = f"{type(e).__name__}: {str(e)[:180]}"
            print(f"  [finance_data] {prov_name} unexpected error: {msg}", file=sys.stderr)
            failures.append((prov_name, msg))
            last_err = e
            continue

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

        # Annotate the fallback chain in warnings so the UI / logs can show it
        if len(attempted) > 1:
            result.warnings.append(
                f"PROVIDER_FALLBACK: tried {' → '.join(attempted)}; "
                f"served by {prov_name}. "
                f"Failures: {'; '.join(f'{n}: {m[:80]}' for n, m in failures)}"
            )
        elif cfg.get("provider"):
            result.warnings.append(
                f"PROVIDER_OVERRIDE: forced through {prov_name} "
                f"(reason: {cfg.get('reason', 'see config')[:120]})"
            )

        print(f"  [finance_data] {ticker} served by {prov_name} (chain: {chain})", file=sys.stderr)
        return result

    # Exhausted the chain
    raise EarningsFetchError(
        f"All providers failed for {ticker}. Tried: {attempted or chain}. "
        f"Failures: {'; '.join(f'{n}: {m[:120]}' for n, m in failures)}. "
        f"Last error: {last_err}"
    )


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
