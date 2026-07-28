"""Append-only JSONL log (laws 5 + 6).

- Every row stamps from the SYSTEM CLOCK at write time (law 5).
- There is deliberately NO update or delete API in this module (law 6):
  a wrong row gets a correction row via correct(), never an edit.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .paths import ROOT, log_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append(event: str, root: Path = ROOT, **fields) -> dict:
    """Append one event row. Returns the row (including its timestamp)."""
    row = {"ts": _now_iso(), "event": event, **fields}
    with open(log_path(root), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return row


def correct(corrects_ts: str, reason: str, root: Path = ROOT, **fields) -> dict:
    """Law 6: corrections go forward. References the wrong row by timestamp;
    never touches it."""
    return append("correction", root=root, corrects_ts=corrects_ts,
                  reason=reason, **fields)


def read(root: Path = ROOT) -> list[dict]:
    p = log_path(root)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows
