"""Consult tickets — the machine's ONLY action when a rule fires (law 1).

A ticket is a markdown file in consults/ with the evidence (provenance
included) and the doors pre-drafted from clauses.yaml. The operator signs in
conversation; the machine never decides.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .paths import ROOT, consults_dir


def write_consult(wire: dict, verdict, clause: dict | None,
                  evidence_rows: list, root: Path = ROOT) -> Path:
    """Idempotent per (wire, session date): re-running a pass never spams
    duplicate tickets."""
    day = (verdict.row_date or datetime.now(timezone.utc).date().isoformat())
    name = f"OPEN_{wire['id']}_{day}.md"
    path = consults_dir(root) / name
    if path.exists():
        return path

    doors = (clause or {}).get("doors") or [
        "ACT: take the pre-agreed action (define it here before signing)",
        "HOLD: reaffirm and re-arm the wire at a new level",
        "AMEND: rewrite the rule; requires written rationale",
    ]
    clause_line = (f"Clause: **{clause['id']}** — {clause.get('title', '')}"
                   if clause else "Clause: none linked (raw wire)")

    evidence_md = "\n".join(
        f"| {r.date} | {r.close} | {'settled' if r.settled else 'snapshot'} "
        f"| {r.source} | {r.fetched_at} | {'CONFLICT' if r.conflict else 'ok'} |"
        for r in evidence_rows
    ) or "| (no rows attached) | | | | | |"

    body = f"""# CONSULT — {wire['id']} fired

Opened: {datetime.now(timezone.utc).isoformat()} (system clock — law 5)
Status: **OPEN — awaiting operator signature**

{clause_line}

## What fired
- Wire: `{wire['id']}` on **{wire.get('ticker')}**
- Condition: `{wire.get('condition')}`
- Verdict: settled close **{verdict.close}** on {verdict.row_date} — {verdict.reason}
- Wire note: {wire.get('note', '').strip()}

## Evidence (provenance — law 3)
| date | close | flag | source | fetched_at | cross-check |
|------|-------|------|--------|-----------|-------------|
{evidence_md}

## Doors (sign exactly one, in conversation)
""" + "\n".join(f"- [ ] {d}" for d in doors) + """

## Signature
- Signed door: _(operator fills in)_
- Signed at:   _(operator fills in)_
- Rationale:   _(operator fills in)_

---
*Constitutional note (law 1): this file is the machine's entire action.
Nothing has been traded, queued, or simulated.*
"""
    path.write_text(body, encoding="utf-8")
    return path
