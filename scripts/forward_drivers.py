#!/usr/bin/env python3
"""
forward_drivers.py — Extract forward-looking valuation drivers from Supabase signals.

Purpose
-------
The target engine (`target_engine.py`) is TTM-anchored: it derives growth and
margin drivers purely from yfinance historical data. This is defensible and
prevents "trust me, it'll grow 80%" fictions, but it also **ignores the
forward story** that the fundamentals and news scouts already captured during
the pipeline run.

Concretely, for a name like LITE, the scouts know:
  - Management is guiding 85%+ revenue growth
  - Next-quarter guidance midpoint is $805M (vs $665.5M last Q = +21% QoQ)
  - Moat is wide and strengthening (InP fabrication, Nvidia partnership)
  - TAM is $90B growing 20% CAGR, LITE gaining share

None of this reaches `compute_smart_defaults`. This module closes that gap.

Output contract
---------------
    load_forward_drivers(ticker) -> ForwardDrivers | None

ForwardDrivers is a plain dict (no dataclass to keep serialization simple)
with these optional keys, each of which may be None if unavailable:

    guided_rev_growth_y1       float   e.g. 0.85  (85% forward revenue growth)
    next_q_guidance_growth_yoy float   e.g. 0.64  (inferred from Q guidance)
    moat_type                  str     'none' | 'narrow' | 'wide'
    moat_score                 float   0-10
    moat_durability            str     'eroding' | 'stable' | 'strengthening'
    tam_growth_rate            float   e.g. 0.20 (20% TAM CAGR)
    share_trajectory           str     'losing' | 'stable' | 'gaining'
    business_quality_score     float   0-10
    management_score           float   0-10
    unit_economics_score       float   0-10
    guided_op_margin           float   e.g. 0.30 (guided non-GAAP op margin)
    sentiment                  str     'bearish' | 'neutral' | 'bullish'
    sentiment_confidence       str     'low' | 'medium' | 'high'
    source_summary             str     one-line diagnostic of what was found

This module is **intentionally forgiving**: any parse failure drops to None
and the engine degrades gracefully to pure TTM-anchored math. No exception
should ever propagate out of `load_forward_drivers`.
"""
from __future__ import annotations

import re
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _parse_pct(s: Any) -> float | None:
    """Extract a percentage (as fraction, e.g. 0.20) from a string or number.

    Accepts '20%', '20% CAGR', '20.5%', 20, 0.20. Returns None on failure.

    Numeric inputs:
      - Values <= 1.5 are treated as already-fractions (e.g. 0.85 → 0.85).
        This covers TAM-doubling / 100%+ growth cases down to fractions.
      - Values > 1.5 are treated as percent-scale (e.g. 85 → 0.85).

    Edge case: a numeric input of 1.2 meaning "120% growth" (TAM doubling)
    will be mis-read as 1.2-fraction, which is then clamped by downstream
    callers anyway. Acceptable tradeoff given that scouts almost always
    emit percent-scale for growth numbers (per the structured schema).
    """
    if s is None:
        return None
    if isinstance(s, (int, float)):
        v = float(s)
        if -1.5 <= v <= 1.5:
            return v  # already a fraction
        return v / 100
    if not isinstance(s, str):
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", s)
    if m:
        try:
            return float(m.group(1)) / 100
        except ValueError:
            return None
    # Bare number, e.g. "20" in contexts like "growth_rate": "20"
    m = re.search(r"(-?\d+(?:\.\d+)?)", s)
    if m:
        try:
            v = float(m.group(1))
            if -1.5 <= v <= 1.5:
                return v
            return v / 100
        except ValueError:
            return None
    return None


def _parse_dollar_range(s: str) -> tuple[float, float] | None:
    """Extract ($low, $high) in dollars from strings like '$780-830 million'.

    Returns (780e6, 830e6) for that example. Returns None if unparseable.
    """
    if not isinstance(s, str):
        return None
    # Match "$780-830M", "$780-830 million", "$1.2-1.4B", "$780M-$830M"
    m = re.search(
        r"\$?\s*(\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*\$?\s*(\d+(?:\.\d+)?)\s*"
        r"(million|billion|[mMbB])\b",
        s,
    )
    if not m:
        return None
    try:
        lo = float(m.group(1))
        hi = float(m.group(2))
        unit = m.group(3).lower()
        mult = 1e9 if unit.startswith("b") else 1e6
        return (lo * mult, hi * mult)
    except ValueError:
        return None


def _extract_guided_growth_from_text(texts: list[str]) -> float | None:
    """Mine explicit **management-guidance** growth phrases from narrative text.

    Only accepts phrases where management/company is the explicit subject AND
    the verb is forward-looking (guide/target/expect/project). Past-tense and
    generic "growing X%" are rejected because they match historical results,
    analyst speculation, and TAM growth — all of which produce bogus forward
    guides when fed to the engine. Earlier versions of this regex fired on
    "the AI server TAM is growing 40%" and lifted guided_rev_growth_y1 to 40%.

    Only patterns explicitly scoped to MANAGEMENT + REVENUE are kept:
      - "guidance for 85%+ growth"
      - "guiding 45-55% revenue growth"
      - "management expects revenue growth of 65%"
      - "company targets 40% revenue growth"

    Returns the MEAN of matches (not max), so one false positive does not
    dominate. Management guides often skew to floors, but that's a user-facing
    asymmetry we accept in exchange for robustness.
    """
    # Anchors that must appear near the numeric claim
    mgmt_anchors = (
        r"(?:management|company|CEO|CFO|guidance|guiding|guided|"
        r"raised\s+guidance|lifted\s+guidance|reaffirmed\s+guidance|"
        r"target(?:s|ing)?|expect(?:s|ing|ed)?|project(?:s|ing|ed)?|"
        r"anticipat(?:e|es|ing|ed))"
    )
    # Revenue / top-line qualifier — prevents matching TAM, margin, EPS growth
    topline = r"(?:revenue|top[- ]?line|sales|net\s+sales)"
    # Bounded gap between anchor and topline-growth phrase; excludes sentence
    # breaks but allows a qualifier like "FY2026" or "next year".
    gap = r"[^.!?\n]{0,50}?"
    # Analyst-disqualifier: if "analyst(s)" appears within 80 chars BEFORE
    # the match, this is analyst speculation, not management guidance.
    analyst_kill = r"(?<!\banalyst)(?<!\banalysts)"

    # Range delimiter — allow either "80-90%" or "80%-90%"
    rng = r"(\d+(?:\.\d+)?)\s*%?\s*[-–—]\s*(\d+(?:\.\d+)?)\s*%"
    pats = [
        # "guiding 45-55% revenue growth" / "guidance for 45-55% top-line growth"
        rf"{mgmt_anchors}\s+(?:for\s+|to\s+|of\s+|)?{rng}\s+(?:{topline}\s+)?growth",
        # "guidance for 85%+ revenue growth" / "targeting 85% top-line growth"
        rf"{mgmt_anchors}\s+(?:for\s+|to\s+|of\s+|)?(\d+(?:\.\d+)?)\s*%\+?\s+(?:{topline}\s+)?growth",
        # "management guided FY2026 revenue growth of 80-90%"
        rf"{mgmt_anchors}{gap}{topline}\s+growth\s+of\s+{rng}",
        # "management expects revenue growth of 65%"
        rf"{mgmt_anchors}{gap}{topline}\s+growth\s+of\s+(\d+(?:\.\d+)?)\s*%",
        # "revenue growth guidance of 45-55%"   (guidance is the noun)
        rf"{topline}\s+growth\s+guidance\s+of\s+{rng}",
        rf"{topline}\s+growth\s+guidance\s+of\s+(\d+(?:\.\d+)?)\s*%",
    ]
    matches: list[float] = []
    for t in texts:
        if not t or not isinstance(t, str):
            continue
        for p in pats:
            for m in re.finditer(p, t, flags=re.IGNORECASE):
                # Analyst-disqualifier: reject if "analyst(s)" appears within
                # 80 chars before the match.
                preceding = t[max(0, m.start() - 80): m.start()].lower()
                if "analyst" in preceding:
                    continue
                # Past-tense disqualifier: reject if "grew", "rose", "reported"
                # appears as a verb in the 30 chars preceding the number.
                near = t[max(0, m.start() - 30): m.start()].lower()
                if any(w in near for w in (" grew ", " rose ", " reported ", " posted ", " delivered ")):
                    continue
                try:
                    if len(m.groups()) >= 2 and m.group(2):
                        lo = float(m.group(1))
                        hi = float(m.group(2))
                        matches.append((lo + hi) / 2 / 100)
                    else:
                        matches.append(float(m.group(1)) / 100)
                except (ValueError, IndexError):
                    continue
    if not matches:
        return None
    # Clamp to sensible bounds — no company grows 500% sustainably
    matches = [max(-0.30, min(2.0, m)) for m in matches]
    # Mean (not max) — robust to one outlier false positive.
    return sum(matches) / len(matches)


def _extract_guidance_from_events(
    events: list[dict],
    ttm_rev: float | None,
    prior_year_q_rev: float | None = None,
) -> float | None:
    """Extract next-quarter guidance midpoint and infer YoY growth.

    If events contain an entry with a $X-Y M/B range (typical of earnings
    guidance), we take the midpoint and compare to the **same quarter one year
    prior** to get a real YoY growth rate. `prior_year_q_rev` is the correct
    denominator — it handles seasonality. `ttm_rev/4` is only used as a last
    resort and is flagged in the source summary as imprecise.
    """
    if not events or not isinstance(events, list):
        return None
    # Prefer prior-year-Q (handles seasonality); fall back to TTM/4 if unavailable.
    if prior_year_q_rev and prior_year_q_rev > 0:
        denom = prior_year_q_rev
    elif ttm_rev and ttm_rev > 0:
        denom = ttm_rev / 4
    else:
        return None
    best: float | None = None
    for e in events:
        if not isinstance(e, dict):
            continue
        t = (e.get("type") or "").lower()
        if "guidance" not in t and "earnings" not in t:
            continue
        summary = e.get("summary") or ""
        rng = _parse_dollar_range(summary)
        if rng is None:
            continue
        mid = (rng[0] + rng[1]) / 2
        growth = mid / denom - 1
        growth = max(-0.30, min(1.5, growth))
        if best is None or growth > best:
            best = growth
    return best


# ---------------------------------------------------------------------------
# Signal extractors — per-scout
# ---------------------------------------------------------------------------
def _from_fundamentals_signal(data: dict) -> dict[str, Any]:
    """Extract drivers from a fundamentals-scout signal row's `data` field.

    Expects `data.analysis` to be a dict with the structure emitted by
    scout_fundamentals.py (overall / tam_analysis / moat_analysis /
    revenue_analysis / management_analysis / unit_economics).
    """
    out: dict[str, Any] = {}
    a = data.get("analysis") or {}
    if not isinstance(a, dict):
        return out

    overall = a.get("overall") or {}
    tam = a.get("tam_analysis") or {}
    moat = a.get("moat_analysis") or {}
    rev_a = a.get("revenue_analysis") or {}
    mgmt = a.get("management_analysis") or {}
    ue = a.get("unit_economics") or {}

    # Moat
    moat_type = (moat.get("moat_type") or "").lower()
    if moat_type in ("none", "narrow", "wide"):
        out["moat_type"] = moat_type
    ms = moat.get("moat_score")
    if isinstance(ms, (int, float)):
        out["moat_score"] = float(ms)
    dur = (moat.get("moat_durability") or "").lower()
    if dur in ("eroding", "stable", "strengthening"):
        out["moat_durability"] = dur

    # TAM
    out["tam_growth_rate"] = _parse_pct(tam.get("market_growth_rate"))
    traj = (tam.get("share_trajectory") or "").lower()
    if traj in ("losing", "stable", "gaining"):
        out["share_trajectory"] = traj
    # TAM size in dollars: e.g. "$90B" or "$90 billion"
    tam_str = tam.get("tam_size") or ""
    if isinstance(tam_str, str):
        m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*(B|billion|T|trillion|M|million)", tam_str, flags=re.IGNORECASE)
        if m:
            try:
                v = float(m.group(1))
                unit = m.group(2).lower()[0]
                mult = {"t": 1e12, "b": 1e9, "m": 1e6}.get(unit, 0)
                if mult:
                    out["tam_size_usd"] = v * mult
            except ValueError:
                pass
    share = tam.get("current_market_share_pct")
    if isinstance(share, (int, float)):
        out["current_market_share_pct"] = float(share)

    # Quality scores
    for k_src, k_dst in (
        ("business_quality_score", "business_quality_score"),
        ("unit_economics_score", "unit_economics_score"),
    ):
        v = (overall.get(k_src) if k_src == "business_quality_score" else ue.get(k_src))
        if isinstance(v, (int, float)):
            out[k_dst] = float(v)
    mgmt_score = mgmt.get("management_score")
    if isinstance(mgmt_score, (int, float)):
        out["management_score"] = float(mgmt_score)

    # Operating margin: fundamentals only reports gross_margin_pct + op_margin
    # sometimes; not typically a forward guide. Skip here — picked up from
    # news events if present.

    # ---- STRUCTURED forward guidance (preferred over regex parsing) ----
    # scout_fundamentals now emits a `forward_guidance` block with explicit
    # numeric fields backed by verbatim quotes. Prefer this over regex-mining
    # the narrative — it's MUCH less hallucination-prone because the scout
    # refuses to populate a field without a management-statement source.
    fg = a.get("forward_guidance") or {}
    if isinstance(fg, dict):
        v = fg.get("guided_revenue_growth_y1_pct")
        if isinstance(v, (int, float)) and fg.get("guided_revenue_growth_y1_source"):
            # Pct → fraction if >1.5 (scouts return e.g. 85, we want 0.85)
            frac = v / 100 if v > 1.5 else v
            if 0 < frac < 2.0:
                out["structured_guided_rev_growth_y1"] = float(frac)
                out["structured_guidance_source"] = fg.get("guided_revenue_growth_y1_source")
                out["structured_guidance_confidence"] = fg.get("guidance_confidence")
        op = fg.get("guided_op_margin_pct")
        if isinstance(op, (int, float)) and fg.get("guided_op_margin_source"):
            frac = op / 100 if op > 1.5 else op
            if 0 < frac < 0.85:
                out["guided_op_margin"] = float(frac)
                out["guided_op_margin_source"] = fg.get("guided_op_margin_source")

    # Signal + narrative text for growth mining
    sig = (overall.get("signal") or "").lower()
    if sig in ("bearish", "neutral", "bullish"):
        out["sentiment"] = sig

    # Collect narrative blobs for growth-rate mining
    narratives: list[str] = []
    for k in ("bull_case", "bear_case", "one_line_thesis"):
        v = overall.get(k)
        if isinstance(v, str):
            narratives.append(v)
    rb = rev_a.get("revenue_breakdown") or []
    if isinstance(rb, list):
        for seg in rb:
            if not isinstance(seg, dict):
                continue
            # revenue_breakdown[i].growth_rate is an explicit growth signal,
            # but it's a per-segment rate. Capture the highest as a forward
            # hint for the fastest-growing segment.
            gr = _parse_pct(seg.get("growth_rate"))
            if gr is not None:
                out.setdefault("_segment_growth_rates", []).append(gr)

    narr_growth = _extract_guided_growth_from_text(narratives)
    if narr_growth is not None:
        out["_narrative_growth"] = narr_growth

    return out


def _from_news_signal(
    data: dict,
    ttm_rev: float | None,
    prior_year_q_rev: float | None = None,
) -> dict[str, Any]:
    """Extract drivers from a news-scout signal row's `data` field.

    Uses `parsed_analysis` (sentiment, key_events, summary) and the raw
    `events` list (structured events with typed entries like
    earnings_beat_raise that carry guidance dollar ranges).
    """
    out: dict[str, Any] = {}
    pa = data.get("parsed_analysis") or {}
    if isinstance(pa, dict):
        sentiment = (pa.get("sentiment") or "").lower()
        if sentiment in ("bearish", "neutral", "bullish"):
            out["sentiment"] = sentiment
        conf = (pa.get("confidence") or "").lower()
        if conf in ("low", "medium", "high"):
            out["sentiment_confidence"] = conf

        # ---- STRUCTURED forward guidance from news scout (preferred path) ----
        fg = pa.get("forward_guidance") or {}
        if isinstance(fg, dict):
            v = fg.get("guided_revenue_growth_y1_pct")
            if isinstance(v, (int, float)) and fg.get("guided_revenue_growth_y1_source"):
                frac = v / 100 if v > 1.5 else v
                if 0 < frac < 2.0:
                    out["structured_guided_rev_growth_y1"] = float(frac)
                    out["structured_guidance_source"] = fg.get("guided_revenue_growth_y1_source")
                    out["structured_guidance_confidence"] = fg.get("guidance_confidence")
            op = fg.get("guided_op_margin_pct")
            if isinstance(op, (int, float)) and fg.get("guided_op_margin_source"):
                frac = op / 100 if op > 1.5 else op
                if 0 < frac < 0.85:
                    out["guided_op_margin"] = float(frac)
                    out["guided_op_margin_source"] = fg.get("guided_op_margin_source")
            # Next-Q revenue: prefer explicit scout-emitted dollars over event-summary regex
            lo = fg.get("guided_next_q_revenue_low_usd")
            hi = fg.get("guided_next_q_revenue_high_usd")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > 0 and hi >= lo:
                out["_next_q_guidance_range_usd"] = (float(lo), float(hi))
                out["_next_q_guidance_source"] = fg.get("guided_next_q_revenue_source")
        # Mine key_events + summary for guidance phrases
        key_events = pa.get("key_events") or []
        texts: list[str] = []
        if isinstance(key_events, list):
            texts.extend(str(k) for k in key_events if k)
        summary = pa.get("summary")
        if isinstance(summary, str):
            texts.append(summary)
        narr_growth = _extract_guided_growth_from_text(texts)
        if narr_growth is not None:
            out["_narrative_growth"] = narr_growth

        # Non-GAAP op margin guidance phrasing: "non-GAAP operating margin of 30-31%"
        for t in texts:
            m = re.search(
                r"(?:non[- ]GAAP\s+)?(?:operating|op)\s+margin\s+(?:of\s+|at\s+)?"
                r"(\d+(?:\.\d+)?)\s*(?:%)?\s*(?:[-–—]\s*(\d+(?:\.\d+)?)\s*%?)?",
                t, flags=re.IGNORECASE,
            )
            if m:
                try:
                    lo = float(m.group(1))
                    hi = float(m.group(2)) if m.group(2) else lo
                    # Bound to plausible margin range (negative to 100%)
                    mid = (lo + hi) / 2
                    if 0 < mid < 100:
                        out["guided_op_margin"] = mid / 100
                        break
                except (ValueError, IndexError):
                    continue

    # Events: extract guidance ranges + forward op margin
    events = data.get("events") or []
    # Prefer structured scout-emitted $ range over event-summary regex
    sg = out.pop("_next_q_guidance_range_usd", None)
    if sg and (prior_year_q_rev or ttm_rev):
        mid = (sg[0] + sg[1]) / 2
        denom = prior_year_q_rev if (prior_year_q_rev and prior_year_q_rev > 0) else (ttm_rev / 4 if ttm_rev else 0)
        if denom > 0:
            out["next_q_guidance_growth_yoy"] = max(-0.30, min(1.5, mid / denom - 1))
    else:
        ev_growth = _extract_guidance_from_events(events, ttm_rev, prior_year_q_rev)
        if ev_growth is not None:
            out["next_q_guidance_growth_yoy"] = ev_growth

    # Op-margin guidance often sits in event summaries, e.g.
    #   "guided Q3 FY2026 ... non-GAAP operating margin of 30-31%"
    if isinstance(events, list) and "guided_op_margin" not in out:
        for e in events:
            if not isinstance(e, dict):
                continue
            s = e.get("summary") or ""
            if not isinstance(s, str):
                continue
            m = re.search(
                r"(?:non[- ]GAAP\s+)?(?:operating|op)\s+margin\s+(?:of\s+|at\s+)?"
                r"(\d+(?:\.\d+)?)\s*%?\s*(?:[-–—]\s*(\d+(?:\.\d+)?)\s*%)?",
                s, flags=re.IGNORECASE,
            )
            if m:
                try:
                    lo = float(m.group(1))
                    hi = float(m.group(2)) if m.group(2) else lo
                    mid = (lo + hi) / 2
                    if 5 < mid < 80:
                        out["guided_op_margin"] = mid / 100
                        break
                except (ValueError, IndexError):
                    continue

    return out


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------
def load_forward_drivers(
    ticker: str,
    ttm_rev: float | None = None,
    prior_year_q_rev: float | None = None,
) -> dict[str, Any] | None:
    """Load all available forward-looking drivers for `ticker` from Supabase.

    Combines fundamentals scout + news scout signals into a single dict.
    Returns None if Supabase is unreachable or the ticker has no signals.

    `ttm_rev` is used when no better prior-quarter anchor is available.
    `prior_year_q_rev` (the revenue from the quarter 4 quarters ago) is the
    correct denominator for next-Q guidance YoY growth and should be passed
    whenever quarterly data is available — it handles seasonality correctly.
    """
    try:
        from supabase_helper import get_client
        sb = get_client()
    except Exception as e:
        print(f"  [forward_drivers] supabase unavailable: {e}", file=sys.stderr)
        return None

    try:
        # Pull ALL recent signals for this ticker; we'll match by shape.
        r = (
            sb.table("signals")
            .select("data, created_at")
            .eq("ticker", ticker.upper())
            .order("created_at", desc=True)
            .limit(25)
            .execute()
        )
    except Exception as e:
        print(f"  [forward_drivers] {ticker}: signals query failed: {e}", file=sys.stderr)
        return None

    if not r.data:
        return None

    merged: dict[str, Any] = {}
    sources: list[str] = []

    # ---- Merge strategy by metric type ----
    #
    # TAKE-MAX: metrics where the maximum IS definitionally correct.
    # TAM growth rate = best-case addressable market; business quality = peak
    # assessment. Higher is a legitimate update, not a bias.
    _TAKE_MAX_KEYS = {
        "tam_growth_rate",
        "business_quality_score",
    }
    #
    # LATEST-TIMESTAMP-WINS: guidance metrics where management may revise
    # downward. Under take-max, a guidance cut from 20% to 15% was silently
    # ignored (max(20,15)=20), creating a structural bullish bias.
    # Since rows are ordered by created_at DESC, setdefault keeps the newest
    # signal's value and ignores older ones — which is correct.
    _LATEST_WINS_KEYS = {
        "guided_op_margin",
        "guided_rev_growth_y1",
        "structured_guided_rev_growth_y1",
    }
    #
    # Track merge conflicts for auditability
    _merge_conflicts: list[str] = []

    for row in r.data:
        d = row.get("data") or {}
        if not isinstance(d, dict):
            continue
        # Fundamentals-scout shape
        if "analysis" in d and "citations" in d and isinstance(d["analysis"], dict):
            try:
                parsed = _from_fundamentals_signal(d)
                if parsed:
                    sources.append("fundamentals")
                    ts = row.get("created_at", "?")
                    for k, v in parsed.items():
                        if v is None:
                            continue
                        if k in _LATEST_WINS_KEYS and isinstance(v, (int, float)):
                            # Latest-timestamp-wins: first value seen (DESC order = newest) wins.
                            # Log when a superseded value differs — may indicate a guidance revision.
                            existing = merged.get(k)
                            if existing is None:
                                merged[k] = float(v)
                            elif isinstance(existing, (int, float)) and abs(existing - float(v)) > 0.001:
                                _merge_conflicts.append(
                                    f"{k}: kept {existing:.4f} (newer), skipped {float(v):.4f} from fundamentals@{ts}"
                                )
                        elif k in _TAKE_MAX_KEYS and isinstance(v, (int, float)):
                            existing = merged.get(k)
                            if isinstance(existing, (int, float)):
                                merged[k] = max(existing, float(v))
                            else:
                                merged[k] = float(v)
                        else:
                            merged.setdefault(k, v)
            except Exception as e:
                print(f"  [forward_drivers] {ticker}: fundamentals parse failed: {e}", file=sys.stderr)
            continue
        # News-scout shape
        if "events" in d and "parsed_analysis" in d:
            try:
                parsed = _from_news_signal(d, ttm_rev, prior_year_q_rev)
                if parsed:
                    sources.append("news")
                    ts = row.get("created_at", "?")
                    for k, v in parsed.items():
                        if v is None:
                            continue
                        if k in _LATEST_WINS_KEYS and isinstance(v, (int, float)):
                            existing = merged.get(k)
                            if existing is None:
                                merged[k] = float(v)
                            elif isinstance(existing, (int, float)) and abs(existing - float(v)) > 0.001:
                                _merge_conflicts.append(
                                    f"{k}: kept {existing:.4f} (newer), skipped {float(v):.4f} from news@{ts}"
                                )
                        elif k in _TAKE_MAX_KEYS and isinstance(v, (int, float)):
                            existing = merged.get(k)
                            if isinstance(existing, (int, float)):
                                merged[k] = max(existing, float(v))
                            else:
                                merged[k] = float(v)
                        else:
                            merged.setdefault(k, v)
            except Exception as e:
                print(f"  [forward_drivers] {ticker}: news parse failed: {e}", file=sys.stderr)
            continue

    # ---- Consolidate forward growth signals ----
    # Prefer structured scout field `structured_guided_rev_growth_y1` when
    # present (scouts now emit this as an explicit numeric field backed by a
    # verbatim management quote). Fall back to regex-parsed narrative growth
    # only if no structured field was provided.
    #
    # Within the fallback path we average the available signals (not max),
    # because max lets one false-positive regex match dominate. For LITE the
    # signals are all consistent; for a noisy ticker, averaging prevents one
    # over-read from producing a blowout.
    structured = merged.get("structured_guided_rev_growth_y1")
    if isinstance(structured, (int, float)) and 0 < structured < 2.0:
        merged["guided_rev_growth_y1"] = float(structured)
        merged["guided_rev_growth_y1_source"] = "scout_structured"
    else:
        growth_candidates: list[float] = []
        for k in ("next_q_guidance_growth_yoy", "_narrative_growth"):
            v = merged.get(k)
            if isinstance(v, (int, float)) and v > 0:
                growth_candidates.append(float(v))
        segs = merged.get("_segment_growth_rates") or []
        if segs:
            # Median of the top-3 segments (not max) — avoids the one-segment
            # hyper-growth outlier dominating whole-company guidance.
            top = sorted(segs, reverse=True)[:3]
            if top:
                top_sorted = sorted(top)
                growth_candidates.append(top_sorted[len(top_sorted) // 2])
        if growth_candidates:
            merged["guided_rev_growth_y1"] = sum(growth_candidates) / len(growth_candidates)
            merged["guided_rev_growth_y1_source"] = "regex_mean"

    # Clean private scratch keys
    merged.pop("_segment_growth_rates", None)
    merged.pop("_narrative_growth", None)

    if not merged:
        return None

    # Log merge conflicts for auditability (guidance cuts, stale signals, etc.)
    if _merge_conflicts:
        for conflict in _merge_conflicts:
            print(f"  [forward_drivers] {ticker}: MERGE CONFLICT — {conflict}", file=sys.stderr)
        merged["_merge_conflicts"] = _merge_conflicts

    merged["source_summary"] = ", ".join(sorted(set(sources))) or "none"
    return merged


def _format_forward_drivers(fd: dict[str, Any]) -> str:
    """Render a one-line diagnostic for logging."""
    parts: list[str] = []
    gg = fd.get("guided_rev_growth_y1")
    if gg is not None:
        parts.append(f"g1={gg:.0%}")
    moat = fd.get("moat_type")
    md = fd.get("moat_durability")
    if moat or md:
        parts.append(f"moat={moat}/{md}")
    bq = fd.get("business_quality_score")
    if bq is not None:
        parts.append(f"bq={bq:.1f}")
    tam = fd.get("tam_growth_rate")
    if tam is not None:
        parts.append(f"tam_g={tam:.0%}")
    om = fd.get("guided_op_margin")
    if om is not None:
        parts.append(f"op_mgn={om:.0%}")
    src = fd.get("source_summary")
    if src:
        parts.append(f"src=[{src}]")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import json
    tickers = sys.argv[1:] or ["LITE", "SNDK", "NVDA", "AAPL"]
    for t in tickers:
        fd = load_forward_drivers(t)
        print(f"\n===== {t} =====")
        if fd is None:
            print("  (no forward drivers available)")
        else:
            print(json.dumps(fd, indent=2, default=str))
            print("  summary:", _format_forward_drivers(fd))
