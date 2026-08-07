"""Config-integrity pins (2026-07-28 review fix: catalysts.yaml promised
validation nobody performed; clause->wire references and law-1 action fields
were unchecked). Runs on the REAL seed config — these SHOULD move when the
operator breaks a schema."""
from datetime import date

import yaml

from engine.paths import config_dir

CONFIGS = ["holdings.yaml", "tripwires.yaml", "clauses.yaml",
           "catalysts.yaml", "grades.yaml", "market_calendar.yaml"]


def _load(machine, name):
    return yaml.safe_load((config_dir(machine) / name).read_text(encoding="utf-8"))


def test_all_configs_parse(machine):
    for name in CONFIGS:
        assert _load(machine, name) is not None, f"{name} empty or unparseable"


def test_every_wire_is_law1_shaped(machine):
    for w in _load(machine, "tripwires.yaml")["tripwires"]:
        assert w.get("action") == "consult", \
            f"{w.get('id')}: action {w.get('action')!r} — consult is the ONLY action (law 1)"
        assert w.get("status") in ("armed", "retired", "fired")
        cond = w.get("condition") or {}
        assert cond.get("op") in ("gte", "lte")
        assert isinstance(cond.get("level"), (int, float))
        assert w.get("id") and w.get("ticker")


def test_clause_wire_references_resolve(machine):
    """Every machine-checkable clause trigger must point at a real wire.
    'euphoria-protocol' is the documented synthetic exception (computed from
    holdings cost, not tripwires.yaml)."""
    wire_ids = {w["id"] for w in _load(machine, "tripwires.yaml")["tripwires"]}
    for c in _load(machine, "clauses.yaml")["clauses"]:
        wire = (c.get("trigger") or {}).get("wire")
        if wire is None or wire == "euphoria-protocol":
            continue
        assert wire in wire_ids, f"clause {c['id']}: trigger.wire {wire!r} not in tripwires"


def test_catalysts_validate(machine):
    """The premarket validator returns no warnings on the shipped seeds — the
    file's 'Phase 1 validates these' claim stays true."""
    from passes.premarket import validate_catalysts
    assert validate_catalysts(machine) == []
    for c in _load(machine, "catalysts.yaml")["catalysts"]:
        d = c["date"]
        d = d if isinstance(d, date) else date.fromisoformat(str(d))
        assert d.year >= 2026
        assert c["pass"] in ("event", "radar", "premarket-note")


def test_grades_methodology_sound(machine):
    m = _load(machine, "grades.yaml")["methodology"]
    assert abs(sum(m["factors"].values()) - 1.0) < 1e-9
    bands = list(m["letter_bands"].values())
    assert bands == sorted(bands, reverse=True), "letter bands must descend"


def test_calendar_covers_current_year(machine):
    cals = _load(machine, "market_calendar.yaml")["calendars"]
    for name in ("XNYS", "XHKG"):
        assert "holidays_2026" in cals[name], f"{name} lacks 2026 coverage"
    assert _load(machine, "market_calendar.yaml")["suffix_map"].get("HK") == "XHKG"
