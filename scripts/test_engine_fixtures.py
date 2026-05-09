#!/usr/bin/env python3
"""
test_engine_fixtures.py - End-to-end regression fixture for target_engine.

Locks in low / base / high / valuation_method / TTM data canary for a
hand-picked set of ticker + as_of combinations covering each archetype.

The fixture's job: catch silent changes in engine output. If you tighten
or change a heuristic, expect a fixture failure and update the JSON
intentionally via scripts/capture_engine_fixtures.py.

Why it exists:
    The MRVL incident (auto-promoted to "cyclical", emitted $0/$0/$0)
    slipped through unit tests because no test exercised the full
    build_target path on a real ticker. Unit tests cover individual
    helpers; this fixture covers what the system actually outputs.

Run:
    pytest scripts/test_engine_fixtures.py -v
    pytest scripts/test_engine_fixtures.py -m fixtures
    pytest scripts/test_engine_fixtures.py -k LITE_cyclical_trough -v
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from finance_data import fetch_financials  # noqa: E402
from target_engine import build_target  # noqa: E402


FIXTURE_PATH = HERE / "test_engine_fixtures.json"


def _load_fixtures():
    if not FIXTURE_PATH.exists():
        pytest.skip("fixture file missing: " + str(FIXTURE_PATH))
    data = json.loads(FIXTURE_PATH.read_text())
    return data["_meta"], data["fixtures"]


def _within_tolerance(actual: float, expected: float, tol_pct: float) -> bool:
    """Within +/- tol_pct of expected.

    For expected==0: only non-negative actuals < $1 pass. This rejects
    small negative outputs (sign-error symptoms) that a permissive
    abs-value floor would let through.
    """
    if expected == 0:
        return 0 <= actual < 1.0
    return abs(actual - expected) / abs(expected) * 100.0 <= tol_pct


def _ids(fixtures):
    return [f["name"] for f in fixtures]


META, FIXTURES = _load_fixtures()
TOL_PCT_DEFAULT = float(META.get("tolerance_pct", 50.0))
SKIP_FLOOR = int(META.get("skip_floor", 2))

# Session-level skip counter -- fail the suite if too many entries can't
# run (prevents silent CI green when network/provider is down).
_skipped_entries: list[str] = []


@pytest.mark.fixtures
@pytest.mark.parametrize("entry", FIXTURES, ids=_ids(FIXTURES))
def test_fixture(entry):
    """Validate one fixture entry against current engine state.

    Asserts:
      1. method == captured method (always)
      2. method == expected_method when set (e.g. MRVL must be ev_ebitda)
      3. low <= base <= high invariant
      4. low/base/high within +/- tolerance_pct of captured (per-entry)
      5. TTM revenue / TTM EBITDA within +/- 5% of pinned values
         (data-layer canary -- catches provider regressions)
    """
    name = entry["name"]
    ticker = entry["ticker"]
    as_of_str = entry.get("as_of")
    archetype = entry.get("archetype")

    def _skip(reason):
        _skipped_entries.append(name)
        pytest.skip(name + ": " + reason)

    spot = None
    as_of_dt = None
    if as_of_str:
        as_of_dt = datetime.fromisoformat(as_of_str).replace(tzinfo=timezone.utc)
        try:
            from backtest_targets import close_at_or_before, load_price_history
            prices = load_price_history(
                ticker,
                as_of_dt - timedelta(days=30),
                as_of_dt + timedelta(days=10),
            )
            tup = close_at_or_before(prices, as_of_dt)
        except Exception as e:
            _skip("price history unavailable: " + str(e))
        if tup is None:
            _skip("no spot price within 7 days of " + as_of_str)
        spot = tup[1]

    try:
        fin = fetch_financials(ticker, as_of=as_of_dt)
    except Exception as e:
        _skip("fetch_financials failed: " + str(e))

    if as_of_dt is not None and spot is not None:
        fin.price = spot
        if fin.shares_diluted:
            fin.market_cap = spot * fin.shares_diluted

    result = build_target(
        fin,
        drivers=None,
        forward=None,
        load_forward=False,
        horizon_months=12,
        archetype=archetype,
    )

    # 1) Method matches captured
    captured_method = entry["method"]
    assert result.valuation_method == captured_method, (
        name + ": routing changed -- captured=" + repr(captured_method)
        + ", current=" + repr(result.valuation_method)
        + ". If intentional, regenerate the fixture."
    )

    # 2) Method matches expected (when set)
    expected_method = entry.get("expected_method")
    if expected_method:
        assert result.valuation_method == expected_method, (
            name + ": required method " + repr(expected_method)
            + ", got " + repr(result.valuation_method)
        )

    # 3) Invariant: low <= base <= high
    eps = 0.01
    assert result.low <= result.base + eps, (
        name + ": invariant violated -- low=" + format(result.low, ".4f")
        + " > base=" + format(result.base, ".4f")
    )
    assert result.base <= result.high + eps, (
        name + ": invariant violated -- base=" + format(result.base, ".4f")
        + " > high=" + format(result.high, ".4f")
    )

    # 4) Tolerance bands (per-entry override allowed)
    tol_pct = float(entry.get("tolerance_pct", TOL_PCT_DEFAULT))
    for leg in ("low", "base", "high"):
        captured = float(entry[leg])
        actual = float(getattr(result, leg))
        assert _within_tolerance(actual, captured, tol_pct), (
            name + ": " + leg + " drifted beyond +/-" + format(tol_pct, ".1f")
            + "% -- captured=" + format(captured, ".2f")
            + ", current=" + format(actual, ".2f")
        )

    # 5) Data-layer canary: pinned TTM values within +/- 5%
    pinned = entry.get("pinned_data") or {}
    if pinned.get("ttm_revenue") is not None:
        actual_rev = fin.ttm_revenue() or 0.0
        captured_rev = float(pinned["ttm_revenue"])
        if captured_rev:
            drift = abs(actual_rev - captured_rev) / abs(captured_rev) * 100.0
            assert drift <= 5.0, (
                name + ": TTM revenue drifted " + format(drift, ".1f")
                + "% -- captured=" + format(captured_rev, ".0f")
                + ", current=" + format(actual_rev, ".0f")
                + ". Likely a data-provider regression."
            )
    if pinned.get("ttm_ebitda") is not None:
        actual_ebitda = fin.ttm_ebitda() or 0.0
        captured_ebitda = float(pinned["ttm_ebitda"])
        if captured_ebitda:
            drift = abs(actual_ebitda - captured_ebitda) / abs(captured_ebitda) * 100.0
            assert drift <= 5.0, (
                name + ": TTM EBITDA drifted " + format(drift, ".1f")
                + "% -- captured=" + format(captured_ebitda, ".0f")
                + ", current=" + format(actual_ebitda, ".0f")
                + ". Likely a data-provider regression."
            )


def test_skip_floor():
    """Fail the suite if more than SKIP_FLOOR entries skipped.

    Prevents silent CI green when network/provider is intermittently
    down. Runs after `test_fixture` parametrized cases (alphabetic).
    """
    if len(_skipped_entries) > SKIP_FLOOR:
        pytest.fail(
            str(len(_skipped_entries)) + " fixture entries skipped (floor="
            + str(SKIP_FLOOR) + "): " + str(_skipped_entries)
            + ". Network or provider likely degraded."
        )
