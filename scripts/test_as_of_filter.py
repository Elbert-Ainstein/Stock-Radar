"""Regression tests for the restored fetch_financials(as_of=...) point-in-time
view (audit 2026-07-02 §3.3 / sprint 2.6).

The kwarg was dropped in the provider-abstraction refactor (~2026-05-07) while
backtest_targets.py, capture_engine_fixtures.py, and test_engine_fixtures.py
kept passing it — all three died on TypeError, and the engine-fixture suite
silently skipped 100% of cases (misattributed to sandbox networking).

Run: pytest scripts/test_as_of_filter.py -v
"""
import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from finance_data import _filter_financials_as_of, _period_public_date, fetch_financials
from test_engine import _make_stub_fin


def _dated_fin():
    """Stub with real per-quarter end dates spanning 2025-06 → 2026-03."""
    fin = _make_stub_fin()
    dates = ["2025-06-28", "2025-09-27", "2025-12-27", "2026-03-28"]
    for lst in (fin.quarterly_income, fin.quarterly_cashflow):
        for p, d in zip(lst, dates):
            p["date"] = d
    fin.annual_income[0]["date"] = "2025-12-27"
    fin.annual_cashflow[0]["date"] = "2025-12-27"
    return fin


def test_signature_accepts_as_of():
    """The exact regression: callers pass as_of= — it must be a real kwarg."""
    params = inspect.signature(fetch_financials).parameters
    assert "as_of" in params
    assert "filing_lag_days" in params


def test_periods_after_as_of_are_dropped():
    fin = _dated_fin()
    # as_of 2026-02-15: Q ending 2026-03-28 is in the future; Q ending
    # 2025-12-27 + 45d lag = public 2026-02-10 → kept.
    as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
    fin, dropped = _filter_financials_as_of(fin, as_of, filing_lag_days=45)
    kept_dates = [p["date"] for p in fin.quarterly_income]
    assert kept_dates == ["2025-06-28", "2025-09-27", "2025-12-27"]
    assert dropped >= 2  # one income + one cashflow quarter
    assert any("AS_OF_FILTER" in w for w in fin.warnings)


def test_filing_lag_enforced():
    """A quarter that ENDED before as_of but was not yet FILED is dropped."""
    fin = _dated_fin()
    # as_of 2026-01-10: Q ending 2025-12-27 ended 14 days ago — not filed yet.
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    fin, _ = _filter_financials_as_of(fin, as_of, filing_lag_days=45)
    kept_dates = [p["date"] for p in fin.quarterly_income]
    assert kept_dates == ["2025-06-28", "2025-09-27"]


def test_nothing_dropped_when_all_public():
    fin = _dated_fin()
    as_of = datetime(2026, 6, 30, tzinfo=timezone.utc)
    fin, dropped = _filter_financials_as_of(fin, as_of, filing_lag_days=45)
    assert dropped == 0
    assert len(fin.quarterly_income) == 4


def test_undated_period_falls_back_to_label_parse():
    p = {"period": "3Q25"}
    d = _period_public_date(p)
    assert d is not None and d.year == 2025


def test_provider_date_preferred_over_label():
    # SNDK-shape: fiscal quarter labeled Q2 but truly ending Jan 2 — the true
    # 'date' must drive the filter, not the label's month approximation.
    p = {"period": "2Q26", "date": "2026-01-02"}
    d = _period_public_date(p)
    assert (d.year, d.month, d.day) == (2026, 1, 2)
