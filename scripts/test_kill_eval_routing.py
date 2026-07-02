"""Tests for archetype-routed kill evaluation + fail-closed behavior
(2026-07-02: decisions 4.1 + gap (b) from the consolidation sprint report).

Acceptance (sprint 4.1): SNDK kill evaluation runs under CYCLICAL guidance,
not GARP. Gap (b): evaluation failure returns status 'unknown', never 'safe'.

Run: pytest scripts/test_kill_eval_routing.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

import kill_condition_eval as k
from target_engine import _load_archetype_override

WATCHLIST_TAGS = {
    "LITE": "transformational",
    "SNDK": "cyclical",
    "RKLB": "transformational",
    "ACHR": "transformational",
    "PLTR": "compounder",
    "CELH": "garp",
}


def test_all_watchlist_archetypes_resolve():
    """The audit's 'archetype routing inert for 5 of 6 names' — now all 6 tag."""
    for ticker, expected in WATCHLIST_TAGS.items():
        assert _load_archetype_override(ticker) == expected, ticker


class _FakeResponse:
    def __init__(self, status="safe"):
        self._status = status

    def raise_for_status(self):
        pass

    def json(self):
        return {"content": [{"text": (
            '{"status": "%s", "confidence": 0.9, "reasoning": "ok", "evidence": []}'
            % self._status)}]}


def _capture_post(captured, response=None, raise_exc=None):
    def fake_post(url, headers=None, json=None, timeout=None):
        captured["prompt"] = json["messages"][0]["content"]
        if raise_exc:
            raise raise_exc
        return response or _FakeResponse()
    return fake_post


def test_sndk_kill_eval_uses_cyclical_guidance(monkeypatch):
    captured = {}
    monkeypatch.setattr(k, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(k.requests, "post", _capture_post(captured))
    out = k.evaluate_kill_condition("SNDK", "NAND ASPs decline 2 consecutive quarters")
    assert "CYCLICAL" in captured["prompt"]
    assert k.ARCHETYPE_KILL_GUIDANCE["cyclical"] in captured["prompt"]
    assert out["status"] == "safe"


def test_untagged_ticker_still_defaults_to_garp(monkeypatch):
    captured = {}
    monkeypatch.setattr(k, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(k.requests, "post", _capture_post(captured))
    k.evaluate_kill_condition("ZZZZ", "some condition")
    assert "GARP" in captured["prompt"]


def test_explicit_archetype_arg_wins_over_config(monkeypatch):
    captured = {}
    monkeypatch.setattr(k, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(k.requests, "post", _capture_post(captured))
    k.evaluate_kill_condition("SNDK", "cond", archetype="special_situation")
    assert "SPECIAL_SITUATION" in captured["prompt"]


# ── fail-closed (gap b): never report 'safe' when the evaluator didn't run ──

def test_missing_api_key_is_unknown(monkeypatch):
    monkeypatch.setattr(k, "ANTHROPIC_API_KEY", "")
    out = k.evaluate_kill_condition("SNDK", "cond")
    assert out["status"] == "unknown"
    assert out["confidence"] == 0.0


def test_api_exception_is_unknown(monkeypatch):
    captured = {}
    monkeypatch.setattr(k, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        k.requests, "post", _capture_post(captured, raise_exc=RuntimeError("timeout"))
    )
    out = k.evaluate_kill_condition("SNDK", "cond")
    assert out["status"] == "unknown"
    assert "Evaluation failed" in out["reasoning"]


def test_garbage_model_status_is_unknown(monkeypatch):
    captured = {}
    monkeypatch.setattr(k, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        k.requests, "post", _capture_post(captured, response=_FakeResponse("all_good"))
    )
    out = k.evaluate_kill_condition("SNDK", "cond")
    assert out["status"] == "unknown"


def test_no_kill_condition_defined_stays_safe():
    # Genuinely nothing to evaluate — not a failure mode.
    out = k.evaluate_kill_condition("SNDK", "")
    assert out["status"] == "safe"
