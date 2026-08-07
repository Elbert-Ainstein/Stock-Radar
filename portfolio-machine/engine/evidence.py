"""External research evidence — the ONE interface an outside research system
gets into this machine (the supremacy clause, CONSTITUTION machine appendix).

An upstream system (Stock Radar's thesis path, a human, anything) drops a
markdown file with YAML frontmatter at `data/evidence/<TICKER>.md`. This
module reads it and hands it to the consult writer as EVIDENCE — never as a
verdict:

  - it can never fire a wire, size a position, or open a ticket by itself;
  - it is stamped with its own as_of date and rendered STALE past a bound,
    because research ages and the reader must see how old the claim is;
  - a malformed file degrades to a declared warning, never to silence.

Recognized frontmatter (all optional; unknown keys pass through untouched):
  source, as_of, thesis_target, risk_adj_target, conviction,
  strategic_conviction (Type A — drives the DEFEND door note), horizon_years.
"""
from __future__ import annotations

import re
from datetime import date as Date, datetime, timezone
from pathlib import Path

import yaml

from .paths import ROOT

STALE_DAYS = 45  # research older than this is rendered STALE, not hidden


def evidence_dir(root: Path = ROOT) -> Path:
    p = Path(root) / "data" / "evidence"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_evidence(ticker: str, root: Path = ROOT) -> dict | None:
    """Returns {meta, body, as_of, age_days, stale, warnings} or None when no
    file exists. A parse failure returns a dict carrying warnings and an
    empty meta — never None, never a silent skip."""
    if not ticker:
        return None
    path = evidence_dir(root) / f"{ticker.upper().replace('/', '_')}.md"
    if not path.exists():
        return None
    warnings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return {"meta": {}, "body": "", "as_of": None, "age_days": None,
                "stale": True, "warnings": [f"{path.name}: unreadable ({e})"]}

    meta: dict = {}
    body = text
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if m:
        try:
            parsed = yaml.safe_load(m.group(1))
            meta = parsed if isinstance(parsed, dict) else {}
            if not isinstance(parsed, dict):
                warnings.append(f"{path.name}: frontmatter is not a mapping — ignored")
        except Exception as e:
            warnings.append(f"{path.name}: bad frontmatter ({e}) — ignored")
        body = m.group(2)
    else:
        warnings.append(f"{path.name}: no YAML frontmatter — body used as-is")

    as_of, age_days = None, None
    raw = meta.get("as_of")
    if raw is not None:
        try:
            as_of = raw if isinstance(raw, Date) else Date.fromisoformat(str(raw))
            age_days = (datetime.now(timezone.utc).date() - as_of).days
        except Exception:
            warnings.append(f"{path.name}: bad as_of {raw!r} — treated as undated")
    if as_of is None:
        warnings.append(f"{path.name}: undated research (no as_of) — treated as STALE")

    stale = age_days is None or age_days > STALE_DAYS
    return {"meta": meta, "body": body.strip(),
            "as_of": as_of.isoformat() if as_of else None,
            "age_days": age_days, "stale": stale, "warnings": warnings}


def evidence_markdown(ev: dict | None, max_body_chars: int = 2500) -> str:
    """Render evidence for a consult ticket. Always labels the regime: this
    is imported research, dated, and non-binding (law 1 + supremacy clause)."""
    if not ev:
        return ""
    meta = ev.get("meta") or {}
    age = ev.get("age_days")
    stamp = (f"{ev.get('as_of')} ({age}d old)" if ev.get("as_of") else "UNDATED")
    if ev.get("stale"):
        stamp += "  **STALE — older than the freshness bound; weigh accordingly**"
    fields = [(k, meta[k]) for k in
              ("source", "thesis_target", "risk_adj_target", "conviction",
               "strategic_conviction", "horizon_years") if k in meta]
    table = "\n".join(f"| {k} | {v} |" for k, v in fields) or "| (no fields) | |"
    body = (ev.get("body") or "").strip()
    if len(body) > max_body_chars:
        body = body[:max_body_chars].rstrip() + "\n\n… (truncated — full file in data/evidence/)"
    warns = "".join(f"\n> ⚠ {w}" for w in ev.get("warnings") or [])
    return f"""
## Imported research evidence (NOT a verdict)
As of: {stamp}{warns}

| field | value |
|-------|-------|
{table}

{body}

*Supremacy clause: research informs the doors; only the operator's signature
decides. This machine adjudicates settled facts, not theses.*
"""


def type_a_defense_note(ev: dict | None) -> str:
    """Type A (structural, price-independent) conviction meets the euphoria
    protocol's DEFEND door: holding a doubled Type A name requires exactly
    the signed paragraph §V asks for, and it must cite this thesis."""
    meta = (ev or {}).get("meta") or {}
    sc = str(meta.get("strategic_conviction") or "").strip().upper()
    if not sc or sc in ("BROKEN", "NONE"):
        return ""
    return (f"\n> **Type A note:** imported research carries strategic conviction "
            f"**{sc}** (price-independent). If you choose DEFEND, the signed "
            f"paragraph must cite that thesis by name and say what would end it.\n")
