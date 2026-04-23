#!/usr/bin/env python3
"""
Scout: Catalyst / Contract / Order Detector
===========================================

This is the first scout in the 10x-scanner chain pipeline. Its job is to
answer the question:

    "What new or recent orders, contracts, customer wins, or major
     partnerships did this company land?"

Why this scout matters
----------------------
Contract wins are one of the earliest, cleanest demand-side signals:
  - Revolutionary companies: their first big anchor customers show up here
    (e.g. NVDA landing hyperscaler deals, PLTR signing new government
    contracts, anything with a new category that suddenly has a Fortune 500
    anchor willing to put money on the line).
  - Demand-wave companies: scale orders show up here as volume ramps
    (LITE's datacom bookings, ONTO's equipment orders from foundries,
    arms-dealer suppliers inking multi-year LTAs).

Data sources (Stage 1)
----------------------
1. **SEC EDGAR 8-K filings** — Items 1.01 (Material Definitive Agreement)
   and 8.01 (Other Events). Free, authoritative, legally-obligated disclosure
   for any contract material to US-listed issuers.
2. **Perplexity sonar search** — catches press releases, partnership news,
   and non-8-K disclosures (including foreign tickers where 8-K doesn't apply).

Output
------
For each ticker, we emit one signal with a `catalyst_events` array. Each
event fits the existing event_templates taxonomy (customer_win_major,
capacity_expansion, product_launch, etc.) so the downstream event_reasoner
can price it into the target.

Each event is also tagged with `thesis_bucket`:
  - "revolutionary" — suggests disruptive/paradigm-shift DNA
  - "demand_tailwind" — suggests structural-demand / picks-and-shovels DNA
  - "mixed" — elements of both
  - "neutral" — classification indeterminate

Usage
-----
    python scripts/scout_catalyst.py                  # all watchlist
    python scripts/scout_catalyst.py --ticker LITE    # one ticker
    python scripts/scout_catalyst.py --ticker AMD --days 120
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from utils import (
    get_run_id,
    get_watchlist,
    load_env,
    save_signals,
    set_run_id,
    timestamp,
)

load_env()

# ─── API keys (all optional; scout degrades gracefully) ───
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ─── SEC EDGAR config ───
SEC_HEADERS = {
    "User-Agent": "StockRadar/1.0 (stock-radar-catalyst@example.com)",
    "Accept": "application/json",
}

# Which 8-K items we care about for contract/order signals.
# Full list: https://www.sec.gov/fast-answers/answersform8khtm.html
CATALYST_8K_ITEMS = {
    "1.01",  # Entry into a Material Definitive Agreement
    "1.02",  # Termination of a Material Definitive Agreement  (lost contract!)
    "2.01",  # Completion of Acquisition or Disposition of Assets
    "2.03",  # Material Direct Financial Obligation
    "7.01",  # Regulation FD Disclosure (often includes major partnership PR)
    "8.01",  # Other Events (catch-all — most "we won X" announcements)
}

# Allowed event_templates taxonomy IDs (kept in sync with event_templates.py).
TAXONOMY_IDS = {
    "ma_target", "ma_acquirer",
    "regulatory_approval", "regulatory_rejection",
    "earnings_beat_raise", "earnings_miss_cut",
    "capacity_expansion", "supply_constraint",
    "customer_win_major", "customer_loss_major",
    "product_launch", "product_delay",
    "exec_change_positive", "exec_change_negative",
    "litigation_adverse", "litigation_favorable",
    "competitive_threat", "sector_tailwind", "sector_headwind",
    "buyback_large", "dividend_cut",
}

THESIS_BUCKETS = {"revolutionary", "demand_tailwind", "mixed", "neutral"}
MAGNITUDE_BUCKETS = {"small", "medium", "large"}


# ─────────────────────────────────────────────────────────────
# SEC EDGAR: 8-K fetcher
# ─────────────────────────────────────────────────────────────

_CIK_CACHE: dict[str, str] = {}


def _get_cik(ticker: str) -> str | None:
    """Resolve a ticker to its zero-padded CIK (reused from scout_insider pattern)."""
    if ticker in _CIK_CACHE:
        return _CIK_CACHE[ticker]
    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=SEC_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        for entry in resp.json().values():
            t = (entry.get("ticker") or "").upper()
            cik = str(entry["cik_str"]).zfill(10)
            _CIK_CACHE[t] = cik
        return _CIK_CACHE.get(ticker.upper())
    except Exception as e:
        print(f"  [{ticker}] CIK lookup failed: {e}")
        return None


def fetch_recent_8ks(ticker: str, days: int = 90) -> list[dict]:
    """Return list of recent 8-K filings with catalyst-relevant items.

    Each returned dict contains:
        filing_date, accession, primary_doc, items (list of item codes),
        url (link to filing index on EDGAR), description
    """
    cik = _get_cik(ticker)
    if not cik:
        return []

    try:
        resp = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=SEC_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [{ticker}] EDGAR submissions fetch failed: {e}")
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    items_list = recent.get("items", [])
    primary_docs = recent.get("primaryDocument", [])
    primary_descs = recent.get("primaryDocDescription", [])
    accessions = recent.get("accessionNumber", [])

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    out: list[dict] = []

    for i, form in enumerate(forms):
        if form not in ("8-K", "8-K/A"):
            continue

        try:
            fdate = datetime.strptime(dates[i], "%Y-%m-%d").date()
        except Exception:
            continue
        if fdate < cutoff:
            continue

        raw_items = (items_list[i] if i < len(items_list) else "") or ""
        # EDGAR lists items as comma-separated like "1.01,9.01"
        items_parsed = [it.strip() for it in raw_items.split(",") if it.strip()]

        if CATALYST_8K_ITEMS.isdisjoint(items_parsed) and not raw_items:
            # If items weren't tagged at all, keep the filing (edge case — rare).
            pass
        elif CATALYST_8K_ITEMS.isdisjoint(items_parsed):
            # Has items but none are ours — skip.
            continue

        accession = accessions[i] if i < len(accessions) else ""
        accession_nodash = accession.replace("-", "")
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        desc = primary_descs[i] if i < len(primary_descs) else ""

        out.append({
            "filing_date": dates[i],
            "accession": accession,
            "items": items_parsed,
            "primary_doc": primary_doc,
            "description": desc or "",
            "url": (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession_nodash}/{primary_doc}"
            ) if primary_doc else (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                f"&CIK={cik}&type=8-K"
            ),
        })

    return out


def fetch_8k_body_text(url: str, max_chars: int = 15000) -> str:
    """Fetch the 8-K primary document HTML, strip tags, return plain text.

    EDGAR's `primaryDocDescription` is almost always empty or generic, so we
    can't classify meaningfully from metadata alone. The real content (which
    items were filed, which exhibits, and often the actual press release
    language) lives inside the primary document. One extra HTTP call per
    filing is well worth it — it turns a generic 8-K into "Meta signs $60B
    GPU deal".

    Returns an empty string on any failure so callers can gracefully fall
    back to metadata-only classification.
    """
    if not url:
        return ""
    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"    [8-K body] fetch failed for {url[:60]}: {e}")
        return ""

    # Strip <script>/<style> blocks before tag removal — their contents would
    # otherwise leak into the extracted text and eat budget.
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)

    # Strip HTML tags, collapse whitespace.
    text = re.sub(r"<[^>]+>", " ", html)
    # HTML entities — just decode the common ones. Full decode not needed for LLM.
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&#8217;", "'")
    text = text.replace("&#8220;", '"').replace("&#8221;", '"').replace("&#8212;", "—")
    text = re.sub(r"\s+", " ", text).strip()

    return text[:max_chars]


# ─────────────────────────────────────────────────────────────
# Perplexity: contract / order / partnership search
# ─────────────────────────────────────────────────────────────

def perplexity_catalyst_search(ticker: str, company_name: str, days: int = 90) -> dict | None:
    """Query Perplexity sonar for recent contract/order/customer news.

    Returns parsed dict with `events` array. Each event has:
      summary, type (taxonomy id), direction, magnitude_bucket,
      counterparty, thesis_bucket, estimated_tcv_usd, date, source, url.

    Falls back to None if the API is unavailable or the key is missing.
    """
    if not PERPLEXITY_API_KEY:
        return None

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    system_prompt = (
        "You are a financial catalyst analyst. Return ONLY valid JSON (no "
        "markdown fences, no commentary). Your job is to find the most "
        "material CONTRACT WINS, CUSTOMER WINS, ORDERS, PARTNERSHIPS, and "
        "MAJOR AGREEMENTS from the most recent time window for the given "
        "ticker, and classify each one.\n\n"
        "Return this exact structure:\n"
        "{\n"
        "  \"events\": [\n"
        "    {\n"
        "      \"summary\": \"one sentence, factual, what happened\",\n"
        "      \"type\": \"one of: customer_win_major, customer_loss_major, "
        "capacity_expansion, supply_constraint, product_launch, "
        "product_delay, regulatory_approval, regulatory_rejection, "
        "ma_target, ma_acquirer, sector_tailwind, sector_headwind\",\n"
        "      \"direction\": \"up\" | \"down\",\n"
        "      \"magnitude_bucket\": \"small\" | \"medium\" | \"large\",\n"
        "      \"counterparty\": \"customer / partner / supplier name or null\",\n"
        "      \"estimated_tcv_usd\": null,  // total contract value in USD if disclosed, else null\n"
        "      \"duration_months\": null,  // if disclosed, else null\n"
        "      \"thesis_bucket\": \"revolutionary\" | \"demand_tailwind\" | \"mixed\" | \"neutral\",\n"
        "      \"date\": \"YYYY-MM-DD or null\",\n"
        "      \"source\": \"publication name or null\",\n"
        "      \"url\": \"source URL or null\",\n"
        "      \"rationale\": \"one sentence: why this matters for the thesis\"\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "DATE RULES (strict):\n"
        f" - Only include events dated on or after {cutoff_date}. NEVER include "
        f"earlier events even for context. If the announcement date is "
        f"unclear, omit the event rather than guess.\n\n"
        "MATERIALITY RULES:\n"
        " - Only MATERIAL events. Skip: rumors, speculation, analyst price "
        "targets, generic market commentary, distribution agreements that "
        "are not revenue-impacting.\n"
        " - magnitude_bucket: small = <1% of market cap impact likely; "
        "medium = 1-5%; large = >5% or category-defining.\n\n"
        "EVENT TYPE RULES (critical — do not confuse these):\n"
        " - customer_win_major: a SPECIFIC NAMED COUNTERPARTY (customer, "
        "partner, government agency) has agreed to buy from, partner with, "
        "or otherwise transact with the company. This is the correct type "
        "for any named-customer contract, supply agreement, partnership, or "
        "joint development deal — regardless of the broader industry "
        "narrative. Examples: 'Meta signs $60B GPU deal with AMD' is "
        "customer_win_major (Meta is the counterparty). 'OpenAI picks AMD' "
        "is customer_win_major.\n"
        " - sector_tailwind: a MACRO or INDUSTRY-WIDE shift benefits the "
        "company without a specific counterparty transacting (e.g. rate "
        "cuts, CHIPS Act signed, data-center capex up industry-wide). If a "
        "specific counterparty is named, this is NOT the right type.\n"
        " - product_launch: the company commercially releases a new product "
        "(no counterparty required). NOT to be used for a customer win.\n"
        " - capacity_expansion: the company announces a new fab, factory, "
        "or facility expansion.\n"
        " - Choose the SMALLEST category that still fits. If in doubt "
        "between customer_win_major and sector_tailwind and there is ANY "
        "named counterparty, pick customer_win_major.\n\n"
        "THESIS BUCKET RULES:\n"
        " - 'revolutionary' = the deal either (a) legitimizes the company "
        "as a credible alternative in a market previously dominated by one "
        "player (breaking a monopoly), or (b) validates a new architecture / "
        "category the company pioneered, or (c) represents a platform shift "
        "where the old TAM assumption is now clearly wrong. Examples of "
        "revolutionary: Meta or OpenAI signing multi-generation AI compute "
        "deals with AMD (breaks Nvidia monopoly premise); a startup's first "
        "Fortune 500 anchor customer for a new AI-native product.\n"
        " - 'demand_tailwind' = the company is a picks-and-shovels supplier "
        "riding a structural wave. The product itself is not category-creating "
        "— the company's edge is scale, manufacturing, or cost. LITE in AI "
        "optics is the canonical example.\n"
        " - 'mixed' = elements of both. Use this freely when a deal has "
        "both a category-legitimizing quality AND a supply/scale quality.\n"
        " - 'neutral' = only when you genuinely cannot tell (vague 8-K, "
        "undisclosed counterparty, generic PR).\n"
        " - Bias toward 'revolutionary' or 'mixed' when a deal materially "
        "changes the market structure. Defaulting to 'demand_tailwind' on a "
        "deal that breaks a monopoly is a misclassification.\n\n"
        "OUTPUT RULES:\n"
        " - Up to 8 events max. Quality over quantity.\n"
        " - If you cannot find any material catalysts, return {\"events\": []}."
    )

    user_prompt = (
        f"What are the most important NEW CONTRACTS, CUSTOMER WINS, ORDERS, "
        f"or MAJOR PARTNERSHIPS announced for {ticker} ({company_name}) in "
        f"the last {days} days? Focus on revenue-impacting catalysts. Ignore "
        f"price-target changes and pure macro commentary. For each event, "
        f"identify the counterparty, estimate the magnitude, and classify "
        f"whether the catalyst reflects revolutionary DNA or a demand-wave "
        f"tailwind."
    )

    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 1200,
                "temperature": 0.1,
                "web_search": True,
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [{ticker}] Perplexity catalyst search failed: {e}")
        return None

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    citations = data.get("citations", []) or []

    try:
        clean = content.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        print(f"  [{ticker}] Perplexity returned non-JSON — skipping.")
        return None

    return {
        "parsed": parsed,
        "citations": citations[:6],
        "raw_content": content,
    }


# ─────────────────────────────────────────────────────────────
# Event classification + normalization
# ─────────────────────────────────────────────────────────────

def _classify_8k_rule_based(filing: dict) -> dict:
    """Deterministic rule-based classification of an 8-K when no LLM available.

    Uses item codes + description keywords. Purposely conservative — when
    unsure, we default to sector_tailwind/neutral/small so the analyst gives
    it low weight (rather than inventing a customer_win_major signal that
    didn't happen).
    """
    items = set(filing.get("items", []))
    desc = (filing.get("description") or "").lower()

    # Defaults — SAFE / low-confidence (conservative when we can't read the body)
    event_type = "sector_tailwind"
    direction = "up"
    magnitude = "small"
    thesis = "neutral"
    summary = filing.get("description") or "8-K filing (contents not parsed)"

    if "1.02" in items:
        event_type = "customer_loss_major"
        direction = "down"
        magnitude = "medium"
        summary = "Termination of material definitive agreement"
    elif "1.01" in items:
        # Item 1.01 is "entry into a material definitive agreement" — this is
        # only a customer win if the agreement is a revenue-generating one.
        # Without body text we can't tell (might be a debt covenant, lease
        # extension, director agreement, etc.). Keep it small + neutral.
        event_type = "customer_win_major"
        direction = "up"
        magnitude = "small"
        thesis = "neutral"
        summary = "Entry into material definitive agreement (body not parsed)"
    elif "2.01" in items:
        event_type = "ma_acquirer"
        direction = "up"
        magnitude = "medium"
        summary = "Completion of acquisition / disposition"
    elif "2.03" in items:
        event_type = "sector_headwind"
        direction = "down"
        magnitude = "small"
        summary = "Material direct financial obligation incurred"
    elif "7.01" in items or "8.01" in items:
        # These items are catch-alls — only classify when a description hint
        # lets us be specific. Otherwise stay neutral/small.
        if any(k in desc for k in ("launch", "general availability", "commercial shipment")):
            event_type = "product_launch"
            magnitude = "medium"
            summary = "Product launch / commercial availability"
        elif any(k in desc for k in ("fab", "factory", "facility", "expansion", "capacity")):
            event_type = "capacity_expansion"
            magnitude = "medium"
            summary = "Capacity / facility expansion"
        elif any(k in desc for k in ("partnership", "collaborat", "agreement with")):
            event_type = "customer_win_major"
            magnitude = "medium"
            summary = "Partnership / collaboration announcement"
        elif any(k in desc for k in ("buyback", "repurchase")):
            event_type = "buyback_large"
            magnitude = "medium"
            summary = "Buyback / repurchase"
        elif any(k in desc for k in ("acquisition", "to acquire", "merger")):
            event_type = "ma_acquirer"
            magnitude = "medium"
            summary = "M&A announcement"

    return {
        "summary": summary[:280],
        "type": event_type,
        "direction": direction,
        "magnitude_bucket": magnitude,
        "counterparty": None,
        "estimated_tcv_usd": None,
        "duration_months": None,
        "thesis_bucket": thesis,
        "date": filing.get("filing_date"),
        "source": "SEC EDGAR 8-K",
        "url": filing.get("url"),
        "rationale": f"8-K items: {', '.join(sorted(items)) or 'n/a'}",
        "detected_by": "Catalyst-8K",
    }


def _classify_8k_with_claude(filing: dict, ticker: str, company: str) -> dict | None:
    """Enrich an 8-K with Claude classification (adds counterparty, TCV, thesis_bucket).

    Fetches the 8-K primary document body and feeds it to Claude alongside
    the filing metadata. This is what turns a generic "AMD filed an 8-K"
    into "AMD signs $60B / 6GW multi-gen supply deal with Meta".

    Returns None if Anthropic key missing or request fails — caller should
    fall back to _classify_8k_rule_based.
    """
    if not ANTHROPIC_API_KEY:
        return None

    items = ", ".join(filing.get("items", []) or [])
    desc = filing.get("description") or ""
    url = filing.get("url") or ""
    body_text = fetch_8k_body_text(url)
    body_block = (
        f"\n\n8-K DOCUMENT TEXT (first 15KB):\n{body_text}\n"
        if body_text else
        "\n\n(Could not fetch 8-K body — classify from metadata only.)\n"
    )

    prompt = (
        f"You are classifying an SEC 8-K filing for catalyst detection. "
        f"Return ONLY JSON (no markdown, no commentary).\n\n"
        f"Ticker: {ticker} ({company})\n"
        f"Filing date: {filing.get('filing_date')}\n"
        f"8-K items: {items or 'not tagged'}\n"
        f"Primary doc description: {desc}\n"
        f"Filing URL: {url}"
        f"{body_block}\n"
        f"Produce:\n"
        "{\n"
        "  \"summary\": \"one-sentence factual description of what happened\",\n"
        "  \"type\": \"pick one: customer_win_major, customer_loss_major, "
        "capacity_expansion, supply_constraint, product_launch, "
        "product_delay, regulatory_approval, regulatory_rejection, "
        "ma_target, ma_acquirer, buyback_large, sector_tailwind, sector_headwind\",\n"
        "  \"direction\": \"up\" or \"down\",\n"
        "  \"magnitude_bucket\": \"small\" (<1% mcap) | \"medium\" (1-5%) | \"large\" (>5% or category-defining),\n"
        "  \"counterparty\": \"name of customer/partner/target or null\",\n"
        "  \"estimated_tcv_usd\": number (USD) or null,\n"
        "  \"duration_months\": number or null,\n"
        "  \"thesis_bucket\": \"revolutionary\" (deal breaks a monopoly, "
        "validates a new architecture, or changes market structure) | "
        "\"demand_tailwind\" (picks-and-shovels / scale orders on structural wave) | "
        "\"mixed\" (elements of both — use freely) | \"neutral\" (genuinely can't tell),\n"
        "  \"rationale\": \"one sentence — why this matters for the thesis\"\n"
        "}\n\n"
        "TYPE RULES:\n"
        " - customer_win_major = a specific NAMED COUNTERPARTY has agreed "
        "to buy from / partner with the company. This applies to any "
        "named-customer contract regardless of industry narrative. If a "
        "specific counterparty is named, use customer_win_major rather "
        "than sector_tailwind.\n"
        " - sector_tailwind = industry-wide shift WITHOUT a specific "
        "counterparty (e.g. CHIPS Act, macro rate move).\n"
        " - Type must be one of the listed options exactly.\n\n"
        "OTHER RULES:\n"
        " - If the description is ambiguous (just 'Current report' or "
        "'Exhibits only'), use magnitude_bucket='small' and "
        "thesis_bucket='neutral'.\n"
        " - Do NOT invent a counterparty or TCV. If not stated, return null.\n"
        " - Bias toward 'revolutionary' or 'mixed' when a deal materially "
        "changes competitive structure (breaking a monopoly, legitimizing "
        "a new architecture, creating a new category)."
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-6",
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
    except Exception as e:
        print(f"  [{ticker}] Claude classification failed on {filing.get('accession')}: {e}")
        return None

    # Strip code fences if any.
    clean = content.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        return None

    parsed["date"] = filing.get("filing_date")
    parsed["source"] = "SEC EDGAR 8-K"
    parsed["url"] = filing.get("url")
    parsed["detected_by"] = "Catalyst-8K-Claude"
    return _sanitize_event(parsed)


def _event_in_window(ev: dict, cutoff_iso: str) -> bool:
    """Return True if the event date is on-or-after cutoff_iso, or unknown.

    Unknown dates pass (we trust Perplexity's implicit window) but an explicit
    date older than the cutoff is dropped. This catches Perplexity pulling in
    year-old events as "context".
    """
    d = (ev.get("date") or "").strip()
    if not d:
        return True  # no explicit date — let it pass
    # Accept YYYY-MM-DD. Reject malformed silently (treat as unknown = pass).
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", d)
    if not m:
        return True
    return d >= cutoff_iso


def _sanitize_event(e: dict) -> dict:
    """Normalize an event dict: drop unknown enum values, clamp strings."""
    # Type must be in taxonomy, else drop to neutral classification marker
    etype = (e.get("type") or "").strip()
    if etype not in TAXONOMY_IDS:
        etype = "sector_tailwind"  # neutral-ish fallback
    # Direction
    direction = e.get("direction")
    if direction not in ("up", "down"):
        direction = "up"
    # Magnitude bucket
    mag = (e.get("magnitude_bucket") or "").strip().lower()
    if mag not in MAGNITUDE_BUCKETS:
        mag = "small"
    # Thesis bucket
    thesis = (e.get("thesis_bucket") or "").strip().lower()
    if thesis not in THESIS_BUCKETS:
        thesis = "neutral"

    return {
        "summary": (e.get("summary") or "")[:280],
        "type": etype,
        "direction": direction,
        "magnitude_bucket": mag,
        "counterparty": e.get("counterparty") or None,
        "estimated_tcv_usd": e.get("estimated_tcv_usd"),
        "duration_months": e.get("duration_months"),
        "thesis_bucket": thesis,
        "date": e.get("date"),
        "source": e.get("source"),
        "url": e.get("url"),
        "rationale": (e.get("rationale") or "")[:280],
        "detected_by": e.get("detected_by") or "Catalyst",
    }


# ─────────────────────────────────────────────────────────────
# Main per-ticker routine
# ─────────────────────────────────────────────────────────────

def process_ticker(ticker: str, company: str, days: int = 90) -> dict:
    """Gather + classify catalysts for one ticker. Returns a signal row."""
    print(f"\n  → {ticker} ({company})")

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    # 1. SEC EDGAR 8-K pull
    filings = fetch_recent_8ks(ticker, days=days)
    print(f"    [8-K] {len(filings)} recent catalyst-relevant filings")

    edgar_events: list[dict] = []
    for filing in filings:
        enriched = _classify_8k_with_claude(filing, ticker, company) if ANTHROPIC_API_KEY else None
        if enriched is None:
            enriched = _classify_8k_rule_based(filing)
            enriched = _sanitize_event(enriched)
        edgar_events.append(enriched)
        # Small pause so we don't hammer the Anthropic API.
        if ANTHROPIC_API_KEY:
            time.sleep(0.4)

    # 2. Perplexity catalyst search
    pplx_events: list[dict] = []
    pplx_raw = perplexity_catalyst_search(ticker, company, days=days)
    pplx_citations: list = []
    if pplx_raw:
        parsed = pplx_raw.get("parsed") or {}
        pplx_citations = pplx_raw.get("citations") or []
        for raw_ev in (parsed.get("events") or [])[:8]:
            if not isinstance(raw_ev, dict):
                continue
            ev = _sanitize_event({**raw_ev, "detected_by": "Catalyst-Perplexity"})
            if not ev["summary"]:
                continue
            if not _event_in_window(ev, cutoff_iso):
                # Perplexity pulled in an old event as "context" — drop it.
                print(f"    [pplx] dropped stale event dated {ev.get('date')} "
                      f"< cutoff {cutoff_iso}: {ev['summary'][:80]}")
                continue
            pplx_events.append(ev)
    print(f"    [pplx] {len(pplx_events)} catalyst events")

    # 3. Merge + dedupe. Same deal reported by two outlets phrases differently
    #    ("Lumentum announced…" vs "Lumentum confirmed…"), so we also key on
    #    (event type + dollar amount + counterparty) to catch those. The
    #    cheaper 6-word prefix still catches near-identical wording.
    def _word_prefix(s: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", (s or "").lower())
        return " ".join(words[:6])

    def _numeric_key(ev: dict) -> str | None:
        """Signature keyed on type + rounded dollar amount + counterparty.

        Matches near-duplicates that differ in wording but reference the same
        underlying deal (same TCV, same customer).
        """
        tcv = ev.get("estimated_tcv_usd")
        cp = (ev.get("counterparty") or "").strip().lower() or None
        if tcv is None and cp is None:
            # Fall back to scanning the summary for a dollar figure.
            # Require a '$' prefix so we don't misread share counts
            # ("160 million shares") or time windows ("5 million hours") as TCV.
            m = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(billion|million|b|m)\b",
                          (ev.get("summary") or "").lower())
            if m:
                try:
                    val = float(m.group(1))
                    if m.group(2) in ("billion", "b"):
                        tcv = val * 1e9
                    else:
                        tcv = val * 1e6
                except ValueError:
                    tcv = None
        if tcv is None and cp is None:
            return None
        # Round TCV to 2 sig figs so $400M and $400M dedupe cleanly.
        tcv_key = f"{round(tcv, -int(max(0, len(str(int(tcv))) - 2)))}" if tcv else "-"
        return f"{ev.get('type', '?')}|{tcv_key}|{cp or '-'}"

    prefix_seen: set[str] = set()
    numeric_seen: set[str] = set()
    merged: list[dict] = []
    for ev in edgar_events + pplx_events:
        fp = _word_prefix(ev.get("summary", ""))
        nk = _numeric_key(ev)
        if fp and fp in prefix_seen:
            continue
        if nk and nk in numeric_seen:
            continue
        if fp:
            prefix_seen.add(fp)
        if nk:
            numeric_seen.add(nk)
        merged.append(ev)

    # 4. Decide overall signal direction
    up = sum(1 for e in merged if e["direction"] == "up")
    dn = sum(1 for e in merged if e["direction"] == "down")
    if up > dn + 1:
        signal = "bullish"
    elif dn > up + 1:
        signal = "bearish"
    else:
        signal = "neutral"

    # 5. Summary line for the dashboard
    if not merged:
        summary_str = "No material catalysts detected in the last window."
    else:
        top = sorted(
            merged,
            key=lambda e: {"large": 3, "medium": 2, "small": 1}.get(e["magnitude_bucket"], 1),
            reverse=True,
        )[:3]
        summary_str = " | ".join(
            f"{e['summary'][:110]} ({e['magnitude_bucket']}, {e['thesis_bucket']})"
            for e in top
        )

    return {
        "ticker": ticker,
        "scout": "Catalyst",
        "ai": "Claude+Perplexity" if (ANTHROPIC_API_KEY and PERPLEXITY_API_KEY) else (
            "Claude" if ANTHROPIC_API_KEY else "Perplexity" if PERPLEXITY_API_KEY else "Rules"
        ),
        "signal": signal,
        "summary": summary_str[:300],
        "timestamp": timestamp(),
        "data": {
            # `events` is the canonical key the analyst's
            # collect_events_from_signals walks — using it here means
            # catalyst events automatically flow into event_reasoner and
            # adjust the price target, just like news events.
            "events": merged,
            # Alias kept for backward-compat / UI convenience.
            "catalyst_events": merged,
            "edgar_count": len(edgar_events),
            "pplx_count": len(pplx_events),
            "citations": pplx_citations,
            "window_days": days,
        },
    }


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def _parse_cli() -> tuple[str | None, int]:
    ticker: str | None = None
    days = 90
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--ticker" and i + 1 < len(args):
            ticker = args[i + 1].upper()
            i += 2
        elif a == "--days" and i + 1 < len(args):
            try:
                days = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    return ticker, days


def main() -> list[dict]:
    print("=" * 60)
    print("  SCOUT: CATALYST / CONTRACT / ORDER DETECTOR")
    print("=" * 60)

    # When invoked standalone (CLI / test endpoint), no run_id has been set
    # by the pipeline runner. Manufacture one so Supabase writes succeed — the
    # run_id prefix makes standalone runs easy to filter out of analyst runs.
    if not get_run_id():
        standalone_id = (
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + "_catalyst_standalone"
        )
        set_run_id(standalone_id)

    target_ticker, days = _parse_cli()
    print(f"  Window: last {days} days")
    print(f"  Anthropic key: {'yes' if ANTHROPIC_API_KEY else 'no (rule-based 8-K fallback)'}")
    print(f"  Perplexity key: {'yes' if PERPLEXITY_API_KEY else 'no (8-K only)'}")

    watchlist = get_watchlist()
    if target_ticker:
        watchlist = [s for s in watchlist if s["ticker"].upper() == target_ticker]
        if not watchlist:
            print(f"\n  ✗ {target_ticker} not in watchlist — nothing to do.")
            return []

    print(f"  Stocks to scan: {len(watchlist)}")
    print("-" * 60)

    signals: list[dict] = []
    for stock in watchlist:
        sig = process_ticker(stock["ticker"], stock.get("name", ""), days=days)
        signals.append(sig)
        # Throttle between tickers — EDGAR + Perplexity both prefer it.
        time.sleep(0.8)

    save_signals("catalyst", signals)

    print("\n" + "=" * 60)
    print("  CATALYST SUMMARY")
    print("=" * 60)
    for s in signals:
        emoji = {"bullish": "🟢", "bearish": "🔴"}.get(s["signal"], "🟡")
        n_events = len(s["data"]["catalyst_events"])
        print(f"  {emoji} {s['ticker']:6s} | {n_events} events | {s['summary'][:90]}")

    return signals


if __name__ == "__main__":
    main()
