#!/usr/bin/env python3
"""radar_bridge.py — Stock Radar → The Portfolio Machine (one-way, read-only).

The supremacy clause (docs/decisions/RADAR_MACHINE_SYNTHESIS_2026-07-28.md):

    At the point of research, Radar's design rules govern; at the point of
    action, the Machine's laws govern — and everything Radar produces enters
    the action layer only as EVIDENCE inside a consult, never as a verdict.

So this bridge does exactly two things, both of them writes of plain text
into the machine's drop folders:

  1. `data/evidence/<TICKER>.md` — the thesis of record rendered as dated,
     non-binding research. The machine attaches it beneath the settled facts
     on any consult for that ticker, stamped with its age (STALE past 45d).
  2. `data/radar_proposed_wires.yaml` — kill signposts and the thesis
     actionability level rendered as PROPOSED tripwires. This file is NEVER
     read by the engine: the operator ratifies entries by hand into
     `config/tripwires.yaml` (that file is human-only, and a wire nobody
     ratified must never adjudicate a real book).

What the bridge deliberately does NOT do: emit position sizes, conviction as
an instruction, or anything the machine could act on unattended. Radar's
clamp table is advice under SAMLA Law 1 — it rides along as a field the
operator reads, not as a number the machine obeys.

Pure functions (render_evidence / propose_wires) are offline-testable; the
Supabase fetch is a thin wrapper the tests never call.

Usage:
    python scripts/radar_bridge.py LITE               # one ticker
    python scripts/radar_bridge.py --all              # every watchlist name
    python scripts/radar_bridge.py LITE --dry-run     # print, write nothing
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO_ROOT = HERE.parent
MACHINE_ROOT = REPO_ROOT / "portfolio-machine"

# Fields carried into the evidence frontmatter. Conviction rides as a READ
# field; position_size_pct deliberately does not cross the line at all.
META_FIELDS = ("thesis_target", "risk_adj_target", "conviction",
               "strategic_conviction", "thesis_horizon_years",
               "risk_adj_ev_ratio")


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def render_evidence(row: dict) -> str:
    """Thesis row → evidence markdown with YAML frontmatter.

    The body states what the machine needs a HUMAN to weigh: the targets, the
    dated kill signposts, the clock. It never states an action.
    """
    ticker = str(row.get("ticker") or "?").upper()
    run_at = str(row.get("run_at") or "")
    as_of = run_at[:10] or datetime.now(timezone.utc).date().isoformat()

    meta: dict[str, Any] = {
        "source": f"stock-radar thesis {row.get('prompt_version') or ''}".strip(),
        "as_of": as_of,
        "ticker": ticker,
    }
    for k in META_FIELDS:
        if row.get(k) is not None:
            meta[k] = row[k]
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()

    def _bullets(items, empty: str) -> str:
        items = [str(i).strip() for i in (items or []) if str(i).strip()]
        return "\n".join(f"- {i}" for i in items) or f"- _{empty}_"

    spot = _num(row.get("spot_at_run"))
    tgt = _num(row.get("risk_adj_target"))
    implied = (f"{tgt / spot - 1:+.0%} vs the ${spot:,.2f} spot this thesis was "
               f"judged at" if (spot and tgt) else "no spot/target pair on the row")

    return f"""---
{front}
---

# {ticker} — thesis of record (imported research)

**Risk-adjusted target:** {row.get('risk_adj_target') or '—'} ({implied})
**Thesis target:** {row.get('thesis_target') or '—'} ·
**Clock:** {row.get('thesis_horizon_years') or '—'}y ·
**Conviction:** trade {row.get('conviction') or '—'} / structural {row.get('strategic_conviction') or '—'}

## Kill signposts (dated, external, falsifiable)
{_bullets(row.get('kill_triggers'), 'none recorded — treat the thesis as unfalsified, not confirmed')}

## Top risks
{_bullets(row.get('top_risks'), 'none recorded')}

## Catalysts
{_bullets(row.get('top_catalysts'), 'none recorded')}

---
*Exported by scripts/radar_bridge.py. This file is EVIDENCE, not an
instruction: it cannot fire a wire, size a position, or open a ticket. Its
age is stamped on every consult that cites it.*
"""


def propose_wires(row: dict, low_bound: Optional[float] = None) -> list[dict]:
    """Thesis row → PROPOSED tripwires (never auto-armed).

    Two kinds:
      - `actionability`: the price at which the trade gate would stop clamping
        this thesis to BROKEN — the gate's own algebra applied to the thesis's
        own target (design rule 1: no reverse-engineered prices). Proposed as
        a CONSULT wire, because crossing it is a decision moment, not a trade.
      - `signpost`: each dated kill trigger, carried across as text for the
        operator to turn into a level or a calendar entry. Price-checkable
        ones are emitted with a level only when the trigger itself names one.
    """
    ticker = str(row.get("ticker") or "").upper()
    if not ticker:
        return []
    out: list[dict] = []
    tgt = _num(row.get("risk_adj_target"))
    if tgt and tgt > 0:
        if low_bound is None:
            try:
                from trade_gate import DEFAULT_HORIZON_YEARS, horizon_adjusted_table
                h = _num(row.get("thesis_horizon_years")) or DEFAULT_HORIZON_YEARS
                low_bound = next(lower for lower, conv, _ in
                                 horizon_adjusted_table(float(h)) if conv == "LOW")
            except Exception:
                low_bound = 0.95
        level = round(tgt / low_bound, 2)
        out.append({
            "id": f"{ticker.lower()}-thesis-actionability",
            "ticker": ticker,
            "condition": {"op": "lte", "level": level, "basis": "settled_close"},
            "action": "consult",
            "status": "proposed",
            "note": (f"PROPOSED by radar_bridge {datetime.now(timezone.utc).date()}: "
                     f"at/below {level} the thesis's risk-adjusted target "
                     f"({tgt}) clears the trade gate's LOW band — a decision "
                     f"moment, not a trade. Ratify or discard by hand."),
        })
    for i, trig in enumerate(row.get("kill_triggers") or [], 1):
        text = str(trig).strip()
        if not text:
            continue
        out.append({
            "id": f"{ticker.lower()}-signpost-{i}",
            "ticker": ticker,
            "condition": {"op": "manual", "level": None, "basis": "dated_signpost"},
            "action": "consult",
            "status": "proposed",
            "note": f"PROPOSED signpost (L5): {text[:220]}",
        })
    return out


def write_bridge(rows: list[dict], machine_root: Path = MACHINE_ROOT,
                 dry_run: bool = False) -> dict:
    """Write evidence files + the proposed-wires file. Returns a summary."""
    ev_dir = machine_root / "data" / "evidence"
    proposed_path = machine_root / "data" / "radar_proposed_wires.yaml"
    written, wires = [], []
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        md = render_evidence(row)
        wires.extend(propose_wires(row))
        if dry_run:
            print(f"--- {ticker} evidence ({len(md)} chars) ---")
            print(md[:600] + ("…" if len(md) > 600 else ""))
        else:
            ev_dir.mkdir(parents=True, exist_ok=True)
            (ev_dir / f"{ticker}.md").write_text(md, encoding="utf-8")
        written.append(ticker)

    doc = {
        "_note": ("PROPOSED wires exported by scripts/radar_bridge.py. The "
                  "engine NEVER reads this file. Ratify entries by hand into "
                  "config/tripwires.yaml (human-only) to arm them."),
        "_exported_at": datetime.now(timezone.utc).isoformat(),
        "proposed": wires,
    }
    if dry_run:
        print("--- proposed wires ---")
        print(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    else:
        proposed_path.parent.mkdir(parents=True, exist_ok=True)
        proposed_path.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {"tickers": written, "wires": len(wires),
            "evidence_dir": str(ev_dir), "proposed": str(proposed_path)}


def fetch_latest_theses(tickers: list[str]) -> list[dict]:
    """Latest theses row per ticker (verdict of record). Network path — the
    offline tests exercise render_evidence/propose_wires directly."""
    from supabase_helper import get_client
    sb = get_client()
    out = []
    for t in tickers:
        try:
            res = (sb.table("theses").select("*").eq("ticker", t.upper())
                   .order("run_at", desc=True).limit(1).execute())
        except Exception as e:
            print(f"  [bridge] {t}: theses query failed — {e}", file=sys.stderr)
            continue
        if getattr(res, "error", None):
            print(f"  [bridge] {t}: theses query error — {res.error}", file=sys.stderr)
            continue
        rows = res.data or []
        if not rows:
            print(f"  [bridge] {t}: no thesis row on file — skipped", file=sys.stderr)
            continue
        out.append(rows[0])
    return out


def _watchlist() -> list[str]:
    p = REPO_ROOT / "config" / "watchlist.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("tickers") or data.get("watchlist") or []
    return [str(t.get("ticker") if isinstance(t, dict) else t).upper() for t in data]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tickers", nargs="*", help="tickers to export")
    ap.add_argument("--all", action="store_true", help="every watchlist name")
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    args = ap.parse_args()

    tickers = [t.upper() for t in args.tickers] or (_watchlist() if args.all else [])
    if not tickers:
        ap.error("give tickers or --all")
    rows = fetch_latest_theses(tickers)
    if not rows:
        print("[bridge] nothing exported — no thesis rows found", file=sys.stderr)
        return 1
    summary = write_bridge(rows, dry_run=args.dry_run)
    print(f"[bridge] evidence for {', '.join(summary['tickers'])} → "
          f"{summary['evidence_dir']}")
    print(f"[bridge] {summary['wires']} PROPOSED wire(s) → {summary['proposed']} "
          f"(ratify by hand into config/tripwires.yaml)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
