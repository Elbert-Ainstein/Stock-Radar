"""VIX tracker tests — pure classifier/trend/context-line, no network.

Run: pytest scripts/test_vix.py -v
"""

import vix


def test_classify_bands():
    assert vix.classify_vix_regime(12)["regime"] == "calm"
    assert vix.classify_vix_regime(15)["regime"] == "normal"     # band is inclusive-low
    assert vix.classify_vix_regime(19.9)["regime"] == "normal"
    assert vix.classify_vix_regime(21.51)["regime"] == "elevated"  # today's live level
    assert vix.classify_vix_regime(30)["regime"] == "stress"
    assert vix.classify_vix_regime(55)["regime"] == "crisis"


def test_classify_invalid():
    assert vix.classify_vix_regime(None)["regime"] == "unknown"
    assert vix.classify_vix_regime(-1)["regime"] == "unknown"


def test_trend_label():
    assert vix.trend_label(21.5, 15.4) == "spiking"   # +40% (today)
    assert vix.trend_label(16.5, 15.6) == "rising"     # +6%
    assert vix.trend_label(15.5, 15.4) == "flat"       # +0.6%
    assert vix.trend_label(14.0, 15.6) == "falling"    # -10%
    assert vix.trend_label(11.0, 16.0) == "collapsing"  # -31%
    assert vix.trend_label(20, None) == "n/a"
    assert vix.trend_label(None, 15) == "n/a"


def test_context_line():
    v = {"level": 21.51, "regime": "elevated", "note": "rising stress; risk-off tilt",
         "trend": "spiking", "day_change_pct": 39.7}
    line = vix.vix_context_line(v)
    assert line.startswith("[VIX] 21.51 — elevated")
    assert "spiking" in line and "+39.7% vs prior close" in line


def test_context_line_unavailable():
    assert vix.vix_context_line(None) == "[VIX] unavailable"
    assert vix.vix_context_line({"level": None}) == "[VIX] unavailable"
