"""D2 — EDGAR cross-check guardrail tests (pure logic; no network).

Run: pytest scripts/test_finance_data_edgar.py -v
"""

from datetime import datetime, timezone

import finance_data as fd


def _p(rev, year, month, label=None, with_date=True):
    """Provider quarter. with_date=False mimics providers that omit `_date`
    (only a fiscal-quarter label is available, e.g. SanDisk via eodhd)."""
    p = {"Total Revenue": rev, "period": label or f"{year}-Q{(month - 1) // 3 + 1}"}
    if with_date:
        p["_date"] = datetime(year, month, 1, tzinfo=timezone.utc)
    return p


def _eq(year, month, day, val):
    """One EDGAR (period_end, revenue) entry."""
    return (datetime(year, month, day), val)


def test_period_end_date():
    # prefers _date, falls back to label, returns a tz-naive datetime
    d = fd._period_end_date(_p(1e9, 2026, 4))
    assert (d.year, d.month) == (2026, 4) and d.tzinfo is None
    d2 = fd._period_end_date({"period": "1Q26"})  # label only
    assert d2 is not None and d2.year == 2026
    assert fd._period_end_date({"period": "garbage"}) is None


def test_edgar_crosscheck_match_passes():
    periods = [_p(8.7e9, 2026, 1), _p(9.0e9, 2026, 4)]
    edgar = [_eq(2026, 1, 1, 8.70e9), _eq(2026, 4, 1, 9.05e9)]  # within tolerance
    w, s = fd._edgar_crosscheck(periods, edgar)
    assert s == set()


def test_edgar_crosscheck_hard_mismatch_rejects():
    # provider 23.86B vs date-matched SEC 8.7B -> ~174% off -> hard reject
    periods = [_p(23.86e9, 2026, 1)]
    edgar = [_eq(2026, 1, 1, 8.7e9)]
    w, s = fd._edgar_crosscheck(periods, edgar)
    assert s == {0}
    assert any("EDGAR MISMATCH (hard)" in x for x in w)


def test_edgar_crosscheck_soft_variance_is_informational():
    periods = [_p(1.0e9, 2026, 1)]
    edgar = [_eq(2026, 1, 1, 1.2e9)]  # 16.7% off -> soft, not suspect
    w, s = fd._edgar_crosscheck(periods, edgar)
    assert s == set()
    assert any("EDGAR variance" in x for x in w)


def test_asts_style_ramp_passes_when_edgar_confirms():
    # near-zero -> 50x ramp; provider and EDGAR AGREE (date-aligned) -> NOT rejected
    periods = [_p(1e6, 2025, 10), _p(50e6, 2026, 1)]
    edgar = [_eq(2025, 10, 1, 1e6), _eq(2026, 1, 1, 50e6)]
    w, s = fd._edgar_crosscheck(periods, edgar)
    assert s == set()


def test_no_edgar_match_in_window_is_skipped_not_rejected():
    # provider quarter with NO SEC end within tolerance -> skipped, not rejected
    periods = [_p(5e9, 2026, 1)]
    edgar = [_eq(2024, 1, 1, 5e9)]  # ~2 years away
    w, s = fd._edgar_crosscheck(periods, edgar)
    assert s == set()


def test_fiscal_calendar_no_false_reject_sndk():
    # SNDK regression: provider fiscal labels (no _date) sit ~32d BEFORE the SEC
    # end-dates and the values match exactly -> must NOT false-reject. The old
    # calendar-quarter bucketing compared the wrong quarters and hard-failed here.
    periods = [_p(2.308e9, 2025, 9, label="3Q25", with_date=False),
               _p(3.025e9, 2025, 12, label="4Q25", with_date=False),
               _p(5.95e9, 2026, 3, label="1Q26", with_date=False)]
    edgar = [_eq(2025, 10, 3, 2.31e9), _eq(2026, 1, 2, 3.02e9), _eq(2026, 4, 3, 5.95e9)]
    w, s = fd._edgar_crosscheck(periods, edgar)
    assert s == set(), f"false reject on clean fiscal-calendar data: {w}"


def test_validate_falls_back_to_advisory_without_edgar(monkeypatch):
    monkeypatch.setattr(fd, "_edgar_revenue_by_quarter", lambda t: None)
    periods = [_p(1e6, 2025, 4), _p(50e6, 2026, 1)]  # huge ramp
    w, s = fd._validate_quarterly_revenue(periods, ticker="ASTS")
    assert s == set()  # no EDGAR -> trajectory advisory only -> NOT rejected
    assert any("ADVISORY ONLY" in x for x in w)


def test_validate_hard_rejects_on_edgar_mismatch(monkeypatch):
    monkeypatch.setattr(fd, "_edgar_revenue_by_quarter", lambda t: [_eq(2026, 1, 1, 8.7e9)])
    periods = [_p(23.86e9, 2026, 1)]
    w, s = fd._validate_quarterly_revenue(periods, ticker="MU")
    assert s == {0}
