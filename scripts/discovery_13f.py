#!/usr/bin/env python3
"""
discovery_13f.py - 13F ingester for discovery_universe.

Pulls 13F-HR filings from SEC EDGAR for a curated list of conviction-style
managers (Druckenmiller, Coatue, Tiger Global, Whale Rock, Lone Pine, ARK,
D1 Capital, Altimeter, Addition). Diffs the latest quarter vs the prior
quarter to identify NEW POSITIONS and SIGNIFICANT ADDS (>50% increase).
Filters to companies with market cap < $50B (the discovery value is in
mid-cap thesis picks, not adding to NVDA). Upserts into discovery_universe
with status='exploring' and source='13f_{manager}_{quarter}_{action}'.

The convergence filter is: "smart manager bought it AND Haiku cheap-scan
scores it 7+" -- two independent signals from real data.

SEC EDGAR rate limit: 10 req/sec. Identify via User-Agent header.

Usage:
    python scripts/discovery_13f.py                       # all managers, latest quarter
    python scripts/discovery_13f.py --manager druckenmiller --dry-run
    python scripts/discovery_13f.py --quarter 2025Q4      # force a specific quarter
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
import yfinance as yf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env  # noqa: E402
load_env()

# ─── Manager registry ───────────────────────────────────────────
# Each manager: SEC CIK (10-digit, zero-padded). Style notes per Hume's brief.
# Verified against EDGAR full-text search for 13F-HR filings.
MANAGERS = {
    "druckenmiller":   "0001536411",   # Duquesne Family Office (Stanley Druckenmiller)
    "coatue":          "0001135730",   # Coatue Management
    "tiger_global":    "0001167483",   # Tiger Global Management
    "whale_rock":      "0001387322",   # Whale Rock Capital Management LLC (verified via EFTS)
    "lone_pine":       "0001061165",   # Lone Pine Capital
    "ark":             "0001697748",   # ARK Investment Management
    "d1_capital":      "0001747057",   # D1 Capital Partners L.P. (verified via EFTS)
    "altimeter":       "0001541617",   # Altimeter Capital Management, LLC (verified via EFTS)
    # "addition" -- not findable via EFTS by name; CIK lookup deferred
}

# ─── EDGAR / OpenFIGI ───────────────────────────────────────────
SEC_USER_AGENT = "Stock Radar discovery_13f.py asyanurpekel@gmail.com"
SEC_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
SEC_REQ_INTERVAL = 0.12  # ~8 req/sec, well under the 10/sec limit
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
MAX_MARKET_CAP_USD = 50_000_000_000  # $50B per Hume's brief

_last_sec_req = 0.0


def _sec_get(url: str, expect_json: bool = False) -> Any:
    """Rate-limited GET against sec.gov / data.sec.gov."""
    global _last_sec_req
    elapsed = time.time() - _last_sec_req
    if elapsed < SEC_REQ_INTERVAL:
        time.sleep(SEC_REQ_INTERVAL - elapsed)
    r = requests.get(url, headers=SEC_HEADERS, timeout=20)
    _last_sec_req = time.time()
    r.raise_for_status()
    return r.json() if expect_json else r.text


# ─── 13F retrieval ──────────────────────────────────────────────
def list_13f_filings(cik: str) -> list[dict]:
    """Return list of {accession, filing_date, period_of_report} for a CIK,
    most recent first."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = _sec_get(url, expect_json=True)
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    period_of_report = recent.get("reportDate", [])
    primary_docs = recent.get("primaryDocument", [])
    out = []
    for i, f in enumerate(forms):
        if f != "13F-HR":
            continue
        out.append({
            "accession": accessions[i],
            "filing_date": filing_dates[i],
            "period_of_report": period_of_report[i],
            "primary_doc": primary_docs[i],
        })
    return out


def fetch_information_table(cik: str, accession: str) -> list[dict]:
    """Fetch and parse the 13F information table XML.
    Returns list of {nameOfIssuer, cusip, value_usd, shares}.
    """
    accession_clean = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/"
    # Find the information table file via the index
    idx_url = urljoin(base, f"{accession}-index.htm")
    try:
        idx_html = _sec_get(idx_url)
    except Exception:
        # Fallback: try the JSON index
        try:
            idx_data = _sec_get(urljoin(base, "index.json"), expect_json=True)
            files = [x["name"] for x in idx_data.get("directory", {}).get("item", [])]
        except Exception:
            return []
    else:
        files = re.findall(r'href="[^"]*?/([^/"]+\.xml)"', idx_html)

    # Heuristic: information table files usually end with infotable.xml or are
    # the second .xml in the index (first is the primary doc/cover page)
    info_xml = None
    for f in files:
        if "infotable" in f.lower() or "informationtable" in f.lower():
            info_xml = f
            break
    if not info_xml:
        # Try the second xml file (skip cover-page form4xxx primary doc)
        xmls = [f for f in files if f.endswith(".xml")]
        if len(xmls) >= 2:
            info_xml = xmls[-1]
        elif xmls:
            info_xml = xmls[0]
    if not info_xml:
        return []

    xml_text = _sec_get(urljoin(base, info_xml))
    return parse_information_table_xml(xml_text)


def parse_information_table_xml(xml_text: str) -> list[dict]:
    """Parse 13F informationTable XML into a list of holdings,
    DEDUPED by CUSIP (sums shares + values across share classes / sub-accounts).

    Older 13F values are in thousands of USD; newer (2023+) are in raw USD.
    The form instructions still say "value in thousands" so we normalize on
    that convention.
    """
    # Strip default namespace for easier parsing
    xml_text = re.sub(r'\sxmlns="[^"]+"', '', xml_text, count=1)
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        print(f"  [13F] XML parse failed: {e}", file=sys.stderr)
        return []
    by_cusip: dict[str, dict] = {}
    for it in root.findall(".//infoTable"):
        try:
            name = (it.findtext("nameOfIssuer") or "").strip()
            cusip = (it.findtext("cusip") or "").strip().upper()
            value_s = (it.findtext("value") or "0").strip().replace(",", "")
            value_int = int(float(value_s))
            shares_node = it.find("shrsOrPrnAmt/sshPrnamt")
            shares = int(shares_node.text or 0) if shares_node is not None else 0
            existing = by_cusip.get(cusip)
            if existing:
                existing["shares"] += shares
                existing["value_usd"] += value_int * 1000
            else:
                by_cusip[cusip] = {
                    "name": name,
                    "cusip": cusip,
                    "value_usd": value_int * 1000,
                    "shares": shares,
                }
        except Exception:
            continue
    return list(by_cusip.values())


# ─── CUSIP → ticker via OpenFIGI ────────────────────────────────
_cusip_cache: dict[str, str | None] = {}


def cusips_to_tickers(cusips: list[str]) -> dict[str, str | None]:
    """Batch resolve CUSIPs to US tickers via OpenFIGI. Returns {cusip: ticker_or_None}."""
    out: dict[str, str | None] = {}
    todo = []
    for c in cusips:
        if c in _cusip_cache:
            out[c] = _cusip_cache[c]
        else:
            todo.append(c)
    # OpenFIGI unauthenticated: 10 jobs per request, 25 requests/minute.
    BATCH = 10
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        body = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        try:
            r = requests.post(OPENFIGI_URL, json=body, timeout=20,
                              headers={"Content-Type": "application/json"})
            if r.status_code != 200:
                print(f"  [openfigi] HTTP {r.status_code} on batch of {len(batch)}", file=sys.stderr)
                for c in batch:
                    _cusip_cache[c] = None
                    out[c] = None
                if r.status_code == 429:
                    time.sleep(8)
                continue
            results = r.json()
            for c, res in zip(batch, results):
                data = (res or {}).get("data") or []
                ticker = None
                us_codes = ("US", "UN", "UR", "UQ", "UV", "UA", "UP", "UM", "UF", "UW")
                for entry in data:
                    if entry.get("exchCode") in us_codes:
                        ticker = entry.get("ticker")
                        break
                if not ticker:
                    for entry in data:
                        t = entry.get("ticker") or ""
                        if t and "/" not in t and " " not in t:
                            ticker = t
                            break
                _cusip_cache[c] = ticker
                out[c] = ticker
            time.sleep(2.5)  # ~24 req/min, just under unauthenticated 25/min cap
        except Exception as e:
            print(f"  [openfigi] threw on batch: {e}", file=sys.stderr)
            for c in batch:
                _cusip_cache[c] = None
                out[c] = None
    return out


# ─── Diff logic ─────────────────────────────────────────────────
def diff_holdings(latest: list[dict], prior: list[dict]) -> dict[str, list[dict]]:
    """Diff two lists of {cusip, shares, value_usd, name} into:
       - new_positions:  in latest, not in prior
       - significant_adds: in both, latest.shares > 1.5 * prior.shares
       - existing: in both, modest change (skipped per Hume's filter)
       - exits:    in prior, not in latest (informational; not used)
    """
    prior_by_cusip = {h["cusip"]: h for h in prior}
    new_positions = []
    significant_adds = []
    existing = []
    for h in latest:
        cusip = h["cusip"]
        if cusip not in prior_by_cusip:
            new_positions.append(h)
            continue
        prev = prior_by_cusip[cusip]
        if prev["shares"] > 0 and h["shares"] / prev["shares"] > 1.5:
            adj = dict(h)
            adj["prior_shares"] = prev["shares"]
            adj["share_increase_pct"] = (h["shares"] / prev["shares"] - 1) * 100
            significant_adds.append(adj)
        else:
            existing.append(h)
    exits = [h for h in prior if h["cusip"] not in {x["cusip"] for x in latest}]
    return {
        "new_positions": new_positions,
        "significant_adds": significant_adds,
        "existing": existing,
        "exits": exits,
    }


# ─── Quarter labeling ───────────────────────────────────────────
def period_to_quarter(period_str: str) -> str:
    """Convert '2025-12-31' to '2025Q4'."""
    try:
        d = datetime.fromisoformat(period_str)
        q = (d.month - 1) // 3 + 1
        return f"{d.year}Q{q}"
    except Exception:
        return period_str


# ─── Market cap check via yfinance ──────────────────────────────
def fetch_ticker_meta(ticker: str) -> dict | None:
    """Return {market_cap_usd, currency, name, sector} for a US ticker."""
    try:
        info = yf.Ticker(ticker).info or {}
        mc = info.get("marketCap")
        if not mc:
            return None
        return {
            "market_cap_usd": float(mc),
            "currency": (info.get("currency") or "USD").upper(),
            "name": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector") or "",
        }
    except Exception:
        return None


# ─── Upsert ──────────────────────────────────────────────────────
def upsert_candidate(row: dict, dry_run: bool = False) -> bool:
    """Upsert with source-signal accumulation: if a row already exists with a
    different `source` value, append the new source rather than overwriting.
    This preserves manager-convergence info (e.g. NTRA bought by Druckenmiller
    AND Coatue produces source = "13f_druckenmiller_..., 13f_coatue_...").
    """
    if dry_run:
        return True
    try:
        from supabase_helper import get_client
        sb = get_client()
        # Read existing source first
        existing = sb.table("discovery_universe").select("source,status").eq(
            "ticker", row["ticker"]
        ).execute()
        existing_data = (existing.data or [None])[0]
        if existing_data:
            existing_source = existing_data.get("source") or ""
            new_source = row["source"]
            if new_source not in existing_source.split(", "):
                row["source"] = (existing_source + ", " + new_source) if existing_source else new_source
            else:
                row["source"] = existing_source  # already there, no change
            # Don't downgrade status (e.g. don't overwrite 'promising' with 'exploring')
            existing_status = existing_data.get("status") or "exploring"
            if existing_status in ("promising", "promoted", "watchlisted"):
                row["status"] = existing_status
        sb.table("discovery_universe").upsert(row, on_conflict="ticker").execute()
        return True
    except Exception as e:
        print(f"  [DB] upsert failed for {row['ticker']}: {e}", file=sys.stderr)
        return False


# ─── Main ────────────────────────────────────────────────────────
def process_manager(name: str, cik: str, dry_run: bool = False) -> dict:
    """Process one manager: fetch latest two 13Fs, diff, upsert filtered candidates."""
    summary = {"manager": name, "new": 0, "adds": 0, "skipped_too_big": 0,
               "no_ticker": 0, "no_meta": 0, "upserted": 0, "quarter": "?"}
    try:
        filings = list_13f_filings(cik)
    except Exception as e:
        print(f"  [{name}] EDGAR fetch failed: {e}", file=sys.stderr)
        return summary
    if len(filings) < 2:
        print(f"  [{name}] only {len(filings)} 13F filings found, need >=2 for diff")
        return summary

    latest = filings[0]
    prior = filings[1]
    quarter = period_to_quarter(latest["period_of_report"])
    summary["quarter"] = quarter
    print(f"\n  [{name}] latest={latest['accession']} ({latest['period_of_report']}) "
          f"vs prior={prior['accession']} ({prior['period_of_report']})")

    latest_holdings = fetch_information_table(cik, latest["accession"])
    prior_holdings = fetch_information_table(cik, prior["accession"])
    print(f"  [{name}] holdings: latest={len(latest_holdings)}, prior={len(prior_holdings)}")
    if not latest_holdings:
        return summary

    diff = diff_holdings(latest_holdings, prior_holdings)
    summary["new"] = len(diff["new_positions"])
    summary["adds"] = len(diff["significant_adds"])
    print(f"  [{name}] new positions: {summary['new']}, significant adds: {summary['adds']}, "
          f"exits: {len(diff['exits'])}")

    candidates = (
        [(h, "new_position") for h in diff["new_positions"]]
        + [(h, "significant_add") for h in diff["significant_adds"]]
    )
    if not candidates:
        return summary

    # Resolve all CUSIPs in one batch
    cusips = list({h["cusip"] for h, _ in candidates})
    cusip_map = cusips_to_tickers(cusips)

    for h, action in candidates:
        ticker = cusip_map.get(h["cusip"])
        if not ticker:
            summary["no_ticker"] += 1
            continue
        meta = fetch_ticker_meta(ticker)
        if not meta:
            summary["no_meta"] += 1
            continue
        if meta["market_cap_usd"] > MAX_MARKET_CAP_USD:
            summary["skipped_too_big"] += 1
            continue
        row = {
            "ticker": ticker,
            "market": "US",  # 13F is US-only by definition
            "company_name": meta["name"],
            "sector": meta["sector"] or None,
            "source": f"13f_{name}_{quarter}_{action}",
            "status": "exploring",
            "market_cap_usd": round(meta["market_cap_usd"], 2),
            "currency": meta["currency"],
        }
        ok = upsert_candidate(row, dry_run=dry_run)
        if ok:
            summary["upserted"] += 1
            print(f"    + {ticker:<6} ${meta['market_cap_usd']/1e9:>5.1f}B  "
                  f"{action:<17}  {meta['name'][:45]}")
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="13F manager-position ingester")
    p.add_argument("--manager", default="",
                   help="Process only this manager (e.g. druckenmiller). Default: all.")
    p.add_argument("--dry-run", action="store_true", help="Don't write to discovery_universe")
    args = p.parse_args(argv)

    if args.manager:
        if args.manager not in MANAGERS:
            print(f"ERROR: unknown manager {args.manager}. Valid: {list(MANAGERS)}", file=sys.stderr)
            return 2
        manager_subset = {args.manager: MANAGERS[args.manager]}
    else:
        manager_subset = MANAGERS

    print("=" * 60)
    print(f"  DISCOVERY 13F INGEST - {datetime.now(timezone.utc).isoformat()}")
    print(f"  managers: {list(manager_subset)}")
    print(f"  dry_run: {args.dry_run}")
    print("=" * 60)

    summaries = []
    for name, cik in manager_subset.items():
        s = process_manager(name, cik, dry_run=args.dry_run)
        summaries.append(s)

    print()
    print("-" * 60)
    print(f"  {'manager':<18} {'qtr':<7} {'new':>4} {'adds':>5} {'>50B':>5} {'noTk':>5} {'upsert':>7}")
    total_upserted = 0
    for s in summaries:
        print(f"  {s['manager']:<18} {s['quarter']:<7} {s['new']:>4} {s['adds']:>5} "
              f"{s['skipped_too_big']:>5} {s['no_ticker']:>5} {s['upserted']:>7}")
        total_upserted += s["upserted"]
    print("-" * 60)
    print(f"  total upserted: {total_upserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
