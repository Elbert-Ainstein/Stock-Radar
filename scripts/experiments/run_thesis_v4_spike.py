#!/usr/bin/env python3
"""
run_thesis_v4_spike.py — minimal V4 two-agent dialogue experiment

Per Hume's request 2026-05-10. Runs the V4 architecture as a research spike
to compare against V3.4.1's output (target $910 / BROKEN / 0% on MU).

This is NOT production. It's a 2-round experiment:
  Round 1: Agent A (Strategic) and Agent B (Tactical) run in parallel, blind to each other.
  Round 2: Each agent sees the other's Round 1 output and may revise.

No termination loop, no synthesizer, no Supabase write. Just the dialogue
captured to a markdown file for comparison with V3.4.1.

Usage:
    python scripts/run_thesis_v4_spike.py MU

Outputs:
    data/theses_v4_spike/<TICKER>_<TIMESTAMP>/
      ├── round1_strategic.md
      ├── round1_tactical.md
      ├── round2_strategic.md
      ├── round2_tactical.md
      └── comparison.md
"""
from __future__ import annotations
import os
import sys
import re
import json
from datetime import datetime, timezone
from pathlib import Path

# Reuse run_thesis.py infrastructure for consistency
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_thesis import (
    load_prompt_with_frontmatter,
    get_memory,
    format_prior_context,
    get_ir_metadata,
    _build_verified_financials_block,
    fill_placeholders,
    call_claude_with_search,
    extract_cited_domains,
    coverage_quality,
    load_allowed_domains,
    REPO_ROOT,
)
from finance_data import fetch_financials


def _load_v4_prompt(filename: str) -> tuple[dict, str]:
    """Load a v4 agent prompt and split YAML frontmatter from body."""
    p = REPO_ROOT / "scripts" / "prompts" / filename
    text = p.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            fm_text = text[4:end]
            body = text[end + 5:]
            try:
                import yaml
                fm = yaml.safe_load(fm_text) or {}
            except Exception:
                fm = {}
            return fm, body
    return {}, text


def run_v4_spike(ticker: str) -> Path:
    print(f"\n{'='*70}")
    print(f"V4 SPIKE — two-agent dialogue experiment on {ticker}")
    print(f"{'='*70}\n")

    # 1. Fetch financials (same as V3.4.1)
    print(f"[setup] fetching financials for {ticker}...")
    fin = fetch_financials(ticker)
    spot = fin.price or 0.0
    sector = getattr(fin, "sector", "") or ""
    print(f"  spot=${spot:.2f}, sector={sector}, source={fin.source}")

    meta = get_ir_metadata(ticker)
    print(f"  company={meta['company_name']!r}")

    memory_md = get_memory(ticker)
    memory_section = format_prior_context(memory_md) if memory_md else ""
    print(f"  memory: {len(memory_md) if memory_md else 0} chars")

    verified_block = _build_verified_financials_block(fin, currency=meta.get("currency", "USD"))
    domains = load_allowed_domains(ir_domain=meta.get("ir_domain", ""))

    # 2. Load both agent prompts
    _, strategic_body = _load_v4_prompt("thesis_v4_strategic.md")
    _, tactical_body = _load_v4_prompt("thesis_v4_tactical.md")

    common_kwargs = dict(
        ticker=ticker,
        company_name=meta["company_name"],
        exchange=meta["exchange"],
        currency=meta["currency"],
        price=f"{spot:.2f}",
        sector=sector or "Unknown",
        memory_section=memory_section,
        verified_financials=verified_block,
    )

    # 3. Output directory
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "data" / "theses_v4_spike" / f"{ticker}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[setup] outputs → {out_dir.relative_to(REPO_ROOT)}\n")

    # ─── ROUND 1 — PARALLEL BLIND ────────────────────────────────────
    print("[round 1] strategic agent (parallel, blind)...")
    a_prompt_r1 = fill_placeholders(strategic_body, **common_kwargs)
    a_result_r1 = call_claude_with_search(a_prompt_r1, domains)
    a_text_r1 = a_result_r1["text"]
    a_cited_r1 = extract_cited_domains(a_result_r1["raw_blocks"])
    print(f"  strategic R1: {len(a_text_r1)} chars, {len(a_cited_r1)} domains cited")
    (out_dir / "round1_strategic.md").write_text(a_text_r1, encoding="utf-8")

    print("\n[round 1] tactical agent (parallel, blind)...")
    b_prompt_r1 = fill_placeholders(tactical_body, **common_kwargs)
    b_result_r1 = call_claude_with_search(b_prompt_r1, domains)
    b_text_r1 = b_result_r1["text"]
    b_cited_r1 = extract_cited_domains(b_result_r1["raw_blocks"])
    print(f"  tactical R1: {len(b_text_r1)} chars, {len(b_cited_r1)} domains cited")
    (out_dir / "round1_tactical.md").write_text(b_text_r1, encoding="utf-8")

    # ─── ROUND 2 — CROSS-POLLINATED ──────────────────────────────────
    print("\n[round 2] strategic agent sees tactical's R1...")
    a_prompt_r2 = fill_placeholders(strategic_body, **common_kwargs)
    a_prompt_r2 += (
        "\n\n---\n## ROUND 2 — TACTICAL AGENT'S ROUND 1 OUTPUT\n\n"
        "The Tactical agent (Agent B) produced the following analysis in Round 1, "
        "which you did not see when producing your Round 1 output. Read it. "
        "You may revise your strategic position in light of Tactical's evidence — "
        "but only to the extent A's evidence directly contradicts a STRATEGIC "
        "assumption you made. You do NOT cross into tactical territory. End with "
        "STATE: AGREED if you accept the current shared position as final, "
        "STATE: PROPOSING if you've revised, or STATE: STUCK if you cannot reconcile.\n\n"
        + b_text_r1
    )
    a_result_r2 = call_claude_with_search(a_prompt_r2, domains)
    a_text_r2 = a_result_r2["text"]
    print(f"  strategic R2: {len(a_text_r2)} chars")
    (out_dir / "round2_strategic.md").write_text(a_text_r2, encoding="utf-8")

    print("\n[round 2] tactical agent sees strategic's R1...")
    b_prompt_r2 = fill_placeholders(tactical_body, **common_kwargs)
    b_prompt_r2 += (
        "\n\n---\n## ROUND 2 — STRATEGIC AGENT'S ROUND 1 OUTPUT\n\n"
        "The Strategic agent (Agent A) produced the following analysis in Round 1, "
        "which you did not see when producing your Round 1 output. Read it. "
        "You may widen or narrow your tactical conclusions if A provides new "
        "structural evidence (e.g., names a verified contract that justifies a "
        "wider multiple range) but you do NOT validate A's targets or sizing. "
        "Your conclusion remains tactical. End with STATE: AGREED if you accept "
        "the current shared position as final, STATE: PROPOSING if you've revised, "
        "or STATE: STUCK if you cannot reconcile.\n\n"
        + a_text_r1
    )
    b_result_r2 = call_claude_with_search(b_prompt_r2, domains)
    b_text_r2 = b_result_r2["text"]
    print(f"  tactical R2: {len(b_text_r2)} chars")
    (out_dir / "round2_tactical.md").write_text(b_text_r2, encoding="utf-8")

    # ─── EXTRACT FINAL STATES + KEY NUMBERS ──────────────────────────
    def _extract_state(text: str) -> str:
        m = re.search(r"STATE:\s*(AGREED|PROPOSING|STUCK)", text, re.IGNORECASE)
        return m.group(1).upper() if m else "?"

    def _extract_field(text: str, label: str) -> str | None:
        # scan for "label: value" or "label = value" or markdown variants
        patterns = [
            rf"{label}\s*:\s*(\$?[\d,]+(?:\.\d+)?)",
            rf"{label}\s*=\s*(\$?[\d,]+(?:\.\d+)?)",
            rf"\*\*{label}\*\*\s*:\s*(\$?[\d,]+(?:\.\d+)?)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    a_state_r2 = _extract_state(a_text_r2)
    b_state_r2 = _extract_state(b_text_r2)

    a_conviction = _extract_field(a_text_r2, "strategic conviction") or _extract_field(a_text_r2, "conviction")
    b_target = _extract_field(b_text_r2, "trade_target") or _extract_field(b_text_r2, "trade target")
    b_conviction = _extract_field(b_text_r2, "trade_conviction") or _extract_field(b_text_r2, "trade conviction")
    b_position = _extract_field(b_text_r2, "position_size_pct") or _extract_field(b_text_r2, "position size")
    b_buy_below = _extract_field(b_text_r2, "buy_below") or _extract_field(b_text_r2, "buy below")

    # ─── COMPARISON FILE ─────────────────────────────────────────────
    cmp_lines = [
        f"# V4 spike — {ticker} dialogue summary",
        f"",
        f"**Run:** {ts}  ",
        f"**Spot:** ${spot:.2f}  ",
        f"**Sector:** {sector}  ",
        f"**Source:** {fin.source}",
        f"",
        f"---",
        f"",
        f"## V4 spike outputs (Round 2 final)",
        f"",
        f"| Field | Strategic (A) | Tactical (B) |",
        f"|---|---|---|",
        f"| State | {a_state_r2} | {b_state_r2} |",
        f"| Conviction | {a_conviction or '(see file)'} | {b_conviction or '(see file)'} |",
        f"| Trade target | — (forbidden for A) | {b_target or '(see file)'} |",
        f"| Position size | — (forbidden for A) | {b_position or '(see file)'} |",
        f"| Buy below | — | {b_buy_below or '(see file)'} |",
        f"",
        f"## V3.4.1 reference (single-call, 2026-05-10 06:40)",
        f"",
        f"| Field | Value |",
        f"|---|---|",
        f"| thesis_target | $910 |",
        f"| conviction | BROKEN |",
        f"| position_size_pct | 0% |",
        f"",
        f"## Convergence check",
        f"",
        f"- Both AGREED? {'YES' if a_state_r2 == 'AGREED' and b_state_r2 == 'AGREED' else 'NO'}",
        f"- Either STUCK? {'YES' if a_state_r2 == 'STUCK' or b_state_r2 == 'STUCK' else 'NO'}",
        f"- V4 vs V3.4.1 trade target delta: see Tactical's `{b_target}` vs V3.4.1's $910",
        f"",
        f"## Files",
        f"",
        f"- `round1_strategic.md` — Agent A initial",
        f"- `round1_tactical.md` — Agent B initial",
        f"- `round2_strategic.md` — Agent A after seeing B",
        f"- `round2_tactical.md` — Agent B after seeing A",
        f"",
    ]
    (out_dir / "comparison.md").write_text("\n".join(cmp_lines), encoding="utf-8")

    print("\n" + "="*70)
    print("V4 SPIKE COMPLETE")
    print("="*70)
    print(f"Strategic state R2: {a_state_r2}")
    print(f"Tactical state R2: {b_state_r2}")
    print(f"Tactical trade target: {b_target}")
    print(f"Tactical trade conviction: {b_conviction}")
    print(f"Tactical position: {b_position}")
    print(f"\nFor comparison vs V3.4.1 ($910 / BROKEN / 0%), see:")
    print(f"  {out_dir.relative_to(REPO_ROOT)}/comparison.md")
    return out_dir


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/run_thesis_v4_spike.py <TICKER>")
        sys.exit(1)
    ticker = sys.argv[1].upper()
    run_v4_spike(ticker)
