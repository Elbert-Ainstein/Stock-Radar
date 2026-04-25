"""
supabase_helper.py — Supabase read/write helpers for Stock Radar scouts & analyst.
Replaces all JSON file I/O with Supabase Postgres calls.
"""

import os, json, uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root. Use override=False to respect already-set env
# vars (e.g. runtime overrides, Docker env). This aligns with utils.load_env()
# which also preserves existing vars. Previous override=True was a bug that
# clobbered intentional runtime env vars on import.
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, override=False)

from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")

_client: Client | None = None


def get_client() -> Client:
    """Lazy-init Supabase client."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY not set in .env")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ── Watchlist (stocks table) ──────────────────────────────────────

def load_watchlist() -> list[dict]:
    """Return all active stocks from DB (replaces watchlist.json read)."""
    sb = get_client()
    resp = sb.table("stocks").select("*").eq("active", True).execute()
    return resp.data or []


def get_stock(ticker: str) -> dict | None:
    """Return a single stock row by ticker."""
    sb = get_client()
    resp = sb.table("stocks").select("*").eq("ticker", ticker).maybe_single().execute()
    return resp.data


def upsert_stock(stock: dict) -> dict:
    """Insert or update a stock row. Uses ticker as the conflict key."""
    sb = get_client()
    resp = sb.table("stocks").upsert(stock, on_conflict="ticker").execute()
    return resp.data[0] if resp.data else {}


def delete_stock(ticker: str) -> bool:
    """Soft-delete a stock (set active=false)."""
    sb = get_client()
    resp = sb.table("stocks").update({"active": False}).eq("ticker", ticker).execute()
    return bool(resp.data)


def hard_delete_stock(ticker: str) -> bool:
    """Permanently remove a stock row."""
    sb = get_client()
    resp = sb.table("stocks").delete().eq("ticker", ticker).execute()
    return bool(resp.data)


# ── Signals ───────────────────────────────────────────────────────

def save_signal(signal: dict) -> dict:
    """Insert a single signal row."""
    sb = get_client()
    resp = sb.table("signals").insert(signal).execute()
    return resp.data[0] if resp.data else {}


def save_signals_batch(signals: list[dict]) -> list[dict]:
    """Insert multiple signal rows in one call."""
    if not signals:
        return []
    sb = get_client()
    resp = sb.table("signals").insert(signals).execute()
    return resp.data or []


def load_latest_signals(ticker: str | None = None) -> list[dict]:
    """Load latest signals per ticker per scout.
    If ticker given, filter to that stock only."""
    sb = get_client()
    q = sb.table("latest_signals").select("*")
    if ticker:
        q = q.eq("ticker", ticker)
    resp = q.execute()
    return resp.data or []


def load_signals_for_run(run_id: str) -> list[dict]:
    """Load all signals from a specific pipeline run."""
    sb = get_client()
    resp = sb.table("signals").select("*").eq("run_id", run_id).execute()
    return resp.data or []


# ── Analysis ──────────────────────────────────────────────────────

def save_analysis(row: dict) -> dict:
    """Upsert an analysis row (unique on ticker + run_id)."""
    sb = get_client()
    resp = sb.table("analysis").upsert(row, on_conflict="ticker,run_id").execute()
    return resp.data[0] if resp.data else {}


def load_latest_analysis() -> list[dict]:
    """Load the most recent analysis per stock."""
    sb = get_client()
    resp = sb.table("latest_analysis").select("*").execute()
    return resp.data or []


def load_analysis_for_ticker(ticker: str) -> dict | None:
    """Load latest analysis for a single stock."""
    sb = get_client()
    resp = (
        sb.table("latest_analysis")
        .select("*")
        .eq("ticker", ticker)
        .maybe_single()
        .execute()
    )
    return resp.data


# ── Pipeline Runs ─────────────────────────────────────────────────

def generate_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


def start_pipeline_run(run_id: str, scouts_active: list[str], free_only: bool = False) -> dict:
    """Record a new pipeline run as started."""
    sb = get_client()
    row = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "free_only": free_only,
        "scouts_active": scouts_active,
        "stock_count": 0,
    }
    resp = sb.table("pipeline_runs").insert(row).execute()
    return resp.data[0] if resp.data else {}


def complete_pipeline_run(
    run_id: str,
    success: bool,
    stock_count: int = 0,
    scout_details: dict | None = None,
    error: str | None = None,
    log_tail: str | None = None,
    duration_s: float | None = None,
) -> dict:
    """Mark a pipeline run as completed."""
    sb = get_client()
    update = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "stock_count": stock_count,
        "error": error,
        "log_tail": log_tail,
        "duration_s": duration_s,
    }
    if scout_details:
        update["scout_details"] = scout_details
    resp = sb.table("pipeline_runs").update(update).eq("run_id", run_id).execute()
    return resp.data[0] if resp.data else {}


def load_latest_run() -> dict | None:
    """Get the most recent pipeline run."""
    sb = get_client()
    resp = (
        sb.table("pipeline_runs")
        .select("*")
        .order("started_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return resp.data


# ── Migration helper: seed from JSON ─────────────────────────────

def seed_stocks_from_watchlist(watchlist_path: str) -> int:
    """One-time: read watchlist.json and insert all stocks into Supabase."""
    with open(watchlist_path, "r") as f:
        wl = json.load(f)

    rows = []
    for entry in wl.get("watchlist", wl.get("stocks", [])):
        target = entry.get("target", {})
        row = {
            "ticker": entry["ticker"],
            "name": entry["name"],
            "sector": entry.get("sector", ""),
            "thesis": entry.get("thesis", ""),
            "kill_condition": entry.get("kill_condition", ""),
            "tags": entry.get("tags", []),
            "target_price": target.get("price"),
            "timeline_years": target.get("timeline_years", 3),
            "valuation_method": target.get("valuation_method", "pe"),
            "target_multiple": target.get("target_multiple"),
            "target_notes": target.get("notes", ""),
            "model_defaults": target.get("model_defaults", {}),
            "scenarios": target.get("scenarios", {}),
            "criteria": entry.get("criteria", []),
            "active": True,
        }
        rows.append(row)

    if not rows:
        return 0

    sb = get_client()
    resp = sb.table("stocks").upsert(rows, on_conflict="ticker").execute()
    return len(resp.data) if resp.data else 0


# ── Schema Validation ────────────────────────────────────────────

# Expected columns per table — the code writes these fields and will
# silently drop data if they're missing.  Run validate_schema() at
# pipeline startup to catch drift early.
EXPECTED_SCHEMA = {
    "stocks": [
        "ticker", "name", "sector", "thesis", "kill_condition", "tags",
        "target_price", "timeline_years", "valuation_method", "target_multiple",
        "target_notes", "model_defaults", "scenarios", "criteria",
        "archetype", "research_cache", "active", "added_at", "updated_at",
    ],
    "signals": [
        "ticker", "scout", "signal", "ai", "summary", "data", "scores",
        "run_id", "created_at",
    ],
    "analysis": [
        "ticker", "composite_score", "overall_signal", "convergence",
        "scores", "valuation", "auto_tiers", "alerts", "criteria_eval",
        "event_impacts", "fundamentals", "price_data", "run_id", "created_at",
    ],
    "pipeline_runs": [
        "run_id", "started_at", "completed_at", "success", "free_only",
        "scouts_active", "scout_details", "stock_count", "error", "log_tail",
        "duration_s",
    ],
    "archetype_history": [
        "ticker", "archetype", "secondary", "justification", "created_at",
    ],
}


def validate_schema(verbose: bool = True) -> dict[str, list[str]]:
    """Check that all expected columns exist in Supabase.

    Returns a dict of {table: [missing_columns]}.  Empty dict = all good.
    Uses a lightweight probe: SELECT a single row and check the returned keys.
    For empty tables, attempts an INSERT+rollback-style probe via column listing.
    """
    sb = get_client()
    missing: dict[str, list[str]] = {}

    for table, expected_cols in EXPECTED_SCHEMA.items():
        try:
            # Fetch one row to see which columns come back
            resp = sb.table(table).select("*").limit(1).execute()
            if resp.data:
                actual_cols = set(resp.data[0].keys())
            else:
                # Empty table — try selecting all expected columns explicitly
                col_list = ",".join(expected_cols)
                try:
                    sb.table(table).select(col_list).limit(1).execute()
                    actual_cols = set(expected_cols)  # All columns exist
                except Exception:
                    actual_cols = set()  # Table may not exist

            table_missing = [c for c in expected_cols if c not in actual_cols]
            if table_missing:
                missing[table] = table_missing
                if verbose:
                    print(
                        f"  [schema] WARNING: {table} missing columns: "
                        f"{', '.join(table_missing)}. Run migration.sql to fix.",
                    )
        except Exception as e:
            if verbose:
                print(f"  [schema] WARNING: Could not probe table '{table}': {e}")
            missing[table] = ["<table_missing_or_inaccessible>"]

    if verbose and not missing:
        print("  [schema] All tables and columns verified OK")

    return missing


if __name__ == "__main__":
    # Quick test: print watchlist count
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        wl_path = Path(__file__).resolve().parent.parent / "config" / "watchlist.json"
        count = seed_stocks_from_watchlist(str(wl_path))
        print(f"Seeded {count} stocks into Supabase")
    else:
        stocks = load_watchlist()
        print(f"Stocks in DB: {len(stocks)}")
        for s in stocks:
            print(f"  {s['ticker']}: {s['name']}")
