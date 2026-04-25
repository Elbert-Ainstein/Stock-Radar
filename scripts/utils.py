"""
Shared utilities for all scout scripts.
"""
import json
import os
import sys
import io
from datetime import datetime, timezone
from pathlib import Path

# ─── Fix Windows console encoding for emoji/unicode ───
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# Paths
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
ENV_FILE = ROOT / ".env"

DATA_DIR.mkdir(exist_ok=True)

# ─── Run ID (set by pipeline runner, used by scouts) ───
_current_run_id: str | None = None

def set_run_id(run_id: str):
    global _current_run_id
    _current_run_id = run_id

def get_run_id() -> str | None:
    return _current_run_id


def load_env():
    """Load .env file into os.environ."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if value and (key not in os.environ or not os.environ[key]):
                    os.environ[key] = value


def _get_supabase():
    """Try to get Supabase client, return None if not configured."""
    try:
        from supabase_helper import get_client
        return get_client()
    except Exception:
        return None


def get_watchlist() -> list[dict]:
    """Load the watchlist — Supabase first, JSON fallback.

    If the PIPELINE_TICKER_FILTER env var is set (by run_single_ticker),
    only return the matching stock. This prevents mini-pipelines from
    scanning the entire watchlist when only one stock is needed.
    """
    ticker_filter = os.environ.get("PIPELINE_TICKER_FILTER", "").upper()

    sb = _get_supabase()
    if sb:
        try:
            query = sb.table("stocks").select("*").eq("active", True)
            if ticker_filter:
                query = query.eq("ticker", ticker_filter)
            resp = query.execute()
            if resp.data:
                # Map DB columns to the format scouts expect
                stocks = []
                for row in resp.data:
                    stock = {
                        "ticker": row["ticker"],
                        "name": row["name"],
                        "sector": row.get("sector", ""),
                        "thesis": row.get("thesis", ""),
                        "kill_condition": row.get("kill_condition", ""),
                        "tags": row.get("tags", []),
                        "archetype": row.get("archetype"),
                        "target": {
                            "price": row.get("target_price"),
                            "timeline_years": row.get("timeline_years", 3),
                            "valuation_method": row.get("valuation_method", "pe"),
                            "target_multiple": row.get("target_multiple"),
                            "notes": row.get("target_notes", ""),
                        },
                        "model_defaults": row.get("model_defaults", {}),
                        "scenarios": row.get("scenarios", {}),
                        "criteria": row.get("criteria", []),
                    }
                    stocks.append(stock)
                label = f" (filtered: {ticker_filter})" if ticker_filter else ""
                print(f"  [DB] Loaded {len(stocks)} stocks from Supabase{label}")
                return stocks
        except Exception as e:
            print(f"  [DB] Supabase read failed, falling back to JSON: {e}")

    # JSON fallback
    cfg = json.loads((CONFIG_DIR / "watchlist.json").read_text(encoding="utf-8"))
    all_stocks = cfg.get("watchlist", cfg.get("stocks", []))
    if ticker_filter:
        all_stocks = [s for s in all_stocks if s["ticker"].upper() == ticker_filter]
    return all_stocks


def get_fresh_tickers(scout_name: str, max_age_hours: int | None = None) -> set[str]:
    """Return tickers that already have recent signals for this scout.

    Used by scouts to skip stocks that were already scanned recently,
    avoiding redundant API calls on re-runs.

    If *max_age_hours* is ``None`` (default), the cadence is looked up
    from ``registries.SCOUT_CADENCE_HOURS``.  This keeps each scout's
    refresh interval in one place instead of scattered across 7 files.
    """
    if max_age_hours is None:
        try:
            from registries import SCOUT_CADENCE_HOURS
            max_age_hours = SCOUT_CADENCE_HOURS.get(scout_name.lower(), 20)
        except ImportError:
            max_age_hours = 20

    sb = _get_supabase()
    if not sb:
        return set()
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        resp = (
            sb.table("signals")
            .select("ticker")
            .eq("scout", scout_name.lower())
            .gte("created_at", cutoff)
            .execute()
        )
        return {r["ticker"] for r in (resp.data or [])}
    except Exception:
        return set()


def get_screen_filters() -> dict:
    """Load screening filters from config."""
    cfg = json.loads((CONFIG_DIR / "watchlist.json").read_text(encoding="utf-8"))
    return cfg.get("screen_filters", {})


def save_signals(scout_name: str, signals: list[dict]):
    """Save scout signals — Supabase first, JSON fallback.

    Automatically computes and injects a confidence score (0.0-1.0) into
    each signal's scores dict if not already present.
    """
    run_id = get_run_id()

    # Auto-inject confidence scores
    try:
        from confidence import compute_scout_confidence
        for sig in signals:
            scores = sig.get("scores") or {}
            if "confidence" not in scores:
                scores["confidence"] = compute_scout_confidence(
                    scout_name.lower(),
                    sig.get("data", {}),
                    scores,
                )
                sig["scores"] = scores
    except ImportError:
        pass  # confidence module not available — skip silently

    sb = _get_supabase()
    if sb and run_id:
        try:
            rows = []
            for sig in signals:
                rows.append({
                    "ticker": sig["ticker"],
                    "scout": sig.get("scout", scout_name).lower(),
                    "signal": sig["signal"],
                    "ai": sig.get("ai", "Script"),
                    "summary": sig.get("summary", ""),
                    "data": sig.get("data", {}),
                    "scores": sig.get("scores", {}),
                    "run_id": run_id,
                })
            if rows:
                sb.table("signals").insert(rows).execute()
                print(f"  [DB] Saved {len(rows)} {scout_name} signals to Supabase (run: {run_id})")
                return
        except Exception as e:
            print(f"  [DB] Supabase write failed, falling back to JSON: {e}")

    # JSON fallback
    output = {
        "scout": scout_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
    }
    path = DATA_DIR / f"{scout_name}_signals.json"
    path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"  [{scout_name}] Saved {len(signals)} signals to {path}")


def load_signals(scout_name: str) -> dict | None:
    """Load existing signals for a scout.

    Prefers Supabase (latest_signals view) when available; falls back to
    local JSON file. The JSON file can be arbitrarily stale since
    save_signals() skips the JSON write after a successful Supabase insert.
    """
    # Try Supabase first
    try:
        from supabase_helper import get_client
        sb = get_client()
        rows = (
            sb.table("latest_signals")
            .select("*")
            .eq("scout", scout_name)
            .execute()
        ).data or []
        if rows:
            return {"signals": rows}
    except Exception:
        pass  # fall back to JSON

    path = DATA_DIR / f"{scout_name}_signals.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def timestamp() -> str:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
