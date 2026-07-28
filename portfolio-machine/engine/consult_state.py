"""Consult lifecycle — the machine's one action, followed to its end.

THE GAP THIS CLOSES (2026-07-28): a consult was written to `consults/` and
then left. Nothing tracked whether it was ever answered. For a system whose
entire action is opening consults, an unanswered consult is the one failure
mode that makes the whole apparatus decorative — the wire fires, the ticket
lands, the week gets busy, and the question quietly ages out. Law 1 says the
machine may only ask; it says nothing about being allowed to forget it asked.

So: every pass now counts open tickets, ages them, and prints the oldest on
the brief. Past `OVERDUE_DAYS` a ticket is marked OVERDUE.

Two deliberate non-behaviors:
  - It does NOT escalate into action. An overdue consult produces a louder
    line on a page, never a decision (law 1 is not softened by impatience).
  - It does NOT judge the answer. Any signed door is a complete answer,
    including "do nothing" — the machine has no opinion about which door was
    right, only about whether the question is still open.

Status is read from the DOCUMENT, not the filename, so it works whether you
rename the file, tick a door, or fill in the signature block.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as Date, datetime, timezone
from pathlib import Path

from .paths import ROOT, consults_dir

OVERDUE_DAYS = 7

# "Signed door: _(operator fills in)_" is the unfilled placeholder.
_PLACEHOLDER = re.compile(r"_\(operator fills in\)_")
_SIGNED_DOOR = re.compile(r"^-?\s*Signed door:\s*(.+?)\s*$", re.MULTILINE)
_OPENED = re.compile(r"^Opened:\s*(\S+)", re.MULTILINE)
_TICKED = re.compile(r"^-\s*\[[xX]\]\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class ConsultRecord:
    path: Path
    name: str
    wire_id: str
    ticker: str
    opened: str | None        # ISO timestamp from the ticket body
    age_days: int | None
    status: str               # "OPEN" | "SIGNED"
    signed_door: str | None
    overdue: bool


def _parse_opened(text: str) -> str | None:
    m = _OPENED.search(text)
    return m.group(1) if m else None


def _signed_door(text: str) -> str | None:
    """A door is signed if the signature line is filled in OR a door checkbox
    is ticked. Both are natural ways to answer; neither is more official."""
    m = _SIGNED_DOOR.search(text)
    if m and not _PLACEHOLDER.search(m.group(1)):
        door = m.group(1).strip()
        if door and door not in ("_", "-"):
            return door
    t = _TICKED.search(text)
    if t:
        return t.group(1).strip()
    return None


def _wire_and_ticker(name: str, text: str) -> tuple[str, str]:
    # Filenames look like OPEN_<wire-id>_<date>.md; the body carries the ticker.
    stem = name[:-3] if name.endswith(".md") else name
    for prefix in ("OPEN_", "SIGNED_", "REVIEW_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    wire_id = stem.rsplit("_", 1)[0] if "_" in stem else stem
    m = re.search(r"on \*\*(.+?)\*\*", text)
    return wire_id, (m.group(1) if m else "")


def scan_consults(root: Path = ROOT, today: Date | None = None) -> list[ConsultRecord]:
    """Every ticket in consults/, newest first, with age and answered-ness."""
    today = today or datetime.now(timezone.utc).date()
    out: list[ConsultRecord] = []
    for p in sorted(consults_dir(root).glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        opened = _parse_opened(text)
        age = None
        if opened:
            try:
                age = (today - datetime.fromisoformat(opened).date()).days
            except ValueError:
                age = None
        door = _signed_door(text)
        wire_id, ticker = _wire_and_ticker(p.name, text)
        status = "SIGNED" if door else "OPEN"
        out.append(ConsultRecord(
            path=p, name=p.name, wire_id=wire_id, ticker=ticker, opened=opened,
            age_days=age, status=status, signed_door=door,
            overdue=(status == "OPEN" and age is not None and age >= OVERDUE_DAYS),
        ))
    return sorted(out, key=lambda r: (r.age_days is None, -(r.age_days or 0)))


def open_consults(root: Path = ROOT, today: Date | None = None) -> list[ConsultRecord]:
    return [r for r in scan_consults(root, today) if r.status == "OPEN"]


def summarize(root: Path = ROOT, today: Date | None = None) -> dict:
    """The line every brief carries: how many questions are still unanswered,
    and how long the oldest has been waiting."""
    records = scan_consults(root, today)
    still_open = [r for r in records if r.status == "OPEN"]
    ages = [r.age_days for r in still_open if r.age_days is not None]
    return {
        "open": len(still_open),
        "signed": len(records) - len(still_open),
        "oldest_days": max(ages) if ages else None,
        "overdue": [r.name for r in still_open if r.overdue],
        # Plain dicts: the renderer is a dumb formatter and must not need to
        # know this module's types (it also serializes straight into the log).
        "records": [
            {"name": r.name, "wire_id": r.wire_id, "ticker": r.ticker,
             "opened": r.opened, "age_days": r.age_days, "status": r.status,
             "signed_door": r.signed_door, "overdue": r.overdue}
            for r in records
        ],
    }
