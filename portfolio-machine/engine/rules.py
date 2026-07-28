"""Wire evaluation — the constitutional core (laws 1, 2, 3, 6).

- SETTLED mode is the only mode that adjudicates: fires write consult tickets
  (the machine's ONLY action — law 1), append wire history, and log.
- SNAPSHOT mode produces PROVISIONAL verdicts: logged and returned for
  display, but NO consult, NO status change, NO history append (law 2 —
  the INTC $91.63→$92.52 and MU $899.85→$900.20 flips).
- A conflict-flagged settled row BLOCKS adjudication (law 3): since the
  2026-07-28 review fix, latest_settled surfaces the flagged latest write
  instead of sliding back to a stale clean date, so blocked_on_conflict is
  the live path — the wire stays armed and the verdict says why.
- Law-2 defense in depth: even a row that reached the CSV flagged settled
  cannot adjudicate unless its date is strictly before the ticker's
  exchange-local today.
- Machine-written wire state (status, history) lives in data/wire_state.yaml,
  NOT in config/tripwires.yaml (2026-07-28 review fix: the yaml round-trip
  was destroying the operator's schema comments on first fire — the config
  file is human-only, the state file is machine-only).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date, datetime, timezone
from pathlib import Path

import yaml

from . import log as logmod
from .consults import write_consult
from .fetch import PriceRow, latest_settled, load_rows
from .market_calendar import exchange_today
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


# ── Machine-owned wire state (config stays human-only) ─────────────────────────

def _state_path(root: Path) -> Path:
    p = Path(root) / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "wire_state.yaml"


def load_wire_state(root: Path = ROOT) -> dict:
    p = _state_path(root)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _save_wire_state(state: dict, root: Path = ROOT) -> None:
    _state_path(root).write_text(
        yaml.safe_dump(state, sort_keys=True, allow_unicode=True), encoding="utf-8")


def effective_status(wire: dict, state: dict) -> str:
    """Machine state overrides the config's initial status (a fired wire
    stays fired even though the human file still says armed)."""
    return (state.get(wire.get("id"), {}) or {}).get("status") or wire.get("status", "armed")


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
    wire_id = wire.get("id", "?")
    ticker = wire.get("ticker") or ""
    cond = wire.get("condition") or {}
    op = _OPS.get(str(cond.get("op")))
    level = cond.get("level")
    provisional = mode != "settled"
    if not ticker:
        return Verdict(wire_id, "?", mode, provisional, None, None, None,
                       "malformed wire: no ticker")
    if op is None or not isinstance(level, (int, float)):
        return Verdict(wire_id, ticker, mode, provisional,
                       None, None, None, f"malformed condition: {cond!r}")
    if row is None:
        return Verdict(wire_id, ticker, mode, provisional, None,
                       None, None, "no usable price row")
    if row.conflict:
        return Verdict(wire_id, ticker, mode, provisional, None,
                       row.close, row.date,
                       "blocked_on_conflict — latest settled print is "
                       "flagged; a disputed number cannot adjudicate (law 3)")
    fired = bool(op(row.close, float(level)))
    basis = "settled close" if (row.settled and mode == "settled") else "snapshot"
    return Verdict(wire_id, ticker, mode, provisional, fired,
                   row.close, row.date,
                   f"{basis} {row.close} vs {cond['op']} {level}")


def adjudicate(mode: str, root: Path = ROOT,
               snapshot_rows: dict[str, PriceRow] | None = None) -> list[Verdict]:
    """Evaluate every armed wire.

    mode='settled': adjudicates against the latest settled write per ticker
    (a conflicted latest print BLOCKS — law 3; a not-yet-next-day date
    BLOCKS — law 2 defense in depth); fires open consults + append machine
    state + log (final verdicts).
    mode='snapshot': evaluates against provided snapshot_rows (ticker->row);
    PROVISIONAL — log-and-display only.
    """
    if mode not in ("settled", "snapshot"):
        raise ValueError(f"mode must be settled|snapshot, got {mode!r}")
    data = load_tripwires(root)
    state = load_wire_state(root)
    wires = data.get("tripwires") or []
    verdicts: list[Verdict] = []
    dirty = False

    for wire in wires:
        if effective_status(wire, state) != "armed":
            continue
        ticker = wire.get("ticker") or ""
        if mode == "settled":
            row = latest_settled(ticker, root) if ticker else None
            # Law-2 defense in depth: even a stored settled row may not
            # adjudicate until its session date is strictly past.
            if row is not None and not row.conflict and ticker and \
                    Date.fromisoformat(row.date) >= exchange_today(ticker, root):
                v = Verdict(wire.get("id", "?"), ticker, mode, False, None,
                            row.close, row.date,
                            "row not yet next-day settled (law 2) — refusing")
                verdicts.append(v)
                logmod.append("wire_verdict", root=root, wire=v.wire_id,
                              ticker=v.ticker, mode=v.mode, provisional=False,
                              fired=None, close=v.close, row_date=v.row_date,
                              reason=v.reason)
                continue
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
            entry = state.setdefault(wire["id"], {})
            entry["status"] = "fired"
            entry.setdefault("history", []).append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "fired", "close": v.close, "row_date": v.row_date,
                "consult": ticket.name,
            })
            dirty = True
            logmod.append("wire_fired", root=root, wire=wire["id"],
                          consult=ticket.name, close=v.close, row_date=v.row_date)

    if dirty:
        _save_wire_state(state, root)
    return verdicts


def euphoria_checks(root: Path = ROOT) -> list[dict]:
    """Charter §V euphoria protocol: any position at >= 2x cost basis fires an
    AUTOMATIC consult (doors: trim the preset slice | sign a defense).

    Settled rows only (law 2); a conflicted latest print BLOCKS with a log
    row (law 3). Idempotent per position episode: if any euphoria consult
    (OPEN_ or signed/renamed) already exists for the ticker, no new ticket
    opens — the operator resets by archiving the old ticket.
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
        if row.conflict:
            logmod.append("euphoria_blocked_on_conflict", root=root,
                          ticker=ticker, close=row.close, row_date=row.date)
            continue
        if Date.fromisoformat(row.date) >= exchange_today(ticker, root):
            continue  # law 2 defense in depth
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
    """The +100%-in-trailing-6-months screen (Charter §V).

    Basis (2026-07-28 review fix): gain vs the close AT the window start
    (~6 months ago) — NOT vs the window trough, which flagged round-trips
    that were flat over the period and contradicted the constitution's
    valley-entry doctrine (§IV: drawdowns are the queue, not the hazard).
    Short history is declared, not hidden: findings carry coverage_days.

    Consequence is a SIZING law (starter size only on new entries) and the
    Momentum-RISK redline (methodology v1.2.1: score capped at 20 that day).
    It does NOT open consults — the euphoria protocol (>=2x cost,
    euphoria_checks) covers held positions. Settled unflagged rows only.
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
        from datetime import timedelta as _Td
        cutoff = (Date.fromisoformat(last_d) - _Td(days=window_days)).isoformat()
        window = [d for d in dates if d >= cutoff]
        if not window:
            continue
        base_d = window[0]                    # close at/nearest the window start
        base = per_date[base_d]
        coverage_days = (Date.fromisoformat(last_d) - Date.fromisoformat(base_d)).days
        if base > 0 and (last_close / base - 1.0) >= threshold:
            f = {"ticker": ticker, "gain": round(last_close / base - 1.0, 3),
                 "from": base, "from_date": base_d, "to": last_close,
                 "window_days": window_days, "coverage_days": coverage_days,
                 "note": ("sizing law + Momentum-RISK redline — no consult; "
                          + (f"SHORT HISTORY: screen covers only {coverage_days}d"
                             if coverage_days < window_days - 14 else "full window"))}
            findings.append(f)
            logmod.append("anti_parabola_flag", root=root, **f)
    return findings
