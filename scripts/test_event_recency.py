"""Regression tests for event_reasoner recency decay (audit 2026-07-02 §4.5).

The old _days_since sliced every date to garbage ('2026-01-15' -> '2026-'),
so strptime failed for ALL formats and every dated event returned 0.0 days —
permanent full weight, no decay ever. A 5-month-old catalyst contributed its
full magnitude to the authoritative final_target blend indefinitely.

Run: pytest scripts/test_event_recency.py -v
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from event_reasoner import _days_since, _recency_weight


def _iso_days_ago(days: int, with_time: bool = False, zulu: bool = False) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=days)
    if not with_time:
        return d.strftime("%Y-%m-%d")
    return d.strftime("%Y-%m-%dT%H:%M:%SZ" if zulu else "%Y-%m-%dT%H:%M:%S")


def test_plain_date_parses_to_real_age():
    assert 149.0 <= _days_since(_iso_days_ago(150)) <= 151.0


def test_iso_datetime_parses_to_real_age():
    assert 149.5 <= _days_since(_iso_days_ago(150, with_time=True)) <= 150.5


def test_iso_zulu_parses_to_real_age():
    assert 149.5 <= _days_since(_iso_days_ago(150, with_time=True, zulu=True)) <= 150.5


def test_old_event_actually_decays():
    """The observable failure: a 150-day-old event must NOT carry full weight.
    exp(-150/62) ~= 0.089 — the old code gave it exactly 1.0 forever."""
    w = _recency_weight(_days_since(_iso_days_ago(150)))
    assert w < 0.15
    fresh = _recency_weight(_days_since(_iso_days_ago(0)))
    assert fresh > 0.95


def test_undated_defaults_to_moderate_age():
    assert _days_since(None) == 30.0
    assert _days_since("") == 30.0


def test_unparseable_treated_as_unknown_not_brand_new():
    # The old code returned 0.0 (maximum freshness) for garbage dates.
    assert _days_since("next quarter") == 30.0
    assert _days_since("06/15/2026") == 30.0


def test_api_cyclical_slider_routing_matches_engine_output():
    """target_api must route cyclical sliders on the string build_target
    actually emits ('cyclical'), not the never-emitted 'cyclical_normalized'."""
    import ast
    src = (Path(__file__).resolve().parent / "target_api.py").read_text()
    tree = ast.parse(src)
    # Find the is_cyclical assignment and confirm it matches "cyclical".
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "is_cyclical" for t in node.targets
        ):
            literals = {n.value for n in ast.walk(node.value) if isinstance(n, ast.Constant)}
            assert "cyclical" in literals, (
                "target_api is_cyclical check must accept the engine's "
                "valuation_method='cyclical'"
            )
            found = True
    assert found, "is_cyclical assignment not found in target_api.py"
