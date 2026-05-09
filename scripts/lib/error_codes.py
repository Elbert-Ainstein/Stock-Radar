"""
error_codes.py — Stock Radar error code registry.

Why this exists: silent failures in standalone scout runs, RLS-empty inserts,
schema drift on outcome rows, and provider unit bugs all looked the same to
a user reading a log — generic exceptions or "no rows" messages with no
breadcrumb. With error codes, every loud failure mode gets a stable string
like `[SR-SCOUT-002]` that can be grepped in logs, looked up in this
registry, and traced to a fix.

Usage:

    from lib.error_codes import fail, warn

    fail("SR-INSIDER-001", "discovery_universe query returned 0 rows")
    # raises RuntimeError("[SR-INSIDER-001] discovery_universe query returned 0 rows")

    warn("SR-FEEDER-001", f"zero overlap between 13F and {scout_name}")
    # prints "[SR-FEEDER-001] zero overlap..." to stderr

CLI lookup:

    python scripts/lib/error_codes.py SR-SCOUT-002
    # prints the cause + file:function it's raised from
"""
from __future__ import annotations

import sys
from typing import Type

# (code → (cause, file_or_function))
# When you add a new code in the wild, ALSO add it here. Without the registry
# entry the lookup CLI returns "unknown code" but the raise/warn still works.
REGISTRY: dict[str, tuple[str, str]] = {
    # ── SCOUT — pipeline / scout-runner failures ──
    "SR-SCOUT-001": (
        "Scout completed but produced zero signal rows.",
        "scripts/scout_*.py:main",
    ),
    "SR-SCOUT-002": (
        "Scout output written to local JSON only; Supabase ingestion not invoked. "
        "Run scripts/ingest_scout_jsons.py to push to DB. Root cause: get_run_id() "
        "returned None for standalone scout invocation.",
        "scripts/utils.py:save_signals",
    ),
    "SR-INSIDER-001": (
        "scout_insider --source discovery: discovery_universe query returned 0 US "
        "tickers. Check Supabase auth + status filter ('exploring,promising,qualified,"
        "watchlisted') + ticker filtering ('.' suffix excluded as non-US).",
        "scripts/scout_insider.py:_load_tickers_from_discovery",
    ),
    "SR-INSIDER-002": (
        "Form-4 transaction-code parsing gap: every kind=unknown, buys=0, sells=0. "
        "Scout fetches accessions but doesn't parse XML transaction codes. Tracked as "
        "Task #69. Until fixed, feed_insider_to_universe uses transaction_count>=1 "
        "as a coarse proxy.",
        "scripts/scout_insider.py:analyze_insider_activity",
    ),

    # ── FEEDER — Module 11b feeder pipeline ──
    "SR-FEEDER-001": (
        "Diagnostic warning: zero overlap between 13F-tagged tickers and the upstream "
        "scout's universe. Likely the scout was run with default --source watchlist "
        "instead of --source discovery. Re-run the scout, then re-run this feeder.",
        "scripts/feed_*_to_universe.py:diagnose_overlap_with_13f",
    ),

    # ── FINDATA — Module 1 data-acquisition layer ──
    "SR-FINDATA-001": (
        "Provider returned implausible market cap (>$1T for a non-mega-cap ticker). "
        "Likely a units bug (EODHD has been observed reporting in cents instead of "
        "dollars for some tickers). Falling back to yfinance.",
        "scripts/finance_data.py:_validate_market_cap",
    ),
    "SR-FINDATA-002": (
        "Recent quarter sanity check failed: revenue >2x trailing-avg (small/mid) or "
        ">2.5x YoY (large-cap). Hard-fail to prevent corrupt data from feeding the "
        "thesis. Override with override_suspect_recent=True if the jump is verified "
        "real (e.g. SNDK post-spinoff).",
        "scripts/finance_data.py:_validate_and_build",
    ),

    # ── CONVERGE — Module 11a convergence detector ──
    "SR-CONVERGE-001": (
        "discovery_universe query returned 0 rows for the requested status filter. "
        "Either the table is empty or the status values are wrong (default: "
        "exploring,promising,qualified). Check 'python scripts/discovery_13f.py' "
        "has been run.",
        "scripts/convergence_detector.py:detect_convergence",
    ),
    "SR-CONVERGE-API-001": (
        "Supabase query failed in /api/convergence GET. Network or RLS issue. Check "
        "SUPABASE_URL + SUPABASE_ANON_KEY env vars + RLS policy on discovery_universe.",
        "app/api/convergence/route.ts:GET",
    ),
    "SR-CONVERGE-API-002": (
        "Supabase client init failed in /api/convergence. Env vars missing.",
        "app/api/convergence/route.ts:GET",
    ),

    # ── OUTCOME — Module 8 thesis outcome tracker ──
    "SR-OUTCOME-001": (
        "thesis_outcomes row exists but expected schema columns missing. Schema drift "
        "suspected — the theses table column was renamed/removed without updating "
        "outcome tracker queries. Check migrations under supabase/.",
        "scripts/lib/outcomes.py:log_thesis_outcome",
    ),

    # ── THESIS — Module 5 thesis pipeline ──
    "SR-THESIS-001": (
        "write_to_supabase returned None on a successful-looking insert. Likely RLS "
        "denies SELECT on the inserted row, so PostgREST returned empty data. The "
        "thesis row exists in the DB, but we have no thesis_id, so outcome tracking "
        "is silently skipped for this run. Fix: ensure RLS allows the insert role to "
        "SELECT its own writes, OR run the inserter with service-role key.",
        "scripts/run_thesis.py:write_to_supabase",
    ),
    "SR-THESIS-002": (
        "Inserted theses row missing 'id' field. Schema drift suspected — column "
        "renamed/removed in a migration not applied uniformly.",
        "scripts/run_thesis.py:write_to_supabase",
    ),
}


def explain(code: str) -> str:
    """Format a registry entry for display."""
    if code in REGISTRY:
        cause, location = REGISTRY[code]
        return f"\n[{code}] {cause}\n  in: {location}\n"
    return f"\n[{code}] (unknown code — add it to scripts/lib/error_codes.py REGISTRY)\n"


def fail(code: str, detail: str = "", exc_class: Type[Exception] = RuntimeError) -> None:
    """Raise an exception with the [SR-XXX] code prefixed onto the message."""
    if detail:
        msg = f"[{code}] {detail}"
    else:
        cause = REGISTRY.get(code, ("(unknown)", ""))[0]
        msg = f"[{code}] {cause}"
    raise exc_class(msg)


def warn(code: str, detail: str = "", to_stream=sys.stderr) -> None:
    """Print a [SR-XXX]-prefixed warning to stderr (or another stream)."""
    if detail:
        msg = f"[{code}] {detail}"
    else:
        cause = REGISTRY.get(code, ("(unknown)", ""))[0]
        msg = f"[{code}] {cause}"
    print(msg, file=to_stream, flush=True)


def list_all() -> str:
    """Pretty-printed list of every registered code."""
    out = []
    out.append(f"{'CODE':<22} CAUSE")
    out.append(f"{'-'*22} {'-'*60}")
    for code in sorted(REGISTRY):
        cause = REGISTRY[code][0]
        out.append(f"{code:<22} {cause[:80]}")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(explain(sys.argv[1]))
    else:
        print(list_all())
