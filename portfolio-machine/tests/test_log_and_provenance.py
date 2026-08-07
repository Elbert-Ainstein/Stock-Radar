"""Laws 3, 5, 6: provenance on every number; real clocks; corrections go
forward, never overwrite."""
from datetime import date

from engine import log as logmod
from engine.fetch import (PriceRow, append_rows, cross_check, latest_settled,
                          load_rows, mark_settled)


def test_log_is_append_only_by_construction(machine):
    r1 = logmod.append("test_event", root=machine, detail="first")
    logmod.correct(r1["ts"], "wrong detail", root=machine, detail="second")
    rows = logmod.read(machine)
    assert len(rows) == 2
    assert rows[0]["detail"] == "first"           # original untouched
    assert rows[1]["event"] == "correction"
    assert rows[1]["corrects_ts"] == r1["ts"]     # forward reference
    # law 6 structurally: the module exposes no mutation API
    assert not any(hasattr(logmod, n) for n in ("update", "edit", "delete", "rewrite"))
    # law 5: stamps come from the system clock at write time
    assert rows[0]["ts"] <= rows[1]["ts"]


def test_price_rows_carry_provenance(machine):
    row = PriceRow(ticker="INTC", date="2026-07-27", close=92.52,
                   settled=True, source="test")
    append_rows("INTC", [row], machine)
    on_file = load_rows("INTC", machine)[0]
    assert on_file.source == "test"
    assert on_file.fetched_at            # non-empty timestamp
    assert on_file.settled is True


def test_correction_appends_never_overwrites(machine):
    append_rows("INTC", [PriceRow(ticker="INTC", date="2026-07-27", close=92.52,
                                  settled=True, source="a")], machine)
    # The $107.76-ghost class: a revised settled number for the same date.
    append_rows("INTC", [PriceRow(ticker="INTC", date="2026-07-27", close=92.60,
                                  settled=True, source="b")], machine)
    rows = load_rows("INTC", machine)
    assert len(rows) == 2                       # both on file — no overwrite
    assert "correction" in rows[1].note
    assert latest_settled("INTC", machine).close == 92.60  # forward wins


def test_identical_backfill_is_idempotent(machine):
    r = PriceRow(ticker="MU", date="2026-07-27", close=900.20, settled=True, source="a")
    assert append_rows("MU", [r], machine) == 1
    assert append_rows("MU", [r], machine) == 0  # re-run adds nothing


def test_cross_check_flags_never_averages():
    a = [PriceRow(ticker="X", date="2026-07-27", close=100.00, settled=True, source="src1")]
    b = [PriceRow(ticker="X", date="2026-07-27", close=107.76, settled=True, source="src2")]
    out = cross_check(a, b)
    assert out[0].conflict is True
    assert out[0].close == 100.00               # primary preserved, NOT averaged
    assert "107.76" in out[0].note              # the ghost is named in evidence
    # within tolerance -> no flag, cross-check noted
    ok = cross_check(a, [PriceRow(ticker="X", date="2026-07-27", close=100.2,
                                  settled=True, source="src2")])
    assert ok[0].conflict is False and "xchk" in ok[0].note


def test_same_day_row_cannot_be_settled():
    """Law 2 at the data layer: today's bar is demoted to snapshot no matter
    what the fetcher claims."""
    today = date(2026, 7, 28)
    rows = [PriceRow(ticker="X", date="2026-07-28", close=1.0, settled=True, source="s"),
            PriceRow(ticker="X", date="2026-07-27", close=1.0, settled=True, source="s")]
    marked = mark_settled(rows, today)
    assert marked[0].settled is False
    assert marked[1].settled is True
