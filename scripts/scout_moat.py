#!/usr/bin/env python3
"""
Scout: Moat / Differentiation Detector (Chain 2 of 10x scanner)
===============================================================

Job: answer the question

    "Does this company have structural competitive advantages that let it
     sustain above-average returns — and are those advantages widening,
     stable, or eroding?"

Why this scout matters
----------------------
Catalyst (Chain 1) tells us "a big deal happened". Moat (Chain 2) tells us
"and the company can defend it." The two signals together separate
revolutionary companies (moat + catalyst) from demand-wave companies
(catalyst only, moat is their suppliers' / customers' not their own) from
value traps (catalyst without moat).

User priority mapping:
  - Revolutionary DNA → moat via IP, proprietary architecture, or
    regulatory barrier that blocks substitutes. AMD's IP stack in MI450
    vs NVDA CUDA is the canonical live example.
  - Demand-tailwind DNA → moat via switching cost / qualification cycle
    (slower to capture but real). LITE's datacom certification process
    at hyperscalers is the canonical example.

Data sources (Stage 1)
----------------------
1. **Perplexity sonar search** — surfaces news coverage of share shifts,
   pricing actions, patent wins/expiries, qualification wins.
2. **Claude enrichment** — tightens classification, forces taxonomy
   compliance, calibrates thesis_bucket on market-structure evidence.

Downstream
----------
Each emitted event flows into event_reasoner via `data.events` (same key
catalyst uses). Thesis_bucket lets the ranker bias toward revolutionary
over demand_tailwind per user priority.

Usage
-----
    python scripts/scout_moat.py                  # all watchlist
    python scripts/scout_moat.py --ticker AMD     # one ticker
    python scripts/scout_moat.py --ticker LITE --days 180
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

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Allowed event_templates taxonomy IDs for moat events.
# NEW (Chain 2): ip_moat_win, market_share_gain, pricing_power_demonstrated,
# switching_cost_deepening, regulatory_moat, moat_erosion.
# Reused from existing taxonomy: competitive_threat (for bearish moat signals),
# regulatory_approval (when Perplexity surfaces product clearance instead of
# pure barrier evidence).
MOAT_TAXONOMY_IDS = {
    "ip_moat_win",
    "market_share_gain",
    "pricing_power_demonstrated",
    "switching_cost_deepening",
    "regulatory_moat",
    "moat_erosion",
    "competitive_threat",
    "regulatory_approval",
}

THESIS_BUCKETS = {"revolutionary", "demand_tailwind", "mixed", "neutral"}
MAGNITUDE_BUCKETS = {"small", "medium", "large"}


# ─────────────────────────────────────────────────────────────
# Perplexity: moat evidence search
# ─────────────────────────────────────────────────────────────

def _perplexity_raw_dump(ticker: str, company_name: str, category: str, query: str, days: int) -> tuple[str, list]:
    """Run a single Perplexity sonar query with web search. Returns (markdown, citations).

    We ask for markdown bullets rather than JSON — sonar is more reliable at
    free-form summarization than structured output. Claude then structures
    the dump into typed events.
    """
    if not PERPLEXITY_API_KEY:
        return "", []

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    system_prompt = (
        "You are a financial research assistant. Return concise markdown "
        f"bullets of the most relevant NEWS, PATENT GRANTS, REPORTS, or "
        f"ANNOUNCEMENTS matching the user's question — only events dated on "
        f"or after {cutoff_date}. If none exist, write 'No material events "
        f"in window.' Each bullet: one line, include date + source if "
        f"known. Do not speculate. Do not add introductions, summaries, or "
        f"caveats outside of the bullets."
    )
    user_prompt = (
        f"Topic: {category}\n"
        f"Company: {ticker} ({company_name})\n"
        f"Window: last {days} days (on or after {cutoff_date})\n\n"
        f"Question: {query}\n\n"
        f"Return up to 8 markdown bullets. If fewer are available, return "
        f"what you find. If nothing material happened, say so."
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
        print(f"  [{ticker}] pplx '{category}' failed: {e}")
        return "", []

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    citations = data.get("citations", []) or []
    return content, citations


def perplexity_moat_search(ticker: str, company_name: str, days: int = 180) -> dict | None:
    """Query Perplexity sonar across 3 moat categories, then let Claude
    structure the combined raw dump into typed events.

    Splitting into category-specific queries is more reliable than one
    mega-query because sonar's web-search grounding works per-call and
    it tends to return empty on over-constrained multi-category prompts.
    """
    if not PERPLEXITY_API_KEY:
        return None

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    # Multi-query dump: each category is a separate sonar call
    categories = [
        (
            "IP & patents",
            f"What patent grants, IP litigation outcomes, or patent-related "
            f"filings has {ticker} been involved in during the window?",
        ),
        (
            "Market share & pricing",
            f"What market-share data (vs named competitors) or pricing "
            f"power evidence (ASP increases, premium tier adoption) exists "
            f"for {ticker} during the window?",
        ),
        (
            "Architecture wins & qualifications",
            f"What hyperscaler, OEM, government, or industry architecture "
            f"wins, certifications, or multi-generation qualifications did "
            f"{ticker} announce during the window?",
        ),
    ]

    raw_dumps: list[str] = []
    all_citations: list = []
    for category, q in categories:
        dump, cits = _perplexity_raw_dump(ticker, company_name, category, q, days)
        if dump and dump.strip().lower() != "no material events in window.":
            raw_dumps.append(f"### {category}\n{dump.strip()}")
        all_citations.extend(cits)
        time.sleep(0.4)

    if not raw_dumps:
        return {"parsed": {"events": []}, "citations": all_citations[:6], "raw_content": ""}

    combined_dump = "\n\n".join(raw_dumps)

    # Second pass: ask sonar to structure the combined dump into typed events.
    # Doing the classification in a second call avoids the over-constrained
    # failure mode where sonar returns {} because it can't reconcile the
    # search results with the type schema.
    system_prompt = (
        "You are a financial research assistant surfacing moat evidence. "
        "Return ONLY valid JSON (no markdown, no commentary).\n\n"
        "Your job: find concrete, dated events that evidence the "
        "company's competitive moat widening or narrowing. Cast a wide "
        "net — return what exists, don't over-filter.\n\n"
        "Return this structure:\n"
        "{\n"
        "  \"events\": [\n"
        "    {\n"
        "      \"summary\": \"one sentence describing what happened\",\n"
        "      \"type\": \"ip_moat_win | market_share_gain | "
        "pricing_power_demonstrated | switching_cost_deepening | "
        "regulatory_moat | moat_erosion | competitive_threat | "
        "regulatory_approval\",\n"
        "      \"direction\": \"up\" | \"down\",\n"
        "      \"magnitude_bucket\": \"small\" | \"medium\" | \"large\",\n"
        "      \"counterparty\": \"incumbent / competitor / regulator name or null\",\n"
        "      \"estimated_share_bps\": number_or_null,\n"
        "      \"estimated_price_delta_pct\": number_or_null,\n"
        "      \"thesis_bucket\": \"revolutionary | demand_tailwind | mixed | neutral\",\n"
        "      \"date\": \"YYYY-MM-DD or null\",\n"
        "      \"source\": \"publication name or null\",\n"
        "      \"url\": \"source URL or null\",\n"
        "      \"rationale\": \"one sentence: why this matters for the moat\"\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"TIME WINDOW: Include events dated on or after {cutoff_date} only. "
        f"If you cannot tell the date, include the event with date=null.\n\n"
        "WHAT COUNTS AS A MOAT EVENT:\n"
        " - Patent grants / IP litigation outcomes (ip_moat_win or moat_erosion)\n"
        " - Market-share reports from IDC / JPR / Mercury / Gartner / "
        "Omdia / SEMI / IEA (market_share_gain or competitive_threat)\n"
        " - Successful price increases or ASP expansion "
        "(pricing_power_demonstrated)\n"
        " - Architecture / platform wins at named hyperscalers, OEMs, "
        "or governments — especially multi-generation commitments that "
        "lock customers in (switching_cost_deepening)\n"
        " - Certifications that block competitors: FAA TC, FDA BLA, "
        "defense qualification, CMS code (regulatory_moat)\n"
        " - Substitute tech demonstrated, patent expiries, commoditization, "
        "customer defection (moat_erosion or competitive_threat)\n\n"
        "WHAT DOESN'T COUNT:\n"
        " - Pure sell-side price target changes with no underlying event\n"
        " - Generic 'the company has a moat' analyst opinions with no data\n"
        " - One-off contract wins without evidence of lock-in (those are "
        "catalyst events, not moat events — skip them)\n\n"
        "THESIS BUCKET QUICK GUIDE (Claude will tighten this later, best-effort here):\n"
        " - revolutionary: structural advantage blocking substitutes "
        "(blocking IP, regulatory barrier, big share take from monopoly)\n"
        " - demand_tailwind: picks-and-shovels positioning on a wave "
        "(qualification wins, supply-chain lock-in)\n"
        " - mixed: both\n"
        " - neutral: undetermined\n\n"
        "OUTPUT: Return 3-6 events if evidence exists across these "
        "categories. Quality matters, but don't artificially limit to 1 "
        "when there's more evidence. Empty array only if the window is "
        "genuinely quiet across all 6 categories."
    )

    user_prompt = (
        f"Structure the following research dump about {ticker} "
        f"({company_name}) into typed moat events. Do not add events that "
        f"aren't in the dump. For each item in the dump that counts as a "
        f"moat event (per the categories in the system prompt), emit one "
        f"entry in the events array. Skip items that don't fit any moat "
        f"category (e.g. generic price-target commentary).\n\n"
        f"RAW DUMP:\n{combined_dump}"
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
                "max_tokens": 2500,
                "temperature": 0.1,
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [{ticker}] Perplexity moat structure pass failed: {e}")
        return None

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    try:
        clean = content.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        print(f"  [{ticker}] Structure pass returned non-JSON — skipping.")
        return None

    return {
        "parsed": parsed,
        "citations": all_citations[:6],
        "raw_content": content,
        "raw_dump": combined_dump,
    }


# ─────────────────────────────────────────────────────────────
# Claude enrichment pass (optional — tightens thesis classification)
# ─────────────────────────────────────────────────────────────

def _claude_enrich_moat(ticker: str, company: str, events: list[dict]) -> list[dict]:
    """Run events through Claude for tighter thesis_bucket / magnitude.

    Perplexity is reliable for finding evidence but sometimes defaults to
    'demand_tailwind' on events that actually evidence structural-advantage
    (e.g. a blocking patent win gets tagged demand_tailwind). Claude does
    a focused re-read of each event to ensure the classification matches
    the evidence.

    If Anthropic key is missing, return events unchanged.
    """
    if not ANTHROPIC_API_KEY or not events:
        return events

    prompt = (
        f"You are reclassifying moat events for {ticker} ({company}). "
        f"Return ONLY a JSON array — same length as input, same order, "
        f"same fields — but with tightened 'thesis_bucket', 'magnitude_bucket', "
        f"and 'rationale' fields. Preserve all other fields exactly.\n\n"
        f"INPUT EVENTS:\n{json.dumps(events, indent=2)}\n\n"
        "CLASSIFICATION GUIDANCE:\n"
        " - thesis_bucket='revolutionary' when the evidence points to a "
        "structural advantage that blocks substitutes at scale (IP in "
        "chokepoint, regulatory barrier with multi-year moat, share take "
        ">500bps from monopoly incumbent).\n"
        " - thesis_bucket='demand_tailwind' when the evidence points to "
        "sustained participation in a wave (qualification cycle completed, "
        "supply-chain positioning, incremental share take).\n"
        " - thesis_bucket='mixed' when both are evidenced. Use freely.\n"
        " - Do NOT downgrade revolutionary signals to demand_tailwind "
        "just because the company also has supply-chain positioning. "
        "Upgrade to mixed instead.\n"
        " - magnitude_bucket: small=<1% target Δ, medium=1-5%, large=>5% "
        "or category-defining.\n"
        " - rationale: one sentence explaining why the revised bucket fits.\n\n"
        "Output pure JSON array. No markdown fence, no commentary."
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
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
    except Exception as e:
        print(f"  [{ticker}] Claude moat enrichment failed: {e} — using raw pplx events")
        return events

    clean = content.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        revised = json.loads(clean)
    except json.JSONDecodeError:
        return events
    if not isinstance(revised, list) or len(revised) != len(events):
        # Shape mismatch — bail rather than misalign.
        return events

    out: list[dict] = []
    for orig, upd in zip(events, revised):
        if not isinstance(upd, dict):
            out.append(orig)
            continue
        merged = {**orig}
        for k in ("thesis_bucket", "magnitude_bucket", "rationale"):
            if k in upd and upd[k] is not None:
                merged[k] = upd[k]
        out.append(merged)
    return out


# ─────────────────────────────────────────────────────────────
# Normalization + filtering
# ─────────────────────────────────────────────────────────────

def _event_in_window(ev: dict, cutoff_iso: str) -> bool:
    """Drop events dated explicitly before cutoff. Unknown dates pass."""
    d = (ev.get("date") or "").strip()
    if not d:
        return True
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", d)
    if not m:
        return True
    return d >= cutoff_iso


def _sanitize_event(e: dict) -> dict:
    """Normalize a raw event dict: enum clamping, length caps, detected_by tag."""
    etype = (e.get("type") or "").strip()
    if etype not in MOAT_TAXONOMY_IDS:
        # Fallback to neutral-positive: an unrecognized type almost always
        # means Perplexity picked a catalyst-ish type. Downgrade rather than
        # silently accept a non-moat event.
        etype = "switching_cost_deepening"

    direction = e.get("direction")
    if direction not in ("up", "down"):
        # Default direction by type: erosion / threat are down, others up.
        direction = "down" if etype in ("moat_erosion", "competitive_threat") else "up"

    mag = (e.get("magnitude_bucket") or "").strip().lower()
    if mag not in MAGNITUDE_BUCKETS:
        mag = "small"

    thesis = (e.get("thesis_bucket") or "").strip().lower()
    if thesis not in THESIS_BUCKETS:
        thesis = "neutral"

    return {
        "summary": (e.get("summary") or "")[:280],
        "type": etype,
        "direction": direction,
        "magnitude_bucket": mag,
        "counterparty": e.get("counterparty") or None,
        "estimated_share_bps": e.get("estimated_share_bps"),
        "estimated_price_delta_pct": e.get("estimated_price_delta_pct"),
        "thesis_bucket": thesis,
        "date": e.get("date"),
        "source": e.get("source"),
        "url": e.get("url"),
        "rationale": (e.get("rationale") or "")[:280],
        "detected_by": e.get("detected_by") or "Moat-Perplexity",
    }


# ─────────────────────────────────────────────────────────────
# Main per-ticker routine
# ─────────────────────────────────────────────────────────────

def process_ticker(ticker: str, company: str, days: int = 180) -> dict:
    """Gather + classify moat evidence for one ticker. Returns a signal row."""
    print(f"\n  → {ticker} ({company})")

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    # 1. Perplexity moat search
    raw_events: list[dict] = []
    pplx_citations: list = []
    pplx_raw = perplexity_moat_search(ticker, company, days=days)
    if pplx_raw:
        parsed = pplx_raw.get("parsed") or {}
        pplx_citations = pplx_raw.get("citations") or []
        for raw_ev in (parsed.get("events") or [])[:6]:
            if not isinstance(raw_ev, dict):
                continue
            ev = _sanitize_event({**raw_ev, "detected_by": "Moat-Perplexity"})
            if not ev["summary"]:
                continue
            if not _event_in_window(ev, cutoff_iso):
                print(f"    [pplx] dropped stale event {ev.get('date')} "
                      f"< {cutoff_iso}: {ev['summary'][:80]}")
                continue
            raw_events.append(ev)
    print(f"    [pplx] {len(raw_events)} moat events")

    # 2. Claude enrichment pass (tightens thesis_bucket per user priority)
    enriched = _claude_enrich_moat(ticker, company, raw_events)
    # Re-sanitize post-enrichment in case Claude output something outside
    # the enum (defensive — shouldn't happen but cheap insurance).
    merged = [_sanitize_event({**ev, "detected_by": ev.get("detected_by")}) for ev in enriched]

    # 3. Dedupe on 6-word summary prefix (same story re-reported)
    seen: set[str] = set()
    deduped: list[dict] = []
    for ev in merged:
        key = " ".join(re.findall(r"[A-Za-z0-9]+", (ev.get("summary") or "").lower())[:6])
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(ev)
    merged = deduped

    # 4. Decide overall signal direction
    up = sum(1 for e in merged if e["direction"] == "up")
    dn = sum(1 for e in merged if e["direction"] == "down")
    if up > dn + 1:
        signal = "bullish"
    elif dn > up + 1:
        signal = "bearish"
    else:
        signal = "neutral"

    # 5. Moat strength score — simple aggregate for UI summary.
    #    Revolutionary beats mixed beats demand_tailwind beats neutral.
    bucket_weights = {"revolutionary": 3, "mixed": 2, "demand_tailwind": 1, "neutral": 0}
    mag_weights = {"large": 3, "medium": 2, "small": 1}
    strength = sum(
        bucket_weights.get(e["thesis_bucket"], 0)
        * mag_weights.get(e["magnitude_bucket"], 1)
        * (1 if e["direction"] == "up" else -1)
        for e in merged
    )

    # 6. Summary line for dashboard — lead with the strongest up-events.
    if not merged:
        summary_str = "No material moat evidence detected in the last window."
    else:
        up_events = [e for e in merged if e["direction"] == "up"]
        picks = sorted(
            up_events if up_events else merged,
            key=lambda e: (
                bucket_weights.get(e["thesis_bucket"], 0),
                mag_weights.get(e["magnitude_bucket"], 0),
            ),
            reverse=True,
        )[:3]
        summary_str = " | ".join(
            f"{e['summary'][:110]} ({e['magnitude_bucket']}, {e['thesis_bucket']})"
            for e in picks
        )

    return {
        "ticker": ticker,
        "scout": "Moat",
        "ai": "Claude+Perplexity" if (ANTHROPIC_API_KEY and PERPLEXITY_API_KEY) else (
            "Claude" if ANTHROPIC_API_KEY else "Perplexity" if PERPLEXITY_API_KEY else "Rules"
        ),
        "signal": signal,
        "summary": summary_str[:300],
        "timestamp": timestamp(),
        "data": {
            # `events` is the canonical key analyst.collect_events_from_signals
            # walks — dual-writing here means moat events flow into
            # event_reasoner and adjust targets alongside news + catalyst.
            "events": merged,
            # UI alias.
            "moat_events": merged,
            "strength_score": strength,
            "pplx_count": len(raw_events),
            "citations": pplx_citations,
            "window_days": days,
        },
    }


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def _parse_cli() -> tuple[str | None, int]:
    ticker: str | None = None
    days = 180  # moat evidence has longer shelf life than catalyst
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
    print("  SCOUT: MOAT / DIFFERENTIATION DETECTOR")
    print("=" * 60)

    # Standalone runs need a run_id so Supabase writes succeed.
    if not get_run_id():
        standalone_id = (
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + "_moat_standalone"
        )
        set_run_id(standalone_id)

    target_ticker, days = _parse_cli()
    print(f"  Window: last {days} days")
    print(f"  Anthropic key: {'yes' if ANTHROPIC_API_KEY else 'no (pplx-only)'}")
    print(f"  Perplexity key: {'yes' if PERPLEXITY_API_KEY else 'NO — scout cannot run without it'}")

    if not PERPLEXITY_API_KEY:
        print("  ✗ Perplexity key required for moat scout. Exiting.")
        return []

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
        time.sleep(0.8)

    save_signals("moat", signals)

    print("\n" + "=" * 60)
    print("  MOAT SUMMARY")
    print("=" * 60)
    for s in signals:
        emoji = {"bullish": "🟢", "bearish": "🔴"}.get(s["signal"], "🟡")
        n = len(s["data"]["moat_events"])
        strength = s["data"]["strength_score"]
        print(f"  {emoji} {s['ticker']:6s} | {n} events | strength={strength:+d} | {s['summary'][:80]}")

    return signals


if __name__ == "__main__":
    main()
