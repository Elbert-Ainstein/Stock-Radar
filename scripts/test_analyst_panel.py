"""Analyst Panel — pure logic tests (parse / propagation / render / persistence).

No network/LLM. Run: pytest scripts/test_analyst_panel.py -v
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import analyst_panel as ap


def _clock(node, pos, dur, conf="HIGH", read="x"):
    return ap.NodeClock(node=node, position=pos, duration_quarters=dur, confidence=conf, read=read)


# ── parse_node_clock ────────────────────────────────────────────────────────────

def test_parse_valid():
    c = ap.parse_node_clock("memory", {"position": "Peaking", "duration_quarters": 2,
                                       "confidence": "high", "read": "HBM tight"})
    assert c.position == "peaking" and c.confidence == "HIGH" and c.duration_quarters == 2.0
    # duration may be absent
    c2 = ap.parse_node_clock("optical", {"position": "accelerating", "confidence": "MEDIUM"})
    assert c2.duration_quarters is None


def test_parse_rejects_bad_inputs():
    with pytest.raises(ValueError):
        ap.parse_node_clock("m", {"position": "exploding", "confidence": "HIGH"})   # bad position
    with pytest.raises(ValueError):
        ap.parse_node_clock("m", {"position": "peaking", "confidence": "SURE"})     # bad confidence
    with pytest.raises(ValueError):
        ap.parse_node_clock("m", {"position": "peaking", "confidence": "HIGH", "duration_quarters": -1})
    with pytest.raises(ValueError):
        ap.parse_node_clock("m", {"position": "peaking", "confidence": "HIGH", "duration_quarters": "soon"})
    with pytest.raises(ValueError):
        ap.parse_node_clock("m", ["not", "a", "dict"])


def test_parse_rejects_bool_and_nonfinite_duration():
    # bool is an int subclass — must NOT slip through as 1.0/0.0 (red-team finding)
    with pytest.raises(ValueError):
        ap.parse_node_clock("m", {"position": "peaking", "confidence": "HIGH", "duration_quarters": True})
    with pytest.raises(ValueError):
        ap.parse_node_clock("m", {"position": "peaking", "confidence": "HIGH", "duration_quarters": float("inf")})


def test_parse_sanitizes_braces_in_read():
    c = ap.parse_node_clock("m", {"position": "peaking", "confidence": "HIGH",
                                  "read": "HBM3E tight {HBM4} slipping"})
    assert "{" not in c.read and "}" not in c.read
    assert "(HBM4)" in c.read


# ── derive_propagation ──────────────────────────────────────────────────────────

def test_propagation_tailwind_headwind_gap():
    edges = [["memory", "optical"], ["optical", "custom_silicon"]]
    clocks = {
        "memory": _clock("memory", "peaking", 2),
        "optical": _clock("optical", "accelerating", 6),
        "custom_silicon": _clock("custom_silicon", "decelerating", 5),
    }
    flags = ap.derive_propagation(clocks, edges)
    types = [f["type"] for f in flags]
    # memory peaking -> tailwind into optical; memory(2) vs optical(6) -> gap
    assert "tailwind" in types and "gap" in types
    # optical accelerating -> tailwind into custom_silicon
    assert any(f["from"] == "optical" and f["type"] == "tailwind" for f in flags)


def test_propagation_decelerating_is_headwind():
    flags = ap.derive_propagation(
        {"a": _clock("a", "decelerating", 1), "b": _clock("b", "trough", 1)},
        [["a", "b"]])
    assert flags[0]["type"] == "headwind" and flags[0]["from"] == "a"


def test_propagation_skips_missing_nodes():
    flags = ap.derive_propagation({"a": _clock("a", "peaking", 2)}, [["a", "b"]])
    assert flags == []   # b absent -> edge skipped


def test_propagation_skips_self_loops_and_dedupes():
    clocks = {"a": _clock("a", "peaking", 2), "b": _clock("b", "accelerating", 5)}
    # self-loop a->a produces nothing
    assert ap.derive_propagation(clocks, [["a", "a"]]) == []
    # duplicate edge a->b yields exactly one tailwind (deduped)
    flags = ap.derive_propagation(clocks, [["a", "b"], ["a", "b"]])
    assert len([f for f in flags if f["type"] == "tailwind"]) == 1


def test_full_chain_config_is_consistent():
    # every edge endpoint must be a declared node (catches typos when scaling)
    nodes = set(ap.DEFAULT_CHAIN["nodes"])
    for a, b in ap.DEFAULT_CHAIN["edges"]:
        assert a in nodes and b in nodes, f"edge {a}->{b} references an unknown node"
    assert len(ap.DEFAULT_CHAIN["nodes"]) == 7


# ── render ──────────────────────────────────────────────────────────────────────

def test_render_includes_nodes_and_flags():
    out = ap.render_chain_context(
        ap.DEFAULT_CHAIN,
        {"memory": _clock("memory", "peaking", 2, read="HBM tight"),
         "optical": _clock("optical", "accelerating", 6, read="EML sold out")},
        [{"type": "tailwind", "from": "memory", "to": "optical", "note": "memory → optical demand"}],
    )
    assert out.startswith("[CHAIN:")
    assert "Memory (HBM/DRAM): peaking" in out and "HBM tight" in out
    assert "Cross-node:" in out and "memory → optical demand" in out


# ── persistence + load + staleness (anchoring guard) ────────────────────────────

def test_save_load_roundtrip_and_history(tmp_path):
    p = tmp_path / "panel.json"
    clocks = {"memory": _clock("memory", "peaking", 2), "optical": _clock("optical", "accelerating", 6)}
    flags = ap.derive_propagation(clocks, [["memory", "optical"]])
    ap.save_panel_state(ap.DEFAULT_CHAIN, clocks, flags, path=p)
    block = ap.load_chain_context(path=p)
    assert block and "[CHAIN:" in block
    # a second save preserves the prior as READ-ONLY history (anchoring guard)
    import json
    for _ in range(15):  # many saves -> history must stay bounded (<= 10)
        ap.save_panel_state(ap.DEFAULT_CHAIN, clocks, flags, path=p)
    data = json.loads(p.read_text())
    assert "clocks" in data["history"][0]
    assert len(data["history"]) <= 10   # cap invariant


def test_load_missing_and_stale(tmp_path):
    assert ap.load_chain_context(path=tmp_path / "nope.json") is None
    # write a stale state by hand
    p = tmp_path / "panel.json"
    clocks = {"memory": _clock("memory", "peaking", 2)}
    ap.save_panel_state(ap.DEFAULT_CHAIN, clocks, [], path=p)
    future = datetime.now(timezone.utc) + timedelta(days=ap.CHAIN_STALE_DAYS + 3)
    stale = ap.load_chain_context(path=p, now=future)
    assert stale is not None and "stale" in stale
    # boundary: just over the window (days truncation must NOT mask it)
    just_over = datetime.now(timezone.utc) + timedelta(days=ap.CHAIN_STALE_DAYS, seconds=5)
    assert "stale" in ap.load_chain_context(path=p, now=just_over)
    # well within the window -> fresh (no stale note)
    fresh = ap.load_chain_context(path=p, now=datetime.now(timezone.utc) + timedelta(hours=1))
    assert fresh is not None and "stale" not in fresh
