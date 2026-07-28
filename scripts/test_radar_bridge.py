"""radar_bridge: the ONE interface Radar gets into the Portfolio Machine.

The load-bearing pins are the supremacy clause's限 limits — evidence never
crosses as an instruction, proposed wires are never armed, and position
sizing does not cross the line at all."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import radar_bridge as rb

ROW = {
    "ticker": "LITE",
    "run_at": "2026-07-20T12:00:00+00:00",
    "prompt_version": "v3.4.4",
    "thesis_target": 180.0,
    "risk_adj_target": 142.5,
    "conviction": "MEDIUM",
    "strategic_conviction": "HIGH",
    "thesis_horizon_years": 3.0,
    "risk_adj_ev_ratio": 0.95,
    "spot_at_run": 150.0,
    "position_size_pct": 25,
    "kill_triggers": [
        "800G transceiver certification decision slips past 2027-Q2",
        "gross margin below 32% for two consecutive prints",
    ],
    "top_risks": ["customer concentration >40%"],
    "top_catalysts": ["Q3 print 2026-08-13"],
}


def test_evidence_carries_frontmatter_and_signposts():
    md = rb.render_evidence(ROW)
    assert md.startswith("---\n")
    meta = yaml.safe_load(md.split("---")[1])
    assert meta["ticker"] == "LITE" and meta["as_of"] == "2026-07-20"
    assert meta["strategic_conviction"] == "HIGH"      # drives the DEFEND door
    assert meta["risk_adj_target"] == 142.5
    assert "certification decision slips past 2027-Q2" in md
    assert "-5%" in md  # 142.5 vs 150 spot, stated as an implied move


def test_position_size_never_crosses_the_line():
    """SAMLA law 1: sizing is advice. It may not enter the action layer even
    as a field."""
    md = rb.render_evidence(ROW)
    assert "position_size" not in md and "25%" not in md


def test_evidence_declares_itself_non_binding():
    md = rb.render_evidence(ROW)
    assert "EVIDENCE, not an" in md
    assert "cannot fire a wire" in md


def test_missing_signposts_are_declared_not_hidden():
    md = rb.render_evidence({**ROW, "kill_triggers": []})
    assert "unfalsified, not confirmed" in md


def test_proposed_wires_are_never_armed():
    wires = rb.propose_wires(ROW, low_bound=0.95)
    assert wires and all(w["status"] == "proposed" for w in wires)
    assert all(w["action"] == "consult" for w in wires)   # law 1
    assert all("PROPOSED" in w["note"] for w in wires)


def test_actionability_wire_uses_the_gate_algebra():
    # 142.5 / 0.95 = 150.0 — the price at which the gate stops clamping.
    wire = rb.propose_wires(ROW, low_bound=0.95)[0]
    assert wire["id"] == "lite-thesis-actionability"
    assert wire["condition"]["level"] == 150.0
    assert wire["condition"]["op"] == "lte"


def test_each_signpost_becomes_a_proposal():
    wires = rb.propose_wires(ROW, low_bound=0.95)
    signposts = [w for w in wires if "signpost" in w["id"]]
    assert len(signposts) == 2
    assert all(w["condition"]["basis"] == "dated_signpost" for w in signposts)


def test_no_target_no_price_wire_invented():
    wires = rb.propose_wires({**ROW, "risk_adj_target": None}, low_bound=0.95)
    assert not [w for w in wires if "actionability" in w["id"]]   # design rule 1


def test_write_bridge_lands_in_the_machine_drop_folders(tmp_path):
    summary = rb.write_bridge([ROW], machine_root=tmp_path)
    ev = tmp_path / "data" / "evidence" / "LITE.md"
    assert ev.exists() and "thesis of record" in ev.read_text()
    doc = yaml.safe_load((tmp_path / "data" / "radar_proposed_wires.yaml").read_text())
    assert doc["proposed"] and all(w["status"] == "proposed" for w in doc["proposed"])
    assert "engine NEVER reads this file" in doc["_note"]
    assert summary["tickers"] == ["LITE"]
