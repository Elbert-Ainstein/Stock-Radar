"""Shared fixtures.

Two tiers (2026-07-28 review fix — the old suite was seed-coupled: replacing
SEED_REPLACE values, the instructed operation, broke 8+ tests):

- `machine`: tmp root with the repo's REAL config/ copied in. For config
  integrity and smoke tests — the ones that SHOULD move when config moves.
- `flip_machine` / `euphoria_machine`: `machine` plus TEST-OWNED yaml
  (schema-true, minimal) overwriting the pieces the scenario touches. The
  settlement-flip and charter regressions run on these and survive any
  operator edit to the seeds.
"""
import shutil
import sys
from pathlib import Path

import pytest
import yaml

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))

# Test-owned copies of the two settlement-flip incident wires (the repo seeds
# ship status: retired so a real first run cannot fire placeholders).
FLIP_WIRES = {
    "tripwires": [
        {"id": "intc-92-flip-example", "ticker": "INTC",
         "condition": {"op": "gte", "level": 92.00, "basis": "settled_close"},
         "action": "consult", "status": "armed",
         "note": "test copy — INTC $91.63 provisional -> $92.52 settled flip"},
        {"id": "mu-900-flip-example", "ticker": "MU",
         "condition": {"op": "gte", "level": 900.00, "basis": "settled_close"},
         "action": "consult", "status": "armed",
         "note": "test copy — MU $899.85 provisional -> $900.20 settled flip"},
    ]
}

# Test-owned holdings for Charter §V scenarios: INTC cost 30 -> 2x line at 60.
EUPHORIA_HOLDINGS = {
    "holdings": [
        {"ticker": "INTC", "name": "Intel (test copy)", "shares": 100,
         "cost": 30.00, "currency": "USD", "sleeve": "test"},
    ],
    "cash": [{"currency": "USD", "amount": 0.00}],
    "floor": {"amount": 40000.00, "currency": "USD",
              "note": "sacred — never invested, never margined (test copy)"},
}


@pytest.fixture
def machine(tmp_path):
    """A tmp machine root with the repo's real config/ copied in."""
    shutil.copytree(PKG_ROOT / "config", tmp_path / "config")
    (tmp_path / "data" / "prices").mkdir(parents=True)
    (tmp_path / "consults").mkdir()
    return tmp_path


@pytest.fixture
def flip_machine(machine):
    """machine + the two flip wires ARMED via a test-owned tripwires.yaml."""
    (machine / "config" / "tripwires.yaml").write_text(
        yaml.safe_dump(FLIP_WIRES, sort_keys=False), encoding="utf-8")
    return machine


@pytest.fixture
def euphoria_machine(machine):
    """machine + test-owned holdings.yaml (known cost basis; real clauses.yaml
    stays — the euphoria doors come from the seed clause, which is charter
    text, not a SEED_REPLACE value)."""
    (machine / "config" / "holdings.yaml").write_text(
        yaml.safe_dump(EUPHORIA_HOLDINGS, sort_keys=False), encoding="utf-8")
    return machine
