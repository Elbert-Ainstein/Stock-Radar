"""Shared fixtures: a throwaway machine root with real config seeds."""
import shutil
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT))


@pytest.fixture
def machine(tmp_path):
    """A tmp machine root with the repo's real config/ copied in — tests run
    against the actual seed schemas, never hand-rolled approximations."""
    shutil.copytree(PKG_ROOT / "config", tmp_path / "config")
    (tmp_path / "data" / "prices").mkdir(parents=True)
    (tmp_path / "consults").mkdir()
    return tmp_path
