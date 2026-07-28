"""Built-in visual briefs — the machine reports before and after the market.

Two briefs, one per pass, rendered as self-contained HTML into out/:
  - out/premarket.html  (SETTLED basis — the morning verdicts of record)
  - out/close.html      (PROVISIONAL basis — law 2: nothing here is
                         actionable until it settles tomorrow morning)

Design rules:
  - The brief is a RENDERING of what the pass already did and logged — it
    never computes new verdicts, opens consults, or touches state.
  - Law 2 is visual: the close brief wears a PROVISIONAL banner; premarket
    wears the settled one. A reader who sees only the header knows which
    regime they are looking at.
  - A render failure must never lose the pass's constitutional work: passes
    wrap render_brief in try/except and log loudly on failure.
  - Stdlib only; no external assets (the file opens from disk, offline).
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .paths import ROOT, config_dir


def out_dir(root: Path = ROOT) -> Path:
    p = Path(root) / "out"
    p.mkdir(parents=True, exist_ok=True)
    return p


def upcoming_catalysts(root: Path = ROOT, days: int = 30
                       ) -> tuple[list[dict] | None, list[str]]:
    """Catalysts within `days`, sorted by date, plus warnings. Returns
    (None, [warning]) when the file is missing/unreadable — the brief must
    say 'unreadable', never 'none scheduled' (2026-07-28 review fix: the
    close pass rendered an affirmative empty state over a parse failure)."""
    from datetime import date as Date
    p = config_dir(root) / "catalysts.yaml"
    if not p.exists():
        return None, ["catalysts.yaml missing"]
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return None, [f"catalysts.yaml unreadable: {e}"]
    today = datetime.now(timezone.utc).date()
    out, warns = [], []
    for i, c in enumerate(data.get("catalysts") or []):
        d = c.get("date")
        try:
            d = d if isinstance(d, Date) else Date.fromisoformat(str(d))
        except Exception:
            warns.append(f"catalysts.yaml row #{i}: bad date {c.get('date')!r} — skipped")
            continue
        if today <= d <= Date.fromordinal(today.toordinal() + days):
            out.append({"date": d.isoformat(), "ticker": str(c.get("ticker") or ""),
                        "what": str(c.get("what") or "")})
    return sorted(out, key=lambda c: c["date"]), warns


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _fmt(v, places: int = 2) -> str:
    try:
        return f"{float(v):,.{places}f}"
    except (TypeError, ValueError):
        return "—"


_CSS = """
:root{--paper:#FAFAF7;--ink:#1C2620;--muted:#66716B;--line:#DDE2DC;--card:#FFF;
--well:#F1F3EE;--green:#0E6E5C;--greensoft:#E3EFEA;--red:#B3372E;--redsoft:#F6E7E4;
--amber:#9A6A1B;--ambersoft:#F4ECDD;
--mono:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace;
--sans:"Avenir Next","Segoe UI",system-ui,Helvetica,Arial,sans-serif}
@media (prefers-color-scheme:dark){:root{--paper:#0E1412;--ink:#E6EAE3;--muted:#8A968E;
--line:#26312B;--card:#141C18;--well:#1A231E;--green:#46B294;--greensoft:#12271F;
--red:#E0685C;--redsoft:#2E1815;--amber:#D9A03F;--ambersoft:#2A2113}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:var(--sans);font-size:14px;line-height:1.45}
.wrap{max-width:980px;margin:0 auto;padding:24px 18px 56px}
h1{font-family:var(--mono);font-size:19px;margin:0;text-transform:uppercase;letter-spacing:.04em}
h2{font-family:var(--mono);font-size:12px;text-transform:uppercase;color:var(--muted);
margin:34px 0 12px;letter-spacing:.12em}
.mast{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 16px;
border-bottom:2px solid var(--ink);padding-bottom:12px}
.eyebrow{font-family:var(--mono);font-size:10.5px;letter-spacing:.18em;
text-transform:uppercase;color:var(--muted);width:100%}
.when{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-left:auto}
.banner{margin-top:14px;padding:10px 14px;font-family:var(--mono);font-size:12.5px;
letter-spacing:.06em;border:2px solid}
.banner.settled{border-color:var(--green);background:var(--greensoft);color:var(--green)}
.banner.provisional{border-color:var(--amber);background:var(--ambersoft);color:var(--amber)}
.banner.degraded{border-color:var(--red);background:var(--redsoft);color:var(--red)}
.pill{display:inline-block;font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;
padding:2px 9px;border-radius:999px;border:1px solid;white-space:nowrap}
.pill.ok{background:var(--greensoft);color:var(--green);border-color:var(--green)}
.pill.bad{background:var(--redsoft);color:var(--red);border-color:var(--red)}
.pill.wait{background:var(--ambersoft);color:var(--amber);border-color:var(--amber)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
background:var(--line);border:1px solid var(--line);margin-top:18px}
.stat{background:var(--card);padding:13px 16px}
.stat b{display:block;font-family:var(--mono);font-size:26px;font-weight:600;
font-variant-numeric:tabular-nums;line-height:1.15}
.stat span{font-family:var(--mono);font-size:10px;letter-spacing:.1em;
text-transform:uppercase;color:var(--muted)}
.stat .up{color:var(--green)}.stat .down{color:var(--red)}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);font-size:12.5px}
th{font-family:var(--mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;
color:var(--muted);text-align:left;padding:7px 11px;border-bottom:1px solid var(--line)}
td{padding:6px 11px;border-bottom:1px solid var(--line);vertical-align:top;
font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
td.n{font-family:var(--mono);text-align:right;white-space:nowrap}
td.mono{font-family:var(--mono);white-space:nowrap}
.tw{overflow-x:auto}
.up{color:var(--green)}.down{color:var(--red)}
.empty{color:var(--muted);font-size:12.5px;font-style:italic}
footer{margin-top:40px;border-top:1px solid var(--line);padding-top:10px;
font-family:var(--mono);font-size:10.5px;color:var(--muted);display:flex;
flex-wrap:wrap;gap:6px 18px}
"""


def _table(headers: list[str], rows: list[list[str]], empty: str) -> str:
    if not rows:
        return f'<p class="empty">{_esc(empty)}</p>'
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(cells) + "</tr>" for cells in rows)
    return f'<div class="tw"><table><tr>{head}</tr>{body}</table></div>'


def render_brief(pass_name: str, data: dict, root: Path = ROOT) -> Path:
    """Render one pass's brief. `data` is assembled by the pass; see
    passes/premarket.py and passes/close.py for the exact shapes."""
    provisional = pass_name == "close"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Banners STACK (2026-07-28 review fix): degradation must never replace
    # the law-2 regime marker — a reader of the worst runs still needs to
    # know which regime they are looking at.
    if provisional:
        banner = ('<div class="banner provisional">PROVISIONAL — latest snapshots; '
                  'NOTHING here is actionable until it settles next session (law 2)</div>')
    else:
        banner = '<div class="banner settled">SETTLED BASIS — adjudicated verdicts of record</div>'
    if data.get("degraded"):
        banner += '<div class="banner degraded">DEGRADED RUN — fetches failed; numbers below may be stale</div>'

    sections: list[str] = []

    # Wires — every verdict carries its row's session date (law 3: the
    # number's date is provenance, never dropped).
    verdicts = data.get("verdicts") or []
    stale_dates = data.get("stale") or {}   # ticker -> stale snapshot date
    rows = []
    for v in verdicts:
        if v["fired"] is True:
            state = ('<span class="pill wait">WOULD FIRE — settles next session</span>'
                     if provisional else '<span class="pill bad">FIRED → consult open</span>')
        elif v["fired"] is None:
            state = '<span class="pill wait">BLOCKED</span>'
        else:
            state = '<span class="pill ok">quiet</span>'
        date_cell = _esc(v.get("row_date") or "—")
        if v.get("ticker") in stale_dates:
            date_cell += ' <span class="pill bad">STALE</span>'
        rows.append([f'<td class="mono">{_esc(v["wire_id"])}</td>',
                     f'<td class="mono">{_esc(v["ticker"])}</td>',
                     f'<td class="n">{_fmt(v.get("close"))}</td>',
                     f'<td class="mono">{date_cell}</td>',
                     f'<td>{state}</td>',
                     f'<td>{_esc(v.get("reason"))}</td>'])
    sections.append("<h2>Wires</h2>" + _table(
        ["wire", "ticker", "close", "session", "state", "reason"], rows,
        "no armed wires evaluated"))

    # Moves (close brief) — snapshot vs last settled, snapshot DATED and
    # stale prints marked (2026-07-28 review fix: an old snapshot rendered
    # undated under a "today" header — a session claim for a non-session day).
    if provisional:
        rows = []
        for m in data.get("moves") or []:
            pct = m.get("pct")
            cls = "up" if (pct or 0) >= 0 else "down"
            snap_cell = (f'{_fmt(m.get("snap_close"))} '
                         f'<span style="color:var(--muted)">({_esc(m.get("snap_date") or "—")})</span>')
            if m.get("stale"):
                snap_cell += ' <span class="pill bad">STALE</span>'
            rows.append([f'<td class="mono">{_esc(m["ticker"])}</td>',
                         f'<td class="n">{_fmt(m.get("settled_close"))} <span style="color:var(--muted)">({_esc(m.get("settled_date") or "—")})</span></td>',
                         f'<td class="n">{snap_cell}</td>',
                         f'<td class="n {cls}">{"" if pct is None else f"{pct:+.1%}"}</td>'])
        sections.append("<h2>Latest tape — provisional vs last settled</h2>" + _table(
            ["ticker", "last settled", "snapshot (session)", "move"], rows,
            "no snapshots on file"))

    # Monitors — ABSENT keys mean "not evaluated", never "nothing flagged"
    # (2026-07-28 review fix: the close brief claimed a clean bill for
    # checks it never ran).
    if "euphoria" in data or "parabola" in data:
        monitors = []
        for f in data.get("euphoria") or []:
            monitors.append([f'<td class="mono">{_esc(f["ticker"])}</td>',
                             '<td><span class="pill bad">EUPHORIA ≥2× cost</span></td>',
                             f'<td>{_fmt(f.get("multiple"))}× — consult: {_esc(f.get("consult") or "—")}</td>'])
        for f in data.get("parabola") or []:
            monitors.append([f'<td class="mono">{_esc(f["ticker"])}</td>',
                             '<td><span class="pill wait">ANTI-PARABOLA</span></td>',
                             f'<td>+{f.get("gain", 0):.0%} vs {_esc(f.get("from_date"))} — {_esc(f.get("note"))}</td>'])
        sections.append("<h2>Charter §V monitors</h2>" + _table(
            ["ticker", "screen", "detail"], monitors, "nothing flagged"))
    else:
        sections.append('<h2>Charter §V monitors</h2><p class="empty">'
                        'not evaluated in this pass — settled-basis monitors '
                        'run in the premarket pass</p>')

    # Book
    book = data.get("book") or {}
    t = book.get("totals") or {}
    fl = book.get("floor") or {}
    rows = []
    for s in book.get("seats") or []:
        rows.append([f'<td class="mono">{_esc(s["ticker"])}</td>',
                     f'<td class="n">{_fmt(s.get("shares"), 0)}</td>',
                     f'<td class="n">{_fmt(s.get("close"))} <span style="color:var(--muted)">({_esc(s.get("close_date"))})</span></td>',
                     f'<td class="mono">{_esc(s.get("source") or "—")}</td>',
                     f'<td class="n">{_fmt(s.get("value_usd"))}</td>'])
    for g in book.get("gaps") or []:
        rows.append([f'<td class="mono">{_esc(g["ticker"])}</td>',
                     '<td colspan="3"><span class="pill wait">GAP</span></td>',
                     f'<td>{_esc(g.get("reason"))}</td>'])
    incomplete = ' <span class="pill wait">INCOMPLETE</span>' if t.get("incomplete") else ""
    sections.append(
        f"<h2>Book — settled basis</h2>"
        f'<div class="stats"><div class="stat"><b>${_fmt(t.get("usd"))}</b>'
        f'<span>book value{incomplete}</span></div>'
        f'<div class="stat"><b>${_fmt(fl.get("amount"))}</b>'
        f'<span>floor — outside the book, never counted</span></div></div>'
        + _table(["seat", "shares", "close", "source", "value usd"], rows, "no seats"))

    # Imported research freshness (supremacy clause): visible daily, so aging
    # evidence is noticed before a wire fires on top of it.
    if data.get("evidence") is not None:
        rows = []
        for e in data["evidence"]:
            age = e.get("age_days")
            pill = ('<span class="pill bad">STALE</span>' if e.get("stale")
                    else '<span class="pill ok">fresh</span>')
            rows.append([f'<td class="mono">{_esc(e["ticker"])}</td>',
                         f'<td class="mono">{_esc(e.get("as_of") or "undated")}</td>',
                         f'<td class="n">{"—" if age is None else age}</td>',
                         f'<td>{pill}</td>',
                         f'<td>{_esc(e.get("source") or "—")}</td>'])
        sections.append("<h2>Imported research — evidence only, never a verdict</h2>"
                        + _table(["ticker", "as of", "age (d)", "state", "source"],
                                 rows, "no research files on file"))

    # Catalysts — None means the FILE was unreadable, not an empty schedule.
    cats = data.get("catalysts")
    if cats is None:
        sections.append('<h2>Catalysts — next 30 days</h2><p class="empty">'
                        'catalysts.yaml unreadable or missing — see degradations</p>')
    else:
        rows = [[f'<td class="mono">{_esc(c["date"])}</td>',
                 f'<td class="mono">{_esc(c["ticker"])}</td>',
                 f'<td>{_esc(c["what"])}</td>'] for c in cats]
        sections.append("<h2>Catalysts — next 30 days</h2>" + _table(
            ["date", "ticker", "what"], rows, "none scheduled"))

    # Degradations / warnings
    warn_rows = [[f'<td>{_esc(w)}</td>'] for w in data.get("warnings") or []]
    if warn_rows:
        sections.append("<h2>Degradations — declared, per law 3</h2>"
                        + _table(["warning"], warn_rows, ""))

    title = "After-market brief" if provisional else "Premarket brief"
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} · {ts}</title><style>{_CSS}</style></head><body>
<div class="wrap">
<header class="mast">
  <span class="eyebrow">The Portfolio Machine · analyzes, never advises, never trades</span>
  <h1>{_esc(title)}</h1>
  <span class="when">{ts}</span>
</header>
{banner}
{"".join(sections)}
<footer><span>pass: {_esc(pass_name)}</span><span>generated by passes/{_esc(pass_name)}.py</span>
<span>append-only log: data/log.jsonl</span></footer>
</div></body></html>"""

    path = out_dir(root) / f"{pass_name}.html"
    path.write_text(doc, encoding="utf-8")
    return path
