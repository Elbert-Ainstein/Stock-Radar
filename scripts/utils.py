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
    """Load the watchlist — Supabase first, JSON fallback."""
    sb = _get_supabase()
    if sb:
        try:
            resp = sb.table("stocks").select("*").eq("active", True).execute()
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
                print(f"  [DB] Loaded {len(stocks)} stocks from Supabase")
                return stocks
        except Exception as e:
            print(f"  [DB] Supabase read failed, falling back to JSON: {e}")

    # JSON fallback
    cfg = json.loads((CONFIG_DIR / "watchlist.json").read_text(encoding="utf-8"))
    return cfg.get("watchlist", cfg.get("stocks", []))


def get_screen_filters() -> dict:
    """Load screening filters from config."""
    cfg = json.loads((CONFIG_DIR / "watchlist.json").read_text(encoding="utf-8"))
    return cfg.get("screen_filters", {})


def save_signals(scout_name: str, signals: list[dict]):
    """Save scout signals — Supabase first, JSON fallback."""
    run_id = get_run_id()

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
