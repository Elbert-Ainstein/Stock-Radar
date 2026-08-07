"""Repo-root resolution. Every engine function takes root=ROOT so tests run
against a tmp tree without monkeypatching."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def config_dir(root: Path = ROOT) -> Path:
    return Path(root) / "config"


def prices_dir(root: Path = ROOT) -> Path:
    p = Path(root) / "data" / "prices"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_path(root: Path = ROOT) -> Path:
    p = Path(root) / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "log.jsonl"


def consults_dir(root: Path = ROOT) -> Path:
    p = Path(root) / "consults"
    p.mkdir(parents=True, exist_ok=True)
    return p
