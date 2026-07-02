"""Unit tests for prediction_logger.py — schema-drift strip-retry budget, no network/DB.

The 2026-07-02 fix: the retry budget is one attempt per strippable column plus
one. The old fixed range(5) was exactly exhausted by the 5 optional
checkpoint-seal columns while their migration was unapplied, silently losing
the ENTIRE prediction row.

Run: pytest scripts/test_prediction_logger.py -v
"""

import types

import prediction_logger as pl

SEAL_COLS = [
    "system_version",
    "reasoning_fingerprint",
    "cohort_key",
    "version_cohort_break",
    "socratic_analysis_id",
]


class _FakeTable:
    """PostgREST sim: rejects one missing column per call until none remain."""

    def __init__(self, missing_cols):
        self.missing = missing_cols
        self.rows = None

    def insert(self, rows):
        self.rows = rows
        return self

    def upsert(self, rows, on_conflict=None):
        self.rows = rows
        return self

    def execute(self):
        for col in self.missing:
            if any(col in r for r in self.rows):
                raise Exception(
                    f"Could not find the '{col}' column of 'prediction_log' in the schema cache"
                )
        resp = types.SimpleNamespace()
        resp.data = [dict(r) for r in self.rows]
        return resp


class _FakeClient:
    def __init__(self, missing_cols):
        self._missing = missing_cols
        self.table_calls = 0

    def table(self, name):
        self.table_calls += 1
        return _FakeTable(self._missing)


def _seal_row():
    return pl._coerce_row(
        {
            "ticker": "LITE",
            "run_id": "soc-42",
            "current_price": 786.9,
            "target_low": 512.0,
            "target_high": 1506.0,
        }
    )


def test_row_survives_all_five_seal_columns_missing(monkeypatch):
    """Pre-migration schema (5 seal columns absent): the row must persist minus
    the stripped columns — the old code lost the entire row here."""
    client = _FakeClient(list(SEAL_COLS))
    monkeypatch.setattr(pl, "get_client", lambda: client)
    result = pl._upsert_with_retry("prediction_log", [_seal_row()], on_conflict="ticker,run_id")
    assert len(result) == 1
    written = result[0]
    assert written["ticker"] == "LITE"
    assert written["current_price"] == 786.9
    for col in SEAL_COLS:
        assert col not in written


def test_no_drift_writes_everything(monkeypatch):
    client = _FakeClient([])
    monkeypatch.setattr(pl, "get_client", lambda: client)
    result = pl._upsert_with_retry("prediction_log", [_seal_row()], on_conflict="ticker,run_id")
    assert len(result) == 1
    assert result[0]["cohort_key"] is None  # seal cols present, engine path leaves them NULL


def test_non_schema_error_gives_up(monkeypatch):
    class _Boom(_FakeTable):
        def execute(self):
            raise Exception("connection refused")

    class _BoomClient:
        def table(self, name):
            return _Boom([])

    monkeypatch.setattr(pl, "get_client", lambda: _BoomClient())
    assert pl._upsert_with_retry("prediction_log", [_seal_row()]) == []


def test_budget_scales_with_row_width(monkeypatch):
    """Strip MORE than 5 columns (worst-case drift) — the dynamic budget covers it."""
    missing = SEAL_COLS + ["scenario_probabilities", "context_inputs", "sigmoid_params"]
    client = _FakeClient(list(missing))
    monkeypatch.setattr(pl, "get_client", lambda: client)
    result = pl._upsert_with_retry("prediction_log", [_seal_row()], on_conflict="ticker,run_id")
    assert len(result) == 1
    for col in missing:
        assert col not in result[0]
