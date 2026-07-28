"""The built-in report mechanism: premarket + close briefs (out/*.html).

The load-bearing pin is law 2 through the close pass: an after-market run
sees a same-day snapshot ABOVE an armed wire and must render "would fire"
without opening a consult, changing wire state, or appending history."""
from engine import log as logmod
from engine.fetch import PriceRow, append_rows, latest_snapshot
from engine.market_calendar import exchange_today
from engine.rules import load_wire_state
from passes import close as closepass
from passes import premarket


def _settled(ticker, d, price):
    return PriceRow(ticker=ticker, date=d, close=price, settled=True, source="test")


def _snap(ticker, d, price):
    return PriceRow(ticker=ticker, date=d, close=price, settled=False,
                    source="test-snapshot")


def test_close_pass_is_provisional_never_acts(flip_machine):
    """Same-day snapshot at 95 vs the INTC>=92 wire: the close pass must say
    'would fire' and do nothing else (law 2 — the flip incidents). It must
    also never write a settled row."""
    from engine.fetch import load_rows
    today = exchange_today("INTC", flip_machine).isoformat()
    append_rows("INTC", [_snap("INTC", today, 95.00)], flip_machine)
    rc = closepass.run(offline=True, root=flip_machine)
    assert rc == 0
    assert not list((flip_machine / "consults").glob("OPEN_*")), \
        "close pass opened a consult — law 2 violation"
    assert load_wire_state(flip_machine) == {}, "close pass touched wire state"
    assert all(not r.settled for r in load_rows("INTC", flip_machine)), \
        "close pass wrote a settled row — law 2 violation"
    brief = flip_machine / "out" / "close.html"
    assert brief.exists()
    text = brief.read_text(encoding="utf-8")
    assert "PROVISIONAL" in text
    assert "intc-92-flip-example" in text and "WOULD FIRE" in text
    assert today in text, "snapshot session date must be rendered"
    events = [r["event"] for r in logmod.read(flip_machine)]
    assert "brief_rendered" in events and "wire_fired" not in events


def test_stale_snapshot_is_dated_and_marked(flip_machine):
    """An old snapshot must never render as today's tape: it carries its
    session date, a STALE marker, and a degradation warning (laws 3+5)."""
    append_rows("INTC", [_settled("INTC", "2026-07-23", 80.00)], flip_machine)
    append_rows("INTC", [_snap("INTC", "2026-07-24", 95.00)], flip_machine)
    rc = closepass.run(offline=True, root=flip_machine)
    assert rc == 0
    text = (flip_machine / "out" / "close.html").read_text(encoding="utf-8")
    assert "2026-07-24" in text, "stale snapshot's session date missing"
    assert "STALE" in text
    assert "2026-07-24" in text.split("Degradations")[1] or "STALE" in text.split("Degradations")[1]


def test_degraded_close_brief_keeps_provisional_banner(machine):
    """Degradation must never replace the law-2 regime marker — banners
    stack."""
    from engine.report import render_brief
    p = render_brief("close", {"degraded": True, "verdicts": [], "moves": [],
                               "book": {}, "catalysts": [], "warnings": []},
                     root=machine)
    text = p.read_text(encoding="utf-8")
    assert "banner provisional" in text and "PROVISIONAL" in text
    assert "banner degraded" in text and "DEGRADED" in text


def test_close_brief_monitors_say_not_evaluated(flip_machine):
    """The close pass never runs the Charter §V monitors — the brief must say
    so instead of claiming 'nothing flagged'."""
    closepass.run(offline=True, root=flip_machine)
    text = (flip_machine / "out" / "close.html").read_text(encoding="utf-8")
    assert "not evaluated in this pass" in text
    assert "nothing flagged" not in text


def test_unreadable_catalysts_reach_the_close_brief(flip_machine):
    """A corrupt catalysts.yaml must render as 'unreadable', never as an
    affirmative 'none scheduled'."""
    (flip_machine / "config" / "catalysts.yaml").write_text(
        "catalysts: [unclosed", encoding="utf-8")
    rc = closepass.run(offline=True, root=flip_machine)
    assert rc == 0
    text = (flip_machine / "out" / "close.html").read_text(encoding="utf-8")
    assert "unreadable" in text
    assert "none scheduled" not in text
    assert "Degradations" in text


def test_upcoming_catalysts_window_and_warnings(machine):
    from engine.report import upcoming_catalysts
    cats, warns = upcoming_catalysts(machine, days=30)
    assert warns == []
    # Seeds: Aug 5/13/18 inside 30d of 2026-07-28; Sep 29 outside.
    dates = [c["date"] for c in cats]
    assert "2026-08-05" in dates and "2026-09-29" not in dates


def test_table_headers_are_escaped():
    from engine.report import _table
    out = _table(["<script>"], [["<td>x</td>"]], "empty")
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_premarket_renders_settled_brief(flip_machine):
    """A settled fire shows in the morning brief as FIRED with its consult."""
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    rc = premarket.run(offline=True, root=flip_machine)
    assert rc == 0
    brief = flip_machine / "out" / "premarket.html"
    assert brief.exists()
    text = brief.read_text(encoding="utf-8")
    assert "SETTLED BASIS" in text
    assert 'banner provisional' not in text
    assert "intc-92-flip-example" in text and "FIRED" in text
    assert "never trades" in text  # the constitutional masthead


def test_close_brief_moves_vs_last_settled(flip_machine):
    """Moves compare today's snapshot to the LAST SETTLED close."""
    today = exchange_today("INTC", flip_machine).isoformat()
    append_rows("INTC", [_settled("INTC", "2026-07-27", 80.00)], flip_machine)
    append_rows("INTC", [_snap("INTC", today, 88.00)], flip_machine)
    closepass.run(offline=True, root=flip_machine)
    text = (flip_machine / "out" / "close.html").read_text(encoding="utf-8")
    assert "+10.0%" in text


def test_latest_snapshot_ignores_settled(machine):
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], machine)
    assert latest_snapshot("INTC", machine) is None
    append_rows("INTC", [_snap("INTC", "2026-07-27", 91.63)], machine)
    append_rows("INTC", [_snap("INTC", "2026-07-28", 93.10)], machine)
    snap = latest_snapshot("INTC", machine)
    assert snap is not None and snap.close == 93.10 and snap.settled is False


def test_render_failure_never_fails_the_pass(flip_machine, monkeypatch):
    """The brief is a rendering; losing it must not lose the pass (exit 0,
    loud log row)."""
    def boom(*a, **k):
        raise RuntimeError("render broke")
    monkeypatch.setattr(closepass, "render_brief", boom)
    rc = closepass.run(offline=True, root=flip_machine)
    assert rc == 0
    events = [r["event"] for r in logmod.read(flip_machine)]
    assert "brief_render_failed" in events and "pass_done" in events
