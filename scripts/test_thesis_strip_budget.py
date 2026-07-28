"""write_to_supabase strip-and-retry budget — the prediction_logger lesson.

Sprint 1.3 (2026-07-02) fixed prediction_logger's fixed 5-attempt budget being
exactly exhausted by 5 missing columns, losing whole rows. The theses writer
had the same fixed budget; the L4 run_parameters column made SIX columns
potentially missing on a fully pre-migration DB (strategic_conviction,
risk_adj_ev_ratio, thesis_horizon_years, kill_gate_override, model_d_bracket,
run_parameters) — which would have exhausted it and lost the entire verdict
row (2026-07-08 review, major). The budget is now dynamic: one attempt per
column + 1. These tests simulate PostgREST unknown-column errors.
"""
from __future__ import annotations

import run_thesis
import supabase_helper


class _FakeResult:
    data = [{"id": 42}]


class _FakeTable:
    def __init__(self, store: list, missing: set):
        self._store = store
        self._missing = missing
        self._row = None

    def insert(self, row):
        self._row = row
        return self

    def execute(self):
        for col in self._row:
            if col in self._missing:
                # PostgREST reports ONE unknown column per failed insert.
                raise Exception(
                    f"Could not find the '{col}' column of 'theses' in the schema cache")
        self._store.append(dict(self._row))
        return _FakeResult()


class _FakeClient:
    def __init__(self, store: list, missing: set):
        self._store = store
        self._missing = missing

    def table(self, name):
        assert name == "theses"
        return _FakeTable(self._store, self._missing)


PENDING_6 = {"strategic_conviction", "risk_adj_ev_ratio", "thesis_horizon_years",
             "kill_gate_override", "model_d_bracket", "run_parameters"}


def _row_with(missing_cols: set) -> dict:
    row = {"ticker": "TEST", "run_at": "2026-07-08T00:00:00+00:00",
           "conviction": "BROKEN", "thesis_target": 100, "spot_at_run": 80.0}
    for c in missing_cols:
        row[c] = {"x": 1} if c.endswith(("_override", "_bracket", "_parameters")) else 1
    return row


def test_six_missing_columns_row_survives(monkeypatch):
    """The exact fully-pre-migration state: all six pending columns missing.
    The old range(5) budget lost the whole row here."""
    store: list = []
    monkeypatch.setattr(supabase_helper, "get_client",
                        lambda: _FakeClient(store, PENDING_6))
    thesis_id = run_thesis.write_to_supabase(_row_with(PENDING_6))
    assert thesis_id == 42
    assert len(store) == 1
    persisted = store[0]
    assert persisted["ticker"] == "TEST" and persisted["thesis_target"] == 100
    assert not (PENDING_6 & set(persisted))  # stripped, not silently kept


def test_headroom_beyond_known_pending(monkeypatch):
    """Future columns must not re-create the off-by-one: strip 8 and survive."""
    missing = PENDING_6 | {"future_col_a", "future_col_b"}
    store: list = []
    monkeypatch.setattr(supabase_helper, "get_client",
                        lambda: _FakeClient(store, missing))
    thesis_id = run_thesis.write_to_supabase(_row_with(missing))
    assert thesis_id == 42 and len(store) == 1


def test_no_missing_columns_single_attempt(monkeypatch):
    store: list = []
    monkeypatch.setattr(supabase_helper, "get_client",
                        lambda: _FakeClient(store, set()))
    assert run_thesis.write_to_supabase(_row_with(set())) == 42
    assert store[0]["conviction"] == "BROKEN"


def test_non_column_error_still_raises(monkeypatch):
    """The dynamic budget must not swallow real failures."""
    class _Boom(_FakeTable):
        def execute(self):
            raise Exception("connection refused")

    class _BoomClient(_FakeClient):
        def table(self, name):
            return _Boom(self._store, self._missing)

    monkeypatch.setattr(supabase_helper, "get_client",
                        lambda: _BoomClient([], set()))
    try:
        run_thesis.write_to_supabase(_row_with(set()))
        raised = False
    except Exception as e:
        raised = "connection refused" in str(e)
    assert raised
