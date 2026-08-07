#!/usr/bin/env python3
"""
watched_facts.py — signal discipline for the judgment panel.

Operator directive (2026-07-28): "don't let random news get to you. Focus on
the facts that matter. For example for MU look closely on AI supply chain
demand and orders from data centers."

`config/watched_facts.yaml` declares, per ticker, the specific causal chain
the thesis rides on and the categories of noise that may not be cited as
evidence. This module loads it and renders the [WATCHED_FACTS] block every
panelist receives.

Three properties matter:

1. **Absence is declared, never silent.** A ticker with no spec gets an
   explicit "NO FACT SPEC ON FILE" block instructing the analyst to say so and
   propose one — the failure mode this module exists to prevent is an analyst
   quietly reverting to headline-grazing.
2. **It says WHAT to look at, never what the answer is.** Answers come from
   runs; putting them here would seed the analysis with its own conclusion
   (design rule 1: no static numbers).
3. **The noise list is binding.** Categories listed under `noise` are
   inadmissible as evidence for a verdict, however loud the headline.

Pure file reads; no network, no Supabase.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import yaml

HERE = Path(__file__).resolve().parent
FACTS_PATH = HERE.parent / "config" / "watched_facts.yaml"

# Rendered when a ticker has no spec — loud by construction.
NO_SPEC_BLOCK = """### WATCHED FACTS — NONE ON FILE for {ticker}

No fact specification exists for this ticker in config/watched_facts.yaml.

This is a GAP, not permission to graze headlines. You must:
  - state plainly in your reasoning that you worked without a fact spec;
  - ground every claim in a filing, transcript, or dated company disclosure
    anyway — the standard does not drop because the file is missing;
  - populate `proposed_facts` with the 3-5 questions that WOULD decide this
    name, each answerable with a number or a date.
"""


def load_watched_facts(path: Path = FACTS_PATH) -> dict[str, Any]:
    """Parse the spec file. A malformed file is loud and empty — never a
    silent pass-through that would let every ticker run unconstrained."""
    if not path.exists():
        print(f"  [watched_facts] WARN: {path} missing — panel runs without "
              f"fact discipline", file=sys.stderr, flush=True)
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"  [watched_facts] WARN: {path} unparseable ({e}) — panel runs "
              f"without fact discipline", file=sys.stderr, flush=True)
        return {}
    if not isinstance(data, dict):
        print(f"  [watched_facts] WARN: {path} is not a mapping — ignored",
              file=sys.stderr, flush=True)
        return {}
    return data


def spec_for_ticker(ticker: str, specs: Optional[dict] = None) -> Optional[dict]:
    """The spec for one ticker (case-insensitive), or None."""
    specs = load_watched_facts() if specs is None else specs
    if not ticker:
        return None
    upper = ticker.upper()
    for key, val in specs.items():
        if str(key).upper() == upper and isinstance(val, dict):
            return val
    return None


def format_watched_facts(ticker: str, specs: Optional[dict] = None) -> str:
    """Render the [WATCHED_FACTS] block for one ticker.

    Never returns empty: a missing spec renders NO_SPEC_BLOCK so the prompt
    carries the gap instead of hiding it (fill() is strict — an empty string
    here would raise, which is also acceptable, but a declared gap is more
    useful than a crash mid-panel)."""
    spec = spec_for_ticker(ticker, specs)
    if spec is None:
        return NO_SPEC_BLOCK.format(ticker=ticker.upper())

    lines: list[str] = [f"### WATCHED FACTS — {ticker.upper()}", ""]
    engine = str(spec.get("engine") or "").strip()
    if engine:
        lines += ["**What actually decides this name:**", engine, ""]

    facts = spec.get("facts") or []
    if facts:
        lines.append("**The facts that matter.** Answer each with a NUMBER or a "
                     "DATE from a filing, transcript, or dated company "
                     "disclosure. If you cannot find one, DECLARE it unknown — "
                     "an unanswerable fact is itself information, and guessing "
                     "around it is the failure this list exists to prevent.")
        lines.append("")
        for f in facts:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("id") or "?")
            q = str(f.get("question") or "").strip()
            why = str(f.get("why") or "").strip()
            src = f.get("sources") or []
            cadence = str(f.get("cadence") or "").strip()
            lines.append(f"- **{fid}** — {q}")
            if why:
                lines.append(f"  - why it matters: {why}")
            if src:
                lines.append(f"  - acceptable sources: {', '.join(str(s) for s in src)}"
                             + (f" · cadence: {cadence}" if cadence else ""))
        lines.append("")

    noise = spec.get("noise") or []
    if noise:
        lines.append("**INADMISSIBLE AS EVIDENCE.** The following may not support "
                     "any verdict, however loud the headline. You may mention "
                     "one only to explain why it does NOT change the answer:")
        for n in noise:
            lines.append(f"  - {n}")
        lines.append("")

    lines.append("**Binding rule:** every claim in your output must trace to a "
                 "fact above or to an entry you add to `proposed_facts` with a "
                 "reason. A claim that traces to neither is decoration — cut it.")
    return "\n".join(lines)


def all_tickers(specs: Optional[dict] = None) -> list[str]:
    specs = load_watched_facts() if specs is None else specs
    return sorted(str(k).upper() for k in specs)


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "MU"
    print(format_watched_facts(t))
