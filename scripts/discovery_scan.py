#!/usr/bin/env python3
"""
discovery_scan.py — Cheap-scan worker for `discovery_universe` candidates.

Pulls oldest-`last_scanned`-first batch from discovery_universe (status in
{exploring, promising}, last_scanned NULL or > 7 days old). For each
candidate, builds a fundamentals snapshot and asks Claude Haiku to score
whether the company looks like a 10x setup.

Hard rules:
  1. Fiscal-calendar guard for non-US tickers: must have ≥4 quarterly rows
     and consecutive-row gaps ≤100 days. Otherwise SKIP (don't sum bogus
     semi-annual rows into a 2x-too-big TTM). Log the reason. Update
     last_scanned anyway with a "skipped" verdict so we don't retry forever.
  2. Cost budget: --max-cost-usd terminates the loop before exceeding it.
  3. Every drop/skip logs its reason + ticker.
  4. Promotion: score >= 7 → status='promising'. Demotion: 3 consecutive
     scans all <4 → status='dropped'. Full-thesis launch is OUT OF SCOPE
     (separate script will pick up promising-status rows).

Usage:
    python scripts/discovery_scan.py --batch-size 50
    python scripts/discovery_scan.py --batch-size 5 --dry-run
    python scripts/discovery_scan.py --max-cost-usd 0.50
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env  # noqa: E402

load_env()


# ─── Config ───
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SCAN_VERSION = "2"  # bumped: revised patches (staleness detection, cause-tagged drop gate, fiscal cooldown)

# Cheap-scan cadence: skip rows with last_scanned within this window
SCAN_REFRESH_DAYS = 7

# Fiscal-skipped rows recheck sooner — they may have a new filing in days,
# not weeks. Was 7 days (red-team purgatory bug); now 1 day. NEVER auto-drop
# on fiscal-calendar reason — wait for the actual filing to arrive.
FISCAL_SKIP_COOLDOWN_HOURS = 24

# Promotion / drop thresholds
PROMOTE_SCORE = 7.0
DROP_SCORE = 4.0
DROP_CONSECUTIVE = 3

# Staleness-detection signatures. If Haiku's verdict contains any of these
# phrases, its training-data prior is overriding the supplied business
# description (e.g. SNDK case: re-listed 2025 but Haiku still wrote
# "SanDisk was acquired by Western Digital"). Flag the row for manual
# review instead of letting a stale-knowledge low score trigger the drop
# gate. Cheaper and more honest than telling Haiku "trust the description"
# and hoping it works.
STALENESS_SIGNATURES = (
    "was acquired",
    "was delisted",
    "no longer publicly traded",
    "no longer public",
    "merged with",
    "taken private",
    "bankruptcy",
    "ceased trading",
)

# Fiscal-calendar guard
MIN_QUARTERLY_ROWS_NON_US = 4
MAX_QUARTER_GAP_DAYS = 100  # >100 day gap => semi-annual reporting

# Haiku pricing (per 1M tokens, public list price as of model release).
# Used purely for cost-budget tracking — actual billing is by Anthropic.
HAIKU_INPUT_USD_PER_MTOK = 1.00
HAIKU_OUTPUT_USD_PER_MTOK = 5.00


# ─── Market detection (mirrors scout_discovery.detect_market) ───
_MARKET_SUFFIXES = {
    "HK": "HK", "T": "JP", "TW": "TW", "TWO": "TW", "KS": "KR", "KQ": "KR",
}


def detect_market(ticker: str) -> str:
    if not ticker:
        return "UNKNOWN"
    if "." not in ticker:
        return "US"
    suffix = ticker.rsplit(".", 1)[1].upper()
    return _MARKET_SUFFIXES.get(suffix, "UNKNOWN")


# ─── Fundamentals fetch with fiscal-calendar guard ───

def _quarterly_dates(stock: yf.Ticker) -> list[datetime]:
    """Return quarterly-financials index as a list of UTC datetimes (descending)."""
    try:
        qf = stock.quarterly_income_stmt
    except Exception:
        qf = None
    if qf is None or qf.empty:
        try:
            qf = stock.quarterly_financials
        except Exception:
            qf = None
    if qf is None or qf.empty:
        return []
    try:
        cols = list(qf.columns)
        out = []
        for c in cols:
            if isinstance(c, datetime):
                out.append(c)
            else:
                try:
                    out.append(datetime.fromisoformat(str(c)))
                except Exception:
                    continue
        return sorted(out, reverse=True)
    except Exception:
        return []


def fiscal_guard(ticker: str) -> tuple[bool, str]:
    """Return (passed, reason). For non-US tickers, enforce ≥4 quarterly rows
    with consecutive gaps ≤100 days. US tickers always pass.
    """
    market = detect_market(ticker)
    if market == "US":
        return True, ""
    try:
        stock = yf.Ticker(ticker)
        dates = _quarterly_dates(stock)
    except Exception as e:
        return False, f"fiscal-calendar guard tripped: yfinance threw on {ticker}: {e}"

    if len(dates) < MIN_QUARTERLY_ROWS_NON_US:
        return False, (f"fiscal-calendar guard tripped: only {len(dates)} quarterly rows for {ticker} "
                       f"(need ≥{MIN_QUARTERLY_ROWS_NON_US}); dates={[d.date().isoformat() for d in dates]}")

    # Check gaps between the last 4 rows
    last4 = dates[:4]
    gaps = []
    for a, b in zip(last4, last4[1:]):
        gaps.append((a - b).days)
    if any(g > MAX_QUARTER_GAP_DAYS for g in gaps):
        return False, (f"fiscal-calendar guard tripped: semi-annual gap detected for {ticker}; "
                       f"dates={[d.date().isoformat() for d in last4]} gaps={gaps}")

    return True, ""


def fetch_fundamentals(ticker: str) -> dict[str, Any] | None:
    """Pull a small fundamentals snapshot via yfinance. Returns None on failure."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        if not info or "marketCap" not in info:
            return None

        # Convert revenue to USD using info['financialCurrency'] if needed
        rev_local = info.get("totalRevenue") or 0
        fin_ccy = (info.get("financialCurrency") or info.get("currency") or "USD").upper()

        return {
            "currency": fin_ccy,
            "revenue_local_ttm": rev_local,
            "revenue_growth_yoy": info.get("revenueGrowth"),       # decimal e.g. 0.25
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "forward_pe": info.get("forwardPE"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "sector": info.get("sector") or "",
            "name": info.get("longName") or info.get("shortName") or ticker,
        }
    except Exception as e:
        print(f"  [{ticker}] fetch_fundamentals threw: {e}", file=sys.stderr)
        return None


def revenue_ttm_usd(ticker: str, fund: dict[str, Any], fx_cache: dict[str, float]) -> float | None:
    """Convert local-currency revenue to USD via cached FX. HARD-FAIL on bad rate
    only at the worker level — we just return None and skip the field rather
    than abort the whole run."""
    try:
        rev = float(fund.get("revenue_local_ttm") or 0)
    except (TypeError, ValueError):
        return None
    if rev <= 0:
        return None
    ccy = (fund.get("currency") or "USD").upper()
    if ccy == "USD":
        return rev
    if ccy in fx_cache:
        rate = fx_cache[ccy]
    else:
        pair = f"{ccy}USD=X"
        try:
            hist = yf.Ticker(pair).history(period="5d", auto_adjust=False)
            if hist is None or hist.empty:
                print(f"  [{ticker}] FX missing for {pair}; rev_ttm_usd unavailable", file=sys.stderr)
                return None
            rate = float(hist["Close"].dropna().iloc[-1])
        except Exception as e:
            print(f"  [{ticker}] FX fetch failed for {pair}: {e}", file=sys.stderr)
            return None
        if not rate or rate <= 0:
            print(f"  [{ticker}] FX bad rate {pair}={rate!r}", file=sys.stderr)
            return None
        fx_cache[ccy] = rate
    return rev * rate


# ─── Prompt build ───

def build_fundamentals_block(fund: dict[str, Any], rev_usd: float | None) -> str:
    lines = []
    if rev_usd:
        lines.append(f"- Revenue (TTM, USD): ${rev_usd/1e6:,.1f}M")
    rg = fund.get("revenue_growth_yoy")
    if rg is not None:
        try:
            lines.append(f"- Revenue growth YoY: {float(rg)*100:.1f}%")
        except Exception:
            pass
    gm = fund.get("gross_margin")
    if gm is not None:
        try:
            lines.append(f"- Gross margin: {float(gm)*100:.1f}%")
        except Exception:
            pass
    om = fund.get("operating_margin")
    if om is not None:
        try:
            lines.append(f"- Operating margin: {float(om)*100:.1f}%")
        except Exception:
            pass
    fpe = fund.get("forward_pe")
    if fpe and isinstance(fpe, (int, float)) and not math.isnan(fpe):
        lines.append(f"- Forward P/E: {fpe:.1f}")
    ps = fund.get("ps_ratio")
    if ps and isinstance(ps, (int, float)) and not math.isnan(ps):
        lines.append(f"- P/S: {ps:.1f}")
    return "\n".join(lines) if lines else "- (fundamentals unavailable)"


PROMPT_TEMPLATE = """You are scoring whether a public company is worth a deeper investment thesis.
Output exactly one JSON object:
{{"score": 0-10, "verdict": "<one-sentence reason>"}}

Score 0-3: clearly not a 10x setup (mature, slow growth, no catalyst, weak moat)
Score 4-6: maybe; needs deeper look but not obviously compelling
Score 7-10: shows 10x setup characteristics (chokepoint position, accelerating revenue, large TAM, durable moat, asymmetric risk/reward)

Company: {COMPANY_NAME} ({TICKER}, {MARKET})
Sector: {SECTOR}
Market cap: ${MARKET_CAP_USD}M
Currency: {CURRENCY}

Latest fundamentals (skip any that are missing):
{FUNDAMENTALS_BLOCK}

{NEWS_LINE}

Respond with the JSON object only.
"""


def build_prompt(row: dict, fund: dict[str, Any], rev_usd: float | None,
                 news_headline: str = "") -> str:
    mcap_usd = row.get("market_cap_usd") or 0
    news_line = ""
    if news_headline:
        news_line = f"Recent context (one-liner if anything notable; otherwise omit):\n{news_headline}\n"
    return PROMPT_TEMPLATE.format(
        COMPANY_NAME=row.get("company_name") or fund.get("name") or row["ticker"],
        TICKER=row["ticker"],
        MARKET=row.get("market", "?"),
        SECTOR=row.get("sector") or fund.get("sector") or "Unknown",
        MARKET_CAP_USD=f"{mcap_usd/1e6:,.0f}",
        CURRENCY=row.get("currency") or fund.get("currency") or "?",
        FUNDAMENTALS_BLOCK=build_fundamentals_block(fund, rev_usd),
        NEWS_LINE=news_line,
    )


# ─── Haiku call ───

JSON_OBJ_RE = re.compile(r"\{.*?\}", re.DOTALL)


def parse_haiku_response(text: str) -> dict[str, Any]:
    """Extract {score, verdict} JSON from Haiku's reply."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", text)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Last resort: find first {…} block
    m = JSON_OBJ_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def call_haiku(prompt: str) -> tuple[dict[str, Any], int, int]:
    """Call Haiku, return (parsed_json, input_tokens, output_tokens). Empty dict
    on failure."""
    try:
        import anthropic
    except ImportError as e:
        raise ImportError("anthropic SDK required: pip install anthropic") from e
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=200,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    text = "\n".join(text_parts)
    parsed = parse_haiku_response(text)
    return parsed, resp.usage.input_tokens, resp.usage.output_tokens


# ─── DB helpers ───

def fetch_batch(batch_size: int) -> list[dict]:
    """Pull oldest-first batch where status in (exploring, promising) and
    last_scanned is NULL or older than SCAN_REFRESH_DAYS days.
    """
    from supabase_helper import get_client
    sb = get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SCAN_REFRESH_DAYS)).isoformat()
    # Two queries combined client-side: NULL last_scanned first, then stale ones.
    null_resp = (
        sb.table("discovery_universe")
        .select("*")
        .in_("status", ["exploring", "promising"])
        .is_("last_scanned", "null")
        .limit(batch_size)
        .execute()
    )
    rows = list(null_resp.data or [])
    if len(rows) < batch_size:
        remaining = batch_size - len(rows)
        stale_resp = (
            sb.table("discovery_universe")
            .select("*")
            .in_("status", ["exploring", "promising"])
            .lt("last_scanned", cutoff)
            .order("last_scanned", desc=False)
            .limit(remaining)
            .execute()
        )
        rows.extend(stale_resp.data or [])
    return rows[:batch_size]


def update_row(ticker: str, updates: dict) -> None:
    from supabase_helper import get_client
    sb = get_client()
    sb.table("discovery_universe").update(updates).eq("ticker", ticker).execute()


def append_scan_history(existing: list, entry: dict) -> list:
    history = list(existing or [])
    history.append(entry)
    # Keep last 20 to bound row size
    return history[-20:]


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * HAIKU_INPUT_USD_PER_MTOK + \
           (output_tokens / 1_000_000) * HAIKU_OUTPUT_USD_PER_MTOK


# ─── Main ───

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1] if __doc__ else "")
    p.add_argument("--batch-size", type=int, default=50)
    p.add_argument("--max-cost-usd", type=float, default=1.00,
                   help="Stop before estimated total cost exceeds this (default $1.00)")
    p.add_argument("--dry-run", action="store_true",
                   help="Don't call Haiku and don't write to DB; print what would happen")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print("=" * 60)
    print(f"  DISCOVERY SCAN — {datetime.now(timezone.utc).isoformat()}")
    print(f"  batch_size={args.batch_size}  max_cost=${args.max_cost_usd:.2f}  dry_run={args.dry_run}")
    print("=" * 60)

    # Fetch batch
    if args.dry_run:
        print("\n  [dry-run] not contacting Supabase; nothing to scan locally")
        # Allow a no-op dry-run that just confirms the script is wired up
        rows: list[dict] = []
    else:
        try:
            rows = fetch_batch(args.batch_size)
        except Exception as e:
            print(f"  [DB] fetch_batch failed: {e}", file=sys.stderr)
            return 1

    print(f"\n  fetched {len(rows)} candidates to scan")
    if not rows:
        print("  nothing to do.")
        return 0

    fx_cache: dict[str, float] = {"USD": 1.0}
    scanned = promoted = dropped = guard_skips = 0
    total_in = total_out = 0
    total_cost = 0.0
    now_iso = datetime.now(timezone.utc).isoformat()

    for row in rows:
        ticker = row["ticker"]

        # Cost guard — stop if next scan would exceed budget. Estimate ~1500
        # input + 100 output tokens per scan as a conservative ceiling.
        projected_extra = estimate_cost(1500, 100)
        if total_cost + projected_extra > args.max_cost_usd:
            print(f"  [budget] would exceed ${args.max_cost_usd:.2f}; stopping early "
                  f"(scanned={scanned}, used=${total_cost:.4f})")
            break

        # Fiscal-calendar guard
        # PATCH 3 REVISED: NEVER auto-drop on fiscal-calendar reason.
        # Set last_scanned to a 24h-future cooldown so the row reappears in the
        # next scan window rather than the 7-day window. Asian semi-annual
        # reporters get retried sooner, and dropped only if Haiku scoring fails
        # on real data later -- not because we mistook their filing cadence.
        ok, reason = fiscal_guard(ticker)
        if not ok:
            print(f"  [{ticker}] {reason}")
            guard_skips += 1
            # Cooldown: pretend last_scanned was COOLDOWN-HOURS ago, so it
            # naturally re-enters the SCAN_REFRESH_DAYS window in 24h.
            cooldown_iso = (
                datetime.now(timezone.utc) - timedelta(days=SCAN_REFRESH_DAYS)
                + timedelta(hours=FISCAL_SKIP_COOLDOWN_HOURS)
            ).isoformat()
            scan_entry = {
                "ts": now_iso,
                "score": None,
                "verdict": "skipped: insufficient quarterly data for non-US ticker (will retry in 24h)",
                "model": HAIKU_MODEL,
                "version": SCAN_VERSION,
                "stale_knowledge": False,
                "fiscal_skip": True,
            }
            updates = {
                "last_scanned": cooldown_iso,
                "scan_history": append_scan_history(row.get("scan_history") or [], scan_entry),
            }
            if not args.dry_run:
                try:
                    update_row(ticker, updates)
                except Exception as e:
                    print(f"  [{ticker}] DB update failed: {e}", file=sys.stderr)
            continue

        # Fundamentals
        fund = fetch_fundamentals(ticker)
        if fund is None:
            print(f"  [{ticker}] fundamentals unavailable; skipping (will retry next cycle)")
            continue

        rev_usd = revenue_ttm_usd(ticker, fund, fx_cache)
        prompt = build_prompt(row, fund, rev_usd)

        if args.dry_run:
            scanned += 1
            print(f"  [{ticker}] [dry-run] prompt built ({len(prompt)} chars)")
            continue

        # Call Haiku
        try:
            parsed, in_tok, out_tok = call_haiku(prompt)
        except Exception as e:
            print(f"  [{ticker}] Haiku call failed: {e}", file=sys.stderr)
            continue

        total_in += in_tok
        total_out += out_tok
        total_cost = estimate_cost(total_in, total_out)
        scanned += 1

        score = parsed.get("score")
        verdict = parsed.get("verdict") or ""
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None

        if score_f is None:
            print(f"  [{ticker}] Haiku returned no parseable score; raw={parsed!r}")
            verdict = verdict or "haiku response unparseable"
        else:
            print(f"  [{ticker}] score={score_f:.1f} - {verdict[:80]}")

        # PATCH 1 REVISED: detect staleness signatures in the verdict.
        # If Haiku's training-data prior overrode the supplied business
        # description (e.g. "SanDisk was acquired by Western Digital"),
        # flag the row but do NOT let the score trigger the drop gate.
        verdict_lower = verdict.lower()
        is_stale = any(sig in verdict_lower for sig in STALENESS_SIGNATURES)
        if is_stale:
            print(f"  [{ticker}] STALE-KNOWLEDGE detected; flagging for manual review, not counting toward drop gate")

        scan_entry = {
            "ts": now_iso,
            "score": score_f,
            "verdict": verdict,
            "model": HAIKU_MODEL,
            "version": SCAN_VERSION,
            "stale_knowledge": is_stale,  # Patch 1 revised tagging
        }
        new_history = append_scan_history(row.get("scan_history") or [], scan_entry)

        updates: dict[str, Any] = {
            "last_scanned": now_iso,
            "scan_history": new_history,
        }
        # Don't write a stale-knowledge score to cheap_score -- it's noise
        if not is_stale:
            updates["cheap_score"] = score_f
            updates["cheap_verdict"] = verdict
        else:
            # Persist the verdict so manual reviewer can see it
            updates["cheap_verdict"] = f"[STALE-FLAG] {verdict}"

        # Promotion gate (skip stale rows)
        if (not is_stale and score_f is not None and score_f >= PROMOTE_SCORE
            and row.get("status") not in ("promoted", "watchlisted")):
            updates["status"] = "promising"
            promoted += 1

        # Drop gate (PATCH 2 REVISED): only drop if last 3 NON-STALE low scores all <DROP_SCORE.
        # Stale scores (Haiku training-data overrides) are detected via verdict signature
        # and excluded from the drop count. Prevents legitimate names from being permanently
        # dropped because Haiku confused them with old corporate-history events.
        if score_f is not None and score_f < DROP_SCORE:
            recent_non_stale = [
                e for e in new_history
                if e.get("score") is not None
                and not e.get("stale_knowledge", False)
            ][-DROP_CONSECUTIVE:]
            if (
                len(recent_non_stale) >= DROP_CONSECUTIVE
                and all((e["score"] or 0) < DROP_SCORE for e in recent_non_stale)
                and row.get("status") == "exploring"  # never demote promising/promoted/watchlisted
            ):
                updates["status"] = "dropped"
                dropped += 1

        try:
            update_row(ticker, updates)
        except Exception as e:
            print(f"  [{ticker}] DB update failed: {e}", file=sys.stderr)

        time.sleep(0.2)

    print("\n" + "-" * 60)
    print("  SUMMARY")
    print("-" * 60)
    print(f"  scanned:        {scanned}")
    print(f"  promoted:       {promoted}  (status -> 'promising')")
    print(f"  dropped:        {dropped}  (3 consecutive non-stale low scores)")
    print(f"  guard skips:    {guard_skips}  (fiscal-calendar mismatch, cooldown {FISCAL_SKIP_COOLDOWN_HOURS}h)")
    print(f"  tokens in/out:  {total_in} / {total_out}")
    print(f"  est cost:       ${total_cost:.4f}  (budget ${args.max_cost_usd:.2f})")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
