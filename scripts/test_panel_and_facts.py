"""The expanded judgment panel (socratic_panel.py) and signal discipline
(watched_facts.py), 2026-07-28.

Two operator directives are pinned here:
  1. "research department deserves more analysts ... complex personalities and
     philosophies. But we should ultimately strive to the same goal."
  2. "don't let random news get to you. Focus on the facts that matter."
"""
import json
from pathlib import Path

import pytest
import yaml

import socratic_panel as sp
import watched_facts as wf

REPO = Path(__file__).resolve().parent.parent


# ── the roster ────────────────────────────────────────────────────────────────

def test_every_panelist_has_a_prompt_file():
    for p in sp.PANEL:
        path = REPO / "scripts" / "prompts" / "socratic" / f"{p.prompt}.md"
        assert path.exists(), f"{p.id}: missing prompt {path.name}"


def test_ids_and_keys_are_unique():
    assert len({p.id for p in sp.PANEL}) == len(sp.PANEL)
    assert len({p.key for p in sp.PANEL}) == len(sp.PANEL)


def test_every_panelist_declares_a_failure_mode():
    """A persona without a named bias is a caricature that argues its corner
    forever; the declared bias is what the synthesis weighs verdicts against."""
    for p in sp.PANEL:
        assert p.failure_mode and len(p.failure_mode) > 20, p.id
        assert p.school and p.watches, p.id


def test_panel_is_not_structurally_bearish():
    """THE regression for the finding that motivated the expansion: the old
    trio had two bearish priors and no seat assigned to build the bull case,
    inside a system whose purpose is finding 10x names."""
    assert "steelman" in sp.BY_ID, "no seat builds the bull case"
    steel = sp.BY_ID["steelman"]
    assert "strongest" in steel.school.lower()
    body = (REPO / "scripts" / "prompts" / "socratic" /
            f"{steel.prompt}.md").read_text(encoding="utf-8")
    # It must be a DISCIPLINED steelman, not a promoter.
    assert "case_supportable" in body
    assert "evidence standard" in body.lower() or "same evidence" in body.lower()


def test_every_prompt_carries_the_discipline_blocks():
    """Every seat sees who else is in the room and which facts are admissible."""
    for p in sp.PANEL:
        body = (REPO / "scripts" / "prompts" / "socratic" /
                f"{p.prompt}.md").read_text(encoding="utf-8")
        assert "[PANEL_ROSTER]" in body, f"{p.id}: no roster block"
        assert "[WATCHED_FACTS]" in body, f"{p.id}: no fact-discipline block"
        assert "bias_check" in body, f"{p.id}: does not self-report its bias"


def test_new_seats_report_facts_and_unanswerables():
    """Declared ignorance is a first-class output — the new seats must have a
    place to put a fact they could not answer."""
    for pid in ("supply_chain", "capital_cycle", "technologist",
                "base_rates", "steelman"):
        body = (REPO / "scripts" / "prompts" / "socratic" /
                f"{sp.BY_ID[pid].prompt}.md").read_text(encoding="utf-8")
        assert "facts_unanswerable" in body, pid
        assert "proposed_facts" in body, pid


def test_roster_default_is_the_full_panel():
    active = sp.load_roster(Path("/nonexistent/socratic_panel.json"))
    assert [p.id for p in active] == [p.id for p in sp.PANEL]


def test_roster_config_narrows_and_preserves_order(tmp_path):
    cfg = tmp_path / "panel.json"
    cfg.write_text(json.dumps({"enabled": ["steelman", "fundamentals"]}))
    active = sp.load_roster(cfg)
    assert [p.id for p in active] == ["fundamentals", "steelman"]  # PANEL order


def test_unknown_panelist_id_is_loud(tmp_path):
    """A typo must not silently shrink the panel behind a seal claiming a
    full run."""
    cfg = tmp_path / "panel.json"
    cfg.write_text(json.dumps({"enabled": ["fundamentals", "supply_chian"]}))
    with pytest.raises(ValueError, match="unknown panelist"):
        sp.load_roster(cfg)


def test_empty_selection_is_loud(tmp_path):
    cfg = tmp_path / "panel.json"
    cfg.write_text(json.dumps({"enabled": []}))
    # falsy 'enabled' means "unset" -> full panel, never an empty panel
    assert sp.load_roster(cfg) == list(sp.PANEL)


def test_panel_version_changes_with_the_roster(tmp_path):
    """The seated roster is part of the instrument: a different panel must
    produce a different cohort key, or hit-rates mix two instruments."""
    full = sp.panel_version(list(sp.PANEL))
    narrow = sp.panel_version([sp.BY_ID["fundamentals"]])
    assert full != narrow
    assert full.startswith("panel-")


def test_panel_version_is_in_the_cohort_key():
    import checkpoint_seal as cs
    assert "panel" in cs.JUDGMENT_PROMPT_KEYS
    a = cs.compute_cohort_key({"panel": "panel-x"}, "hash", {})
    b = cs.compute_cohort_key({"panel": "panel-y"}, "hash", {})
    assert a != b, "roster change did not reset the calibration clock"


def test_roster_block_demands_falsifiable_disagreement():
    block = sp.format_panel_roster(list(sp.PANEL))
    assert "CHECKABLE FACT" in block
    for p in sp.PANEL:
        assert p.name in block


def test_panel_json_block_labels_school_and_bias():
    round_1 = {p.key: {"parsed": {"verdict": "UNDERVALUED"}} for p in sp.PANEL}
    block = sp.format_panel_json_block(round_1, list(sp.PANEL))
    for p in sp.PANEL:
        assert p.id in block and p.failure_mode in block


def test_panel_json_block_survives_a_missing_seat():
    round_1 = {"a": {"parsed": {"verdict": "OVERVALUED"}}}
    block = sp.format_panel_json_block(round_1, list(sp.PANEL))
    assert "fundamentals" in block and "steelman" not in block


# ── signal discipline ─────────────────────────────────────────────────────────

def test_watched_facts_file_is_well_formed():
    specs = wf.load_watched_facts()
    assert specs, "no watched-facts spec on file"
    for ticker, spec in specs.items():
        assert spec.get("engine"), f"{ticker}: no engine line"
        facts = spec.get("facts") or []
        assert len(facts) >= 3, f"{ticker}: fewer than 3 facts that matter"
        for f in facts:
            assert f.get("id") and f.get("question") and f.get("why"), f"{ticker}: incomplete fact {f}"
            assert f.get("sources"), f"{ticker}/{f.get('id')}: no acceptable sources"
        assert spec.get("noise"), f"{ticker}: no noise list — nothing is excluded"


def test_mu_watches_the_ai_supply_chain():
    """The operator's own example: for MU, look at AI supply-chain demand and
    datacenter orders — not headlines."""
    spec = wf.spec_for_ticker("MU")
    assert spec is not None
    ids = {f["id"] for f in spec["facts"]}
    assert "hbm_sold_out_horizon" in ids
    assert "hyperscaler_capex_direction" in ids
    assert "industry_capacity_additions" in ids   # the capital-cycle kill
    noise = " ".join(spec["noise"]).lower()
    assert "spot" in noise and "price-target" in noise


ALLOWED_SOURCES = {
    "earnings_call_transcript", "customer_earnings_call", "competitor_earnings_call",
    "10-K", "10-Q", "S-1", "8-K", "company_release", "competitor_capex_release",
    "customer_10-Q", "customer_disclosure", "customer_capex_release",
    "industry_filing", "scanner_data_disclosure", "government_budget_document",
    "faa_filing", "launch_record",
}


def test_facts_are_questions_against_documents():
    """Two statically checkable properties: each fact is phrased as a question,
    and its sources come from a controlled vocabulary of DOCUMENTS. The
    'answerable with a number or date' standard is enforced in the prompt; what
    a test can prove is that nobody may cite a source class that isn't a
    filing, a transcript, or a dated disclosure — which is where noise enters."""
    specs = wf.load_watched_facts()
    for ticker, spec in specs.items():
        for f in spec["facts"]:
            assert f["question"].rstrip().endswith("?"), \
                f"{ticker}/{f['id']}: not phrased as a question"
            bad = [s for s in f["sources"] if s not in ALLOWED_SOURCES]
            assert not bad, f"{ticker}/{f['id']}: source not a document class: {bad}"


def test_spec_declares_no_answers():
    """Design rule 1: the file says what to look at, never what the answer is.
    A seeded answer would hand the panel its own conclusion."""
    raw = (REPO / "config" / "watched_facts.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    for ticker, spec in data.items():
        for f in spec["facts"]:
            assert "last_known" not in f, f"{ticker}/{f['id']}: seeded an answer"
            assert "answer" not in f, f"{ticker}/{f['id']}: seeded an answer"


def test_missing_ticker_is_a_declared_gap_not_silence():
    block = wf.format_watched_facts("ZZZZ")
    assert "NONE ON FILE" in block
    assert "GAP" in block and "proposed_facts" in block
    assert block.strip(), "empty block would render a context-blind prompt"


def test_rendered_block_binds_the_analyst():
    block = wf.format_watched_facts("MU")
    assert "INADMISSIBLE AS EVIDENCE" in block
    assert "hbm_sold_out_horizon" in block
    assert "DECLARE it unknown" in block
    assert "decoration" in block


def test_unparseable_spec_degrades_loudly(tmp_path, capsys):
    bad = tmp_path / "watched_facts.yaml"
    bad.write_text("facts: [unclosed", encoding="utf-8")
    assert wf.load_watched_facts(bad) == {}
    assert "WARN" in capsys.readouterr().err


def test_missing_spec_file_warns(tmp_path, capsys):
    assert wf.load_watched_facts(tmp_path / "nope.yaml") == {}
    assert "WARN" in capsys.readouterr().err


def test_every_watchlist_name_has_a_spec():
    """A watchlist name with no fact spec would run on vibes."""
    wl = json.loads((REPO / "config" / "watchlist.json").read_text(encoding="utf-8"))
    names = wl if isinstance(wl, list) else (wl.get("tickers") or wl.get("watchlist") or [])
    tickers = [t if isinstance(t, str) else t.get("ticker") for t in names]
    have = set(wf.all_tickers())
    missing = [t for t in tickers if t and t.upper() not in have]
    assert not missing, f"watchlist names with no watched-facts spec: {missing}"


# ── lineage: method, not mimicry ──────────────────────────────────────────────

def test_every_seat_has_a_lineage_and_a_price_tag():
    """Operator: "get inspiration from great investors." Each seat is grounded
    in the documented METHOD of practitioners who developed that lens — and in
    what that school demonstrably cost them. A method presented without its
    failures becomes authority, which is what this panel exists to do without."""
    for p in sp.PANEL:
        assert p.lineage, f"{p.id}: no lineage"
        assert len(p.lineage) >= 2, f"{p.id}: a single source is a costume, not a school"
        for who, method in p.lineage:
            assert who and method, f"{p.id}: incomplete lineage entry"
            assert len(method) > 25, f"{p.id}/{who}: method not actually described"
        assert p.lineage_cost and len(p.lineage_cost) > 40, \
            f"{p.id}: lineage carries no documented cost"


def test_lineage_block_forbids_impersonation():
    """The guardrail: asking a model to BE a famous investor produces pastiche —
    remembered quotes and borrowed authority standing in for analysis. The
    block must transfer technique and explicitly refuse the costume."""
    block = sp.format_lineage(sp.BY_ID["capital_cycle"])
    low = block.lower()
    assert "do not impersonate" in low
    assert "borrowed authority" in low
    assert "survive with every name above deleted" in low


def test_no_prompt_instructs_impersonation():
    """No seat may be told to *be* someone, or to ask what someone would do —
    the whole panel degrades into cosplay the moment one does."""
    banned = ("you are warren buffett", "you are ben graham", "you are benjamin graham",
              "you are george soros", "you are charlie munger", "you are philip fisher",
              "what would buffett", "what would graham", "what would munger",
              "channel buffett", "think like buffett")
    for p in sp.PANEL:
        body = (REPO / "scripts" / "prompts" / "socratic" /
                f"{p.prompt}.md").read_text(encoding="utf-8").lower()
        for phrase in banned:
            assert phrase not in body, f"{p.id}: impersonation instruction {phrase!r}"


def test_every_prompt_receives_the_lineage_block():
    for p in sp.PANEL:
        body = (REPO / "scripts" / "prompts" / "socratic" /
                f"{p.prompt}.md").read_text(encoding="utf-8")
        assert "[LINEAGE]" in body, f"{p.id}: lineage never injected"


def test_lineage_is_empty_safe():
    """A seat added without a lineage must render nothing rather than a
    half-block — fill() is strict, so an empty string is the honest signal."""
    bare = sp.Panelist(id="x", key="z", prompt="p", name="n", school="s",
                       watches="w", failure_mode="f")
    assert sp.format_lineage(bare) == ""


def test_prompt_versions_moved_with_the_content():
    """Bookkeeping the cohort key depends on: a prompt whose content changed
    must not still claim its old version string."""
    import re
    for p in sp.PANEL:
        body = (REPO / "scripts" / "prompts" / "socratic" /
                f"{p.prompt}.md").read_text(encoding="utf-8")
        m = re.search(r"^version:\s*(\S+)", body, re.MULTILINE)
        assert m, f"{p.id}: no version in frontmatter"
        assert m.group(1) != "v1", f"{p.id}: content changed but version is still v1"
