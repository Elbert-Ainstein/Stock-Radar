#!/usr/bin/env python3
"""
discovery_screens.py — Lesson L2, first slice: S1 + S3 → STALK.

Discovery and allocation are different machines. The allocation gate
(trade_gate) clamps hard and stays untouched. DISCOVERY mode runs the
signature screens and emits a **STALK** — a stance with a stored
trigger_price, never a sized position:

  S1 — anomalies that survive verification (the MU/EDGAR lesson as code):
       a revenue sanity-check firing that the EDGAR XBRL cross-check then
       CONFIRMS is a *signal* of regime change, not a data error.
  S3 — smart money before analysts: 13F adds (gen-2's differ,
       discovery_13f.py) on a name with zero/negative analyst coverage.

STALK discipline (docs/design/HORIZON_DISCOVERY_TYPEA_2026-07-02.md):
  - `stance` + `trigger_price` are NEW fields on discovery_universe
    (supabase/2026-07-08_discovery_stalk.sql) — NEVER a value of
    `conviction` (the kill gate, UI pills, and outcomes seeding all
    pattern-match on conviction).
  - Every STALK is SEALED into prediction_log (L8: discovery hits get
    sealed too, or they never earn trust) with run_id prefix `stalk-` and
    NO reasoning_fingerprint — run_checkpoint.is_gradeable_seal therefore
    classifies it `not_socratic` and the calibration loop is untouched.
    The record is append-only evidence for a future stalk-grader.
  - The screens are diagnostic; nothing here sizes a position. The
    allocation gate may simultaneously (correctly) refuse the same name.

Trigger price: taken from evidence, never invented — the latest thesis's
actionability price (risk_adj_target / scaled LOW bound, i.e. the price at
which the trade gate would stop saying BROKEN) when a thesis exists, else an
explicit operator --trigger. No derivable trigger → STALK is still recorded,
with trigger_price NULL and that fact stated (L4).

Usage:
    python scripts/discovery_screens.py SNDK                # live screens
    python scripts/discovery_screens.py SNDK --trigger 38.5 # operator trigger
    python scripts/discovery_screens.py SNDK --dry-run      # no writes
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import load_env  # noqa: E402

load_env()

from run_parameters import _as_num, _low_bound_at  # noqa: E402
from trade_gate import DEFAULT_HORIZON_YEARS  # noqa: E402

STALK_RUN_PREFIX = "stalk-"

# S1 warning markers, as emitted by finance_data's revenue sanity check.
_S1_MARKERS = ("TRAJECTORY ANOMALY", "SUSPECT DATA")
# finance_data is FAIL-OPEN when EDGAR itself is unreachable (no CIK, foreign
# filer, network failure): the fetch succeeds, anomalies intact, with this
# marker appended. That is an anomaly that was NEVER verified — S1 must not
# claim survival (review finding, 2026-07-08).
_EDGAR_UNAVAILABLE_MARKER = "EDGAR cross-check unavailable"

# S3: "zero or negative coverage" — at or below this many covering analysts.
S3_MAX_COVERAGE = 2


# ─── Screens (pure) ──────────────────────────────────────────────────

def screen_s1(warnings: list[str], fetch_succeeded: bool = True) -> Optional[dict]:
    """S1 — anomaly that survived verification.

    `warnings` is FinancialData.warnings from a SUCCESSFUL fetch_financials
    (success means the EDGAR XBRL hard gate passed — a failed fetch never
    reaches this screen). A sanity-check marker inside a successful fetch is
    the SNDK/MU shape: the print looked impossible and the SEC confirmed it.
    """
    if not fetch_succeeded:
        return None
    if any(_EDGAR_UNAVAILABLE_MARKER in w for w in (warnings or [])):
        return None  # EDGAR never ran — the anomaly survived nothing
    hits = [w for w in (warnings or []) if any(m in w for m in _S1_MARKERS)]
    if not hits:
        return None
    return {
        "screen": "S1",
        "summary": "revenue anomaly fired and survived EDGAR XBRL verification",
        "evidence": [h[:300] for h in hits[:6]],
    }


def parse_13f_source_tags(source: Optional[str]) -> list[dict]:
    """Parse gen-2's REAL artifact: discovery_13f.upsert_candidate writes
    `discovery_universe.source` as a comma-joined STRING of tags like
    '13f_druckenmiller_2026Q1_new_position' — not structured rows (review
    finding, 2026-07-08: the first cut of this module read a `sources` jsonb
    column that has never existed, so S3 could never fire live)."""
    adds = []
    for tag in str(source or "").split(","):
        tag = tag.strip()
        if not tag.lower().startswith("13f_"):
            continue
        parts = tag.split("_")
        adds.append({
            "manager": parts[1] if len(parts) > 1 else "?",
            "quarter": parts[2] if len(parts) > 2 else "?",
            "kind": "_".join(parts[3:]) or "add",
            "tag": tag,
        })
    return adds


def screen_s3(adds: list[dict], analyst_coverage: Optional[int]) -> Optional[dict]:
    """S3 — smart money before analysts.

    `adds` are 13F positions for this ticker (parse_13f_source_tags output,
    or any dicts with manager/kind); `analyst_coverage` is the number of
    covering analysts (None = unknown — conservatively NOT a pass; unknown
    coverage is not zero coverage).
    """
    if not adds or analyst_coverage is None or analyst_coverage > S3_MAX_COVERAGE:
        return None
    return {
        "screen": "S3",
        "summary": f"{len(adds)} 13F add(s) with analyst coverage {analyst_coverage} "
                   f"(≤ {S3_MAX_COVERAGE})",
        "evidence": [
            f"{a.get('manager', '?')}: {a.get('kind', 'add')}"
            + (f" ({a['tag']})" if a.get("tag") else "")
            for a in adds[:6]
        ],
    }


def derive_trigger_price(*, thesis_row: Optional[dict] = None,
                         operator_trigger: Optional[float] = None) -> tuple[Optional[float], str]:
    """Trigger from evidence, never invented. Precedence:
    operator-supplied > thesis actionability price > None (stated).

    Thesis actionability price = risk_adj_target / LOW-band lower bound on
    the thesis's own clock — the spot at which the trade gate would stop
    clamping to BROKEN. (Design rule 1: no reverse-engineered prices — this
    is the gate's own algebra applied to the thesis's own target.)
    """
    op = _as_num(operator_trigger)
    if op and op > 0:
        return round(op, 2), "operator"
    if thesis_row:
        rat = _as_num(thesis_row.get("risk_adj_target"))
        h = _as_num(thesis_row.get("thesis_horizon_years")) or DEFAULT_HORIZON_YEARS
        if rat and rat > 0:
            return round(rat / _low_bound_at(h), 2), "thesis_actionability"
    return None, "none_derivable"


def assemble_stalk(ticker: str, *, screens: list[dict], spot: Optional[float],
                   trigger_price: Optional[float], trigger_source: str,
                   now: Optional[datetime] = None) -> Optional[dict]:
    """Combine screen results into a STALK object (or None if no screen hit).

    First slice requires at least ONE passing screen; the S1+S3 double-hit
    (the SNDK-at-$38.50 shape) is recorded as such in the evidence.
    """
    if not screens:
        return None
    now = now or datetime.now(timezone.utc)
    return {
        "ticker": ticker.upper(),
        "stance": "STALK",
        "trigger_price": trigger_price,
        "trigger_source": trigger_source,
        "spot_at_emission": spot,
        "screens_passed": [s["screen"] for s in screens],
        "evidence": screens,
        "emitted_at": now.isoformat(),
    }


def stalk_seal_row(stalk: dict) -> dict:
    """prediction_log row for a STALK emission (L8: sealed, or it never earns
    trust). run_id prefix `stalk-` + NO reasoning_fingerprint → the checkpoint
    grader's is_gradeable_seal returns not_socratic and skips it; the record
    is append-only evidence for a future stalk-grader.

    The evidence payload rides in `context_inputs` — a column that BOTH
    exists on prediction_log AND survives prediction_logger._coerce_row's
    key whitelist (review finding, 2026-07-08: a `notes` key was silently
    dropped client-side, leaving the seal evidence-free).

    Semantics: 'this name becomes attractive at trigger_price'. target_base
    carries the trigger; current_price the emission spot. Both may be None —
    which also keeps the row ungradeable via the zero_ref_price guard.
    """
    ts = str(stalk["emitted_at"]).replace(":", "").replace("-", "")[:15]
    return {
        "ticker": stalk["ticker"],
        "run_id": f"{STALK_RUN_PREFIX}{stalk['ticker'].lower()}-{ts}",
        "current_price": stalk.get("spot_at_emission"),
        "target_base": stalk.get("trigger_price"),
        "context_inputs": {
            "kind": "stalk_emission",
            "screens_passed": stalk["screens_passed"],
            "trigger_source": stalk["trigger_source"],
            "evidence": stalk["evidence"],
        },
    }


def check_trigger_breach(stalk_rows: list[dict], quotes: dict[str, float]) -> list[dict]:
    """Pure: which STALK rows' triggers are breached by current quotes
    (quote <= trigger_price). Used by refresh_prices (L5: alerts —
    watchlist → pending orders, not sentiment)."""
    breaches = []
    for row in stalk_rows:
        t = str(row.get("ticker") or "")
        trig = _as_num(row.get("trigger_price"))
        px = _as_num(quotes.get(t))
        if t and trig and px and px <= trig:
            breaches.append({"ticker": t, "trigger_price": trig, "price": px})
    return breaches


# ─── Live wiring ─────────────────────────────────────────────────────

def _latest_thesis(sb, ticker: str) -> Optional[dict]:
    try:
        res = (sb.table("theses")
               .select("ticker,run_at,risk_adj_target,thesis_horizon_years,buy_below")
               .eq("ticker", ticker.upper())
               .order("run_at", desc=True).limit(1).execute())
        return (res.data or [None])[0]
    except Exception as e:
        print(f"  [screens] thesis lookup failed ({e}) — no thesis trigger", file=sys.stderr)
        return None


def _s3_adds_from_universe(sb, ticker: str) -> list[dict]:
    """13F adds for this ticker from gen-2's REAL artifact: the singular
    `source` tag-string column that discovery_13f.upsert_candidate maintains.
    Failures are STATED, not silent (L4)."""
    try:
        res = (sb.table("discovery_universe")
               .select("ticker,source,status")
               .eq("ticker", ticker.upper()).limit(1).execute())
        row = (res.data or [None])[0]
    except Exception as e:
        print(f"  [S3] discovery_universe lookup failed ({e}) — no 13F evidence",
              file=sys.stderr)
        return []
    return parse_13f_source_tags((row or {}).get("source"))


def run_screens(ticker: str, *, operator_trigger: Optional[float] = None,
                operator_coverage: Optional[int] = None,
                dry_run: bool = False) -> Optional[dict]:
    ticker = ticker.upper()
    print(f"\n=== discovery_screens: {ticker} ===", flush=True)

    # S1 — needs a live fetch; a fetch FAILURE means EDGAR rejected or data
    # is unusable: no verification survival, no screen.
    s1 = None
    spot = None
    try:
        from finance_data import fetch_financials
        fin = fetch_financials(ticker)
        spot = _as_num(getattr(fin, "price", None))
        s1 = screen_s1(getattr(fin, "warnings", []) or [], fetch_succeeded=True)
    except Exception as e:
        print(f"  [S1] no pass — fetch failed/rejected: {str(e)[:140]}", flush=True)

    from supabase_helper import get_client
    sb = get_client()

    # S3 coverage: NO live analyst-coverage source is wired yet — the operator
    # supplies it (--coverage). Stated, not silent (L4): 13F adds without a
    # coverage number cannot pass.
    adds = _s3_adds_from_universe(sb, ticker)
    s3 = screen_s3(adds, operator_coverage)
    if adds and operator_coverage is None:
        print(f"  [S3] {len(adds)} 13F add(s) found but no coverage source is "
              f"wired — pass --coverage N to evaluate S3", flush=True)

    screens = [s for s in (s1, s3) if s]
    for s in (("S1", s1), ("S3", s3)):
        print(f"  [{s[0]}] {'PASS — ' + s[1]['summary'] if s[1] else 'no pass'}", flush=True)
    if not screens:
        print("  no screen passed — no STALK emitted", flush=True)
        return None

    thesis = _latest_thesis(sb, ticker)
    trigger, source = derive_trigger_price(thesis_row=thesis,
                                           operator_trigger=operator_trigger)
    stalk = assemble_stalk(ticker, screens=screens, spot=spot,
                           trigger_price=trigger, trigger_source=source)
    print(f"  STALK: screens={stalk['screens_passed']} trigger={trigger} "
          f"({source}) spot={spot}", flush=True)
    if trigger is None:
        print("  [screens] no trigger derivable (no thesis, no --trigger) — "
              "STALK recorded without an alert level (stated, not silent)", flush=True)

    if dry_run:
        print("  [DRY RUN] no writes", flush=True)
        return stalk

    # Persist stance on discovery_universe. UPDATE-first: an upsert's insert
    # tuple would trip the table's NOT NULL market/source columns even when
    # the row exists (review finding, 2026-07-08). New names get a full
    # insert that satisfies the base schema.
    try:
        payload = {
            "stance": "STALK",
            "trigger_price": trigger,
            "stalk_evidence": stalk["evidence"],
            "stalk_updated_at": stalk["emitted_at"],
        }
        upd = sb.table("discovery_universe").update(payload).eq("ticker", ticker).execute()
        if not (upd.data or []):
            market = ticker.split(".")[-1] if "." in ticker else "US"
            sb.table("discovery_universe").insert({
                "ticker": ticker,
                "market": market,
                "source": "discovery_screens_" + "_".join(stalk["screens_passed"]).lower(),
                "status": "exploring",
                **payload,
            }).execute()
        print("  persisted stance=STALK on discovery_universe", flush=True)
    except Exception as e:
        print(f"  [screens] WARN: discovery_universe write failed — {e} "
              f"(apply supabase/2026-07-08_discovery_stalk.sql?)", file=sys.stderr, flush=True)

    # Seal (append-only; ungradeable by construction — see stalk_seal_row).
    try:
        from prediction_logger import log_prediction
        row = stalk_seal_row(stalk)
        log_prediction(ticker, row)
        print(f"  sealed {row['run_id']} into prediction_log (not gradeable "
              f"by the socratic grader — by design)", flush=True)
    except Exception as e:
        print(f"  [screens] WARN: seal failed — {e}", file=sys.stderr, flush=True)
    return stalk


def main() -> None:
    ap = argparse.ArgumentParser(description="L2 discovery screens (S1+S3) → STALK")
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--trigger", type=float, default=None,
                    help="operator trigger price (used when no thesis exists)")
    ap.add_argument("--coverage", type=int, default=None,
                    help="analyst coverage count for S3 (no live source is "
                         "wired yet — unknown coverage never passes)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    emitted = 0
    for t in args.tickers:
        if run_screens(t, operator_trigger=args.trigger,
                       operator_coverage=args.coverage, dry_run=args.dry_run):
            emitted += 1
    print(f"\n{emitted}/{len(args.tickers)} name(s) emitted a STALK")


if __name__ == "__main__":
    main()
