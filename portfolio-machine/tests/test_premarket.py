"""Smoke coverage for the actual cron entrypoint (2026-07-28 review fix:
passes/premarket.py had zero tests). Offline mode only — no network."""
from engine import log as logmod
from engine.fetch import PriceRow, append_rows
from passes.premarket import fetch_universe, run


def _settled(ticker, d, close):
    return PriceRow(ticker=ticker, date=d, close=close, settled=True, source="test")


def test_offline_run_clean_empty_store(machine):
    """Empty price store: pass completes, exit 0, logs start/done, opens no
    consults (the only armed seed wire has no rows to adjudicate on)."""
    rc = run(offline=True, root=machine)
    assert rc == 0
    events = [r["event"] for r in logmod.read(machine)]
    assert "pass_start" in events and "pass_done" in events
    assert not list((machine / "consults").glob("OPEN_*"))


def test_offline_run_fire_propagates_to_consult(flip_machine):
    """A settled in-the-money print on file -> the pass itself opens the
    consult (wire -> verdict -> ticket, end to end)."""
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    rc = run(offline=True, root=flip_machine)
    assert rc == 0
    assert len(list((flip_machine / "consults").glob("OPEN_intc-92-flip-example_*.md"))) == 1
    events = [r["event"] for r in logmod.read(flip_machine)]
    assert "wire_fired" in events


def test_fetch_universe_includes_armed_wire_tickers(flip_machine):
    """Review fix: a wire on a non-held ticker must still be fetched (it used
    to report 'no usable price row' forever)."""
    import yaml
    wires = {"tripwires": [
        {"id": "nvda-test", "ticker": "NVDA",
         "condition": {"op": "gte", "level": 100.0, "basis": "settled_close"},
         "action": "consult", "status": "armed", "note": "test"}]}
    (flip_machine / "config" / "tripwires.yaml").write_text(
        yaml.safe_dump(wires), encoding="utf-8")
    universe = fetch_universe(flip_machine)
    assert "NVDA" in universe          # armed wire, not held
    assert "INTC" in universe          # held
    assert "HKDUSD=X" in universe      # FX for the HKD seat


def test_fetch_universe_skips_retired_wires(machine):
    universe = fetch_universe(machine)
    # intc-92/mu-900 ship retired; INTC/MU appear only because they are held.
    assert "SNDK" in universe          # armed wire + held
    assert "HKDUSD=X" in universe
