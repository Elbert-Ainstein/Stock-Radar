"""Wire evaluation — the constitutional core (laws 1, 2, 3, 6).

- SETTLED mode is the only mode that adjudicates: fires write consult tickets
  (the machine's ONLY action — law 1), append wire history, and log.
- SNAPSHOT mode produces PROVISIONAL verdicts: logged and returned for
  display, but NO consult, NO status change, NO history append (law 2 —
  the INTC $91.63→$92.52 and MU $899.85→$900.20 flips).
- A conflict-flagged settled row cannot adjudicate (law 3): the wire logs a
  'blocked_on_conflict' verdict instead and stays armed.
- tripwires.yaml history is append-only; status transitions armed→fired only
  here, and nothing in this module can un-fire or edit history (law 6).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import log as logmod
from .consults import write_consult
from .fetch import PriceRow, latest_settled, load_rows
from .paths import ROOT, config_dir

_OPS = {
    "gte": lambda close, level: close >= level,
    "lte": lambda close, level: close <= level,
}


@dataclass
class Verdict:
    wire_id: str
    ticker: str
    mode: str                 # "settled" | "snapshot"
    provisional: bool         # True in snapshot mode — never actionable
    fired: bool | None        # None = could not adjudicate (no row / conflict)
    close: float | None
    row_date: str | None
    reason: str


def load_tripwires(root: Path = ROOT) -> dict:
    p = config_dir(root) / "tripwires.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {"tripwires": []}


def _save_tripwires(data: dict, root: Path = ROOT) -> None:
    p = config_dir(root) / "tripwires.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                 encoding="utf-8")


def _clause_for_wire(wire_id: str, root: Path) -> dict | None:
    p = config_dir(root) / "clauses.yaml"
    if not p.exists():
        return None
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    for c in data.get("clauses") or []:
        trig = c.get("trigger") or {}
        if trig.get("wire") == wire_id:
            return c
    return None


def evaluate(wire: dict, row: PriceRow | None, mode: str) -> Verdict:
    """Pure evaluation of one wire against one price row."""
    cond = wire.get("condition") or {}
    op = _OPS.get(str(cond.get("op")))
    level = cond.get("level")
    provisional = mode != "settled"
    if op is None or not isinstance(level, (int, float)):
        return Verdict(wire["id"], wire.get("ticker", "?"), mode, provisional,
                       None, None, None, f"malformed condition: {cond!r}")
    if row is None:
        return Verdict(wire["id"], wire["ticker"], mode, provisional, None,
                       None, None, "no usable price row")
    if row.conflict:
        return Verdict(wire["id"], wire["ticker"], mode, provisional, None,
                       row.close, row.date,
                       "blocked_on_conflict — flagged row cannot adjudicate (law 3)")
    fired = bool(op(row.close, float(level)))
    basis = "settled close" if (row.settled and mode == "settled") else "snapshot"
    return Verdict(wire["id"], wire["ticker"], mode, provisional, fired,
                   row.close, row.date,
                   f"{basis} {row.close} vs {cond['op']} {level}")


def adjudicate(mode: str, root: Path = ROOT,
               snapshot_rows: dict[str, PriceRow] | None = None) -> list[Verdict]:
    """Evaluate every armed wire.

    mode='settled': adjudicates against latest unflagged settled rows on file;
    fires open consults + append history + log (final verdicts).
    mode='snapshot': evaluates against provided snapshot_rows (ticker->row);
    PROVISIONAL — log-and-display only.
    """
    if mode not in ("settled", "snapshot"):
        raise ValueError(f"mode must be settled|snapshot, got {mode!r}")
    data = load_tripwires(root)
    wires = data.get("tripwires") or []
    verdicts: list[Verdict] = []
    dirty = False

    for wire in wires:
        if wire.get("status") != "armed":
            continue
        ticker = wire.get("ticker", "")
        if mode == "settled":
            row = latest_settled(ticker, root)
        else:
            row = (snapshot_rows or {}).get(ticker)
        v = evaluate(wire, row, mode)
        verdicts.append(v)

        logmod.append(
            "wire_verdict", root=root, wire=v.wire_id, ticker=v.ticker,
            mode=v.mode, provisional=v.provisional, fired=v.fired,
            close=v.close, row_date=v.row_date, reason=v.reason,
        )

        if mode == "settled" and v.fired:
            clause = _clause_for_wire(wire["id"], root)
            evidence = [r for r in load_rows(ticker, root)
                        if r.settled and r.date == v.row_date]
            ticket = write_consult(wire, v, clause, evidence, root=root)
            wire.setdefault("history", []).append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "fired", "close": v.close, "row_date": v.row_date,
                "consult": ticket.name,
            })
            wire["status"] = "fired"
            dirty = True
            logmod.append("wire_fired", root=root, wire=wire["id"],
                          consult=ticket.name, close=v.close, row_date=v.row_date)

    if dirty:
        _save_tripwires(data, root)
    return verdicts


def euphoria_checks(root: Path = ROOT) -> list[dict]:
    """Charter §V euphoria protocol: any position at >= 2x cost basis fires an
    AUTOMATIC consult (doors: trim the preset slice | sign a defense).

    Settled rows only (law 2). Idempotent per position episode: if any
    euphoria consult (OPEN_ or signed/renamed) already exists for the ticker,
    no new ticket opens — the operator resets by archiving the old ticket.
    """
    import yaml as _yaml
    holdings = (_yaml.safe_load((config_dir(root) / "holdings.yaml")
                                .read_text(encoding="utf-8")) or {}).get("holdings") or []
    clause = None
    clauses_p = config_dir(root) / "clauses.yaml"
    if clauses_p.exists():
        for c in (_yaml.safe_load(clauses_p.read_text(encoding="utf-8")) or {}).get("clauses") or []:
            if c.get("id") == "euphoria-protocol":
                clause = c
                break

    from .paths import consults_dir
    fired = []
    for seat in holdings:
        ticker, cost = seat.get("ticker"), float(seat.get("cost") or 0)
        if not ticker or cost <= 0:
            continue
        row = latest_settled(ticker, root)
        if row is None or row.close < 2.0 * cost:
            continue
        slug = f"euphoria-{ticker.replace('.', '_')}"
        existing = list(consults_dir(root).glob(f"*{slug}*"))
        if existing:
            continue  # episode already open/signed — operator archives to reset
        wire = {"id": slug, "ticker": ticker,
                "condition": {"op": "gte", "level": round(2.0 * cost, 2),
                              "basis": "settled_close (2x cost basis)"},
                "note": f"Charter §V euphoria protocol: {ticker} at "
                        f"{row.close} >= 2x cost {cost}"}
        v = Verdict(slug, ticker, "settled", False, True, row.close, row.date,
                    f"settled close {row.close} >= 2x cost {cost}")
        evidence = [r for r in load_rows(ticker, root)
                    if r.settled and r.date == row.date]
        ticket = write_consult(wire, v, clause, evidence, root=root)
        f = {"ticker": ticker, "close": row.close, "cost": cost,
             "multiple": round(row.close / cost, 2), "consult": ticket.name}
        fired.append(f)
        logmod.append("euphoria_fired", root=root, **f)
    return fired


def anti_parabola(root: Path = ROOT, threshold: float = 1.0,
                  window_days: int = 183) -> list[dict]:
    """The +100%/6mo screen — leg (a) of the euphoria double-trigger.

    Consequence is a SIZING law (starter size only on new entries, Charter §V)
    and the Momentum-RISK redline (methodology v1.2.1: score capped at 20
    that day). It does NOT open consults — the euphoria protocol (>=2x cost,
    euphoria_checks) covers held positions. Settled rows only; logs findings.
    """
    import yaml as _yaml
    holdings_p = config_dir(root) / "holdings.yaml"
    holdings = (_yaml.safe_load(holdings_p.read_text(encoding="utf-8")) or {}).get("holdings") or []
    findings = []
    for seat in holdings:
        ticker = seat.get("ticker")
        per_date = {}
        for r in load_rows(ticker, root):
            if r.settled and not r.conflict:
                per_date[r.date] = r.close
        if len(per_date) < 2:
            continue
        dates = sorted(per_date)
        last_d = dates[-1]
        last_close = per_date[last_d]
        from datetime import date as _Date, timedelta as _Td
        cutoff = (_Date.fromisoformat(last_d) - _Td(days=window_days)).isoformat()
        window = [d for d in dates if d >= cutoff]
        if not window:
            continue
        base = min(per_date[d] for d in window)
        if base > 0 and (last_close / base - 1.0) >= threshold:
            f = {"ticker": ticker, "gain": round(last_close / base - 1.0, 3),
                 "from": base, "to": last_close, "window_days": window_days,
                 "note": "leg (a) only — no consult without operator euphoria read (leg b)"}
            findings.append(f)
            logmod.append("anti_parabola_flag", root=root, **f)
    return findings
