#!/usr/bin/env python3
"""
hypotheses.py — Lesson L7: a front door for human hypotheses.

The two best theses of 2026-07-02 (verified human aggregation; two-wave
robotics) came from the human, not the system. This module reads
`data/hypotheses/*.md` (one file per hypothesis, YAML frontmatter per
data/hypotheses/TEMPLATE.md) and formats the ACTIVE ones that bear on a
ticker for injection into that ticker's thesis run — where the analysis's
job is falsification, not origination.

Injection point: run_thesis appends the block to the [MEMORY_SECTION]
placeholder content (prior-context semantics; thesis_v3.md is NOT edited).
No hypothesis files → empty string → byte-identical prompt. The socratic
cohort key is unaffected (run_thesis.py is not a JUDGMENT_FILE and the
judgment prompts don't change).

Pure file reads; no network, no Supabase.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

HERE = Path(__file__).resolve().parent
HYPOTHESES_DIR = HERE.parent / "data" / "hypotheses"

# Injection budget: hypotheses are operator-curated so a hard cap is mostly a
# guard against an accidentally pasted novel.
MAX_BODY_CHARS = 6_000


def parse_hypothesis(text: str, name: str = "?") -> Optional[dict]:
    """Parse one hypothesis file. Returns None (with a stderr note) for
    files that don't parse — a malformed hypothesis must not kill a thesis
    run, but it must not be silently skipped either (L4)."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        print(f"  [hypotheses] {name}: no YAML frontmatter — skipped", file=sys.stderr)
        return None
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        print(f"  [hypotheses] {name}: bad frontmatter ({e}) — skipped", file=sys.stderr)
        return None
    if not isinstance(meta, dict):
        print(f"  [hypotheses] {name}: frontmatter is not a mapping — skipped", file=sys.stderr)
        return None
    tickers = meta.get("tickers") or []
    if isinstance(tickers, str):
        # `tickers: LITE, RKLB` without YAML brackets parses as one string —
        # split it, or the hypothesis silently never matches (review finding).
        tickers = [t for t in re.split(r"[,\s]+", tickers) if t]
    # Neutralize ALL-CAPS bracket tokens in the body: the hypothesis text is
    # injected BEFORE later placeholders are filled, so a literal
    # [VERIFIED_FINANCIALS] in operator prose would macro-expand inside the
    # hypotheses block (the socratic fill() splice class — review finding).
    body = re.sub(r"\[([A-Z][A-Z0-9_]{2,})\]", r"(\1)",
                  m.group(2).strip()[:MAX_BODY_CHARS])
    return {
        "name": name,
        "status": str(meta.get("status") or "").lower(),
        "tickers": [str(t).upper() for t in tickers if t],
        "horizon_years": meta.get("horizon_years"),
        "body": body,
    }


def load_hypotheses(directory: Path = HYPOTHESES_DIR) -> list[dict]:
    """All parseable hypotheses in the folder (any status), sorted by name.
    TEMPLATE.md participates but its status 'template' is never injected."""
    out = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.md")):
        h = parse_hypothesis(path.read_text(encoding="utf-8"), name=path.stem)
        if h:
            out.append(h)
    return out


def active_for_ticker(ticker: str, hypotheses: Optional[list[dict]] = None) -> list[dict]:
    """ACTIVE hypotheses that name this ticker (empty tickers list = none:
    a hypothesis must commit to names, per the dated-signpost discipline)."""
    if hypotheses is None:
        hypotheses = load_hypotheses()
    t = ticker.upper()
    return [h for h in hypotheses if h["status"] == "active" and t in h["tickers"]]


def format_hypotheses_block(ticker: str, hypotheses: Optional[list[dict]] = None) -> str:
    """Prompt block for one ticker's thesis run. Empty string when nothing
    is active for the ticker — the prompt stays byte-identical."""
    active = active_for_ticker(ticker, hypotheses)
    if not active:
        return ""
    lines = [
        "",
        "## OPERATOR HYPOTHESES (L7 intake — your job is FALSIFICATION)",
        "",
        "The operator has registered the hypotheses below for this ticker.",
        "Do NOT treat them as conclusions. For each: test it against the",
        "evidence you gather, state explicitly whether the named signatures",
        "and kill conditions are confirmed, unmet, or violated as of today,",
        "and let that verdict inform — never replace — your own analysis.",
        "",
    ]
    for h in active:
        lines.append(f"### Hypothesis: {h['name']}"
                     + (f" (plays out on a ~{h['horizon_years']}y clock)"
                        if h.get("horizon_years") else ""))
        lines.append(h["body"])
        lines.append("")
    return "\n".join(lines)
