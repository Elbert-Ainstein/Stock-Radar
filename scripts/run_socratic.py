#!/usr/bin/env python3
"""run_socratic.py — Phase 3 orchestrator for Socratic Mode (BUILD_PLAN_v2 Phase 3).

Three parallel Sonnet calls (model_a / model_b / model_c), then one corpus
callosum call that classifies disagreements as research-vs-judgment. Writes
to socratic_analyses with mode=socratic.

This is the Round 1 + CC slice only. Research round and rough_target_range
come in Phase 4. Judgment card / bets come in Phase 5.

Usage:
    python scripts/run_socratic.py LITE
    python scripts/run_socratic.py CAMT --no-supabase
    python scripts/run_socratic.py LITE --trigger-reason "phase3_smoke"

Pass criterion for Phase 3 (from BUILD_PLAN_v2):
  - mode=socratic row appears in socratic_analyses
  - model_a, model_b, model_c all populated (not null)
  - disagreements array has >=1 entry on a contested ticker like LITE
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env
load_env()

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

from lib.ir_lookup import get_ir_metadata  # noqa: E402

REPO_ROOT = HERE.parent
PROMPTS_DIR = HERE / "prompts" / "socratic"
SOURCES_PATH = HERE / "prompts" / "sources_allowlist.json"
SOCRATIC_DIR = REPO_ROOT / "data" / "socratic"
OPERATOR_NOTES_DIR = REPO_ROOT / "data" / "operator_notes"
VALIDATED_CORRECTIONS_PATH = REPO_ROOT / "data" / "validated_corrections.md"  # 2026-05-26 cross-ticker fact layer

SOCRATIC_MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITER_PER_MODEL = 5
DEFAULT_MAX_TOKENS = 1500
DEFAULT_TEMPERATURE = 0.3


# ────────────────────────────────────────────────────────────────────
# Prompt loading
# ────────────────────────────────────────────────────────────────────

def load_prompt(name: str) -> tuple[dict, str]:
    """Load socratic/{name}.md, split YAML frontmatter from body."""
    path = PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


_PLACEHOLDER_RE = re.compile(r"\[([A-Z][A-Z0-9_]{2,})\]")  # min 3 chars — skips example tokens like [NN] [YY] in JSON schema descriptions
# Placeholders that may legitimately be empty (e.g. optional operator notes)
_OPTIONAL_PLACEHOLDERS: frozenset[str] = frozenset({
    "OPERATOR_NOTES",
    "PREVIOUS_REGIME",
    "PREVIOUS_RUN_DATE",
    "RESEARCH_FINDINGS",
})


def find_placeholders(body: str) -> set[str]:
    """Return the set of unique [PLACEHOLDER] tokens present in the prompt body."""
    return {m.group(1).lower() for m in _PLACEHOLDER_RE.finditer(body)}


def fill(body: str, *, label: str = "?", strict: bool = True, **fields: Any) -> str:
    """Replace [TICKER] [PRICE] etc placeholders in the prompt body.

    Must-fix #2 (review squad 2026-05-20): strict-by-default. Every placeholder
    present in the body must have a non-empty value in `fields`, or this raises.
    Prevents the silent-blank-context failure mode where a prompt has
    [MACRO_CONTEXT] but build_context() forgot to provide it — under the old
    behavior the run produced a context-blind analysis with macro_environment_id
    set in Supabase, looking fully-contextualized. Now: hard error before any
    API call is made.

    Args:
        body: prompt text containing [PLACEHOLDER] tokens.
        label: which prompt this is (used in the error message).
        strict: if True (default), missing or empty placeholder values raise.
                Set to False ONLY for prompts where empty rendering is intended
                (rare; document at the call site).
        **fields: keyword args. Keys are matched case-insensitively to placeholder
                  names; `ticker=foo` matches `[TICKER]`.

    Returns:
        The body with placeholders replaced.

    Raises:
        ValueError: in strict mode, when any placeholder in the body has no
                    corresponding non-empty value (and is not in
                    _OPTIONAL_PLACEHOLDERS).
    """
    placeholders_in_body = find_placeholders(body)
    fields_lower = {k.lower(): v for k, v in fields.items()}

    if strict:
        missing: list[str] = []
        empty: list[str] = []
        for p in placeholders_in_body:
            if p in _OPTIONAL_PLACEHOLDERS:
                continue
            if p not in fields_lower:
                missing.append(p)
                continue
            val = fields_lower[p]
            if val is None or (isinstance(val, str) and val.strip() == ""):
                empty.append(p)

        if missing or empty:
            details = []
            if missing:
                details.append(f"missing: {sorted(missing)}")
            if empty:
                details.append(f"empty: {sorted(empty)}")
            raise ValueError(
                f"[{label}] placeholder-presence guard failed: {' ; '.join(details)}. "
                f"Found in prompt body: {sorted(placeholders_in_body)}. "
                f"Got context keys: {sorted(fields_lower.keys())}. "
                f"This guard prevents silent-blank-context Supabase writes. "
                f"Either add the missing keys to build_context() / the call site, or "
                f"add the placeholder name to _OPTIONAL_PLACEHOLDERS if empty rendering "
                f"is intentional."
            )

    out = body
    for key, val in fields_lower.items():
        out = out.replace(f"[{key.upper()}]", "" if val is None else str(val))
    return out


# ────────────────────────────────────────────────────────────────────
# Claude API call with optional web_search
# Parameterized variant of run_thesis.call_claude_with_search.
# Kept local to avoid touching run_thesis.py (karpathy rule 3).
# ────────────────────────────────────────────────────────────────────

def call_sonnet(
    prompt: str,
    *,
    model: str = SOCRATIC_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    max_iter: int = MAX_TOOL_ITER_PER_MODEL,
    allowed_domains: Optional[list[str]] = None,
    label: str = "",
) -> dict:
    try:
        import anthropic
    except ImportError as e:
        raise ImportError("anthropic SDK required") from e

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")

    client = anthropic.Anthropic(api_key=api_key)

    tools = []
    if allowed_domains is not None:
        tools.append({
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": max_iter,
            "allowed_domains": allowed_domains,
        })

    messages: list[dict] = [{"role": "user", "content": prompt}]
    all_blocks: list[dict] = []
    text_parts: list[str] = []
    input_tokens_total = 0
    output_tokens_total = 0
    web_search_count = 0
    stop_reason = ""

    for iteration in range(max_iter):
        print(f"  [{label}] API call {iteration + 1}/{max_iter}...", file=sys.stderr, flush=True)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)

        input_tokens_total += resp.usage.input_tokens
        output_tokens_total += resp.usage.output_tokens
        stop_reason = resp.stop_reason

        for block in resp.content:
            d: dict[str, Any] = {"type": block.type}
            if block.type == "text":
                d["text"] = block.text
                text_parts.append(block.text)
            elif block.type in ("tool_use", "server_tool_use"):
                d["name"] = getattr(block, "name", "")
                d["input"] = getattr(block, "input", {})
                if getattr(block, "name", "") == "web_search":
                    web_search_count += 1
            all_blocks.append(d)

        if stop_reason == "end_turn":
            break

        messages.append({"role": "assistant", "content": resp.content})
        if stop_reason == "max_tokens":
            print(
                f"  [{label}] WARN: stop_reason=max_tokens — response was truncated. "
                f"Bump max_tokens (currently {max_tokens}) for this prompt and retry.",
                file=sys.stderr, flush=True,
            )
            break
        if stop_reason == "stop_sequence":
            break

    return {
        "text": "\n\n".join(text_parts),
        "raw_blocks": all_blocks,
        "input_tokens": input_tokens_total,
        "output_tokens": output_tokens_total,
        "web_search_count": web_search_count,
        "stop_reason": stop_reason,
    }


# ────────────────────────────────────────────────────────────────────
# Output parsing
# ────────────────────────────────────────────────────────────────────

JSON_FENCE_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
JSON_FENCE_GENERIC_RE = re.compile(r"```\s*(\{[^`]*?\})\s*```", re.DOTALL)


def _find_last_balanced_json_object(text: str) -> Optional[str]:
    """Walk from the end of the text and return the last balanced top-level
    {...} substring. Tolerates prose before/after, escaped braces in strings,
    and trailing notes."""
    # Find every '}' in the text; for each, walk backwards counting braces
    # until we find the matching '{'. Return the LAST one that parses.
    candidates: list[str] = []
    close_positions = [i for i, c in enumerate(text) if c == "}"]
    for end in reversed(close_positions):
        depth = 0
        in_str = False
        esc = False
        start = -1
        for i in range(end, -1, -1):
            ch = text[i]
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start >= 0:
            candidate = text[start:end+1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    return None


def extract_json(text: str, label: str) -> Optional[dict]:
    """Find the model's JSON output. Tries (in order):
      1. ```json ... ``` fence (most specific)
      2. ``` ... ``` generic fence containing a JSON object
      3. Last balanced top-level {...} anywhere in the text

    On failure, dump the raw text to data/socratic/debug/ so we can inspect
    what format the model used.
    """
    # 1. Fenced ```json
    matches = list(JSON_FENCE_JSON_RE.finditer(text))
    if matches:
        raw = matches[-1].group(1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass  # fall through to other strategies

    # 2. Fenced ``` (no language tag) containing a JSON object
    matches = list(JSON_FENCE_GENERIC_RE.finditer(text))
    if matches:
        raw = matches[-1].group(1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    # 3. Last balanced {...} anywhere in the text
    candidate = _find_last_balanced_json_object(text)
    if candidate is not None:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # All strategies failed; dump raw to debug folder for inspection
    debug_dir = SOCRATIC_DIR / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    debug_path = debug_dir / f"{label}_{ts}.txt"
    try:
        debug_path.write_text(text, encoding="utf-8")
        print(
            f"  [{label}] no JSON found in output ({len(text)} chars). "
            f"Raw text saved to {debug_path.relative_to(REPO_ROOT)} for inspection.",
            file=sys.stderr,
        )
    except Exception:
        print(f"  [{label}] no JSON found in output ({len(text)} chars).", file=sys.stderr)
    return None


def _supabase_client():
    """Best-effort Supabase client. Returns None if not configured."""
    try:
        from supabase_helper import get_client
        return get_client()
    except Exception:
        try:
            from supabase import create_client
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SECRET_KEY", "")
            if not url or not key:
                return None
            return create_client(url, key)
        except Exception:
            return None


def fetch_current_macro() -> Optional[dict]:
    """Read the latest non-superseded macro_environment row via the view.
    Returns None if the view does not exist (table not migrated yet) or DB unreachable.
    Phase 5.5 — added 2026-05-20."""
    sb = _supabase_client()
    if sb is None:
        return None
    try:
        result = sb.table("current_macro_environment").select("*").limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        print(f"  [macro] fetch skipped — {e}", file=sys.stderr)
    return None


def fetch_wave_context_for_ticker(ticker: str) -> Optional[dict]:
    """Find the ticker primary wave (or most-recent if no primary set) and
    return its current wave_health row joined with wave metadata.

    Resolution rule (Must-fix #3): use ticker_revolutions.is_primary_wave if
    exactly one is true; otherwise pick the most-recently-refreshed
    wave_health row across all matching waves.
    Returns None if no match or DB unreachable.
    """
    sb = _supabase_client()
    if sb is None:
        return None
    try:
        rev_rows = (
            sb.table("ticker_revolutions")
              .select("wave_id, is_primary_wave")
              .eq("ticker", ticker.upper())
              .execute()
              .data or []
        )
        if not rev_rows:
            return None

        primaries = [r for r in rev_rows if r.get("is_primary_wave")]
        if len(primaries) == 1:
            wave_ids = [primaries[0]["wave_id"]]
        else:
            wave_ids = [r["wave_id"] for r in rev_rows]

        wh_rows = (
            sb.table("current_wave_health")
              .select("*")
              .in_("wave_id", wave_ids)
              .execute()
              .data or []
        )
        if not wh_rows:
            return None
        wh_rows.sort(key=lambda r: r.get("run_at") or "", reverse=True)
        wh = wh_rows[0]

        try:
            w = (
                sb.table("waves")
                  .select("name_cn, name_en, wave_number, lifecycle, timing_category, chokepoint")
                  .eq("id", wh["wave_id"])
                  .limit(1)
                  .execute()
                  .data or [{}]
            )[0]
            wh["_wave_meta"] = w
        except Exception:
            wh["_wave_meta"] = {}
        return wh
    except Exception as e:
        print(f"  [wave_health] fetch skipped for {ticker} — {e}", file=sys.stderr)
        return None


def format_macro_context(macro: Optional[dict]) -> str:
    """Render a macro_environment row into a multi-line text block for prompt injection.
    Returns a labeled "(none)" string if macro is None so downstream rendering produces
    a graceful note rather than a blank."""
    if not macro:
        return "(none — macro_environment table empty or unreachable; treat as macro-blind)"
    bear = macro.get("bear_case") or {}
    bull = macro.get("bull_case") or {}
    triggers = macro.get("state_change_triggers") or []
    this_week = macro.get("this_week_watch") or []

    lines = []
    lines.append(f"REGIME: {macro.get('regime_classification', 'unknown')}")
    summary = macro.get("state_summary") or ""
    if summary:
        lines.append(f"SUMMARY: {summary}")
    lines.append("")
    lines.append(f"BEAR CASE (probability: {bear.get('probability', '?')}):")
    for d in (bear.get("drivers") or []):
        lines.append(f"  - {d}")
    if bear.get("implication"):
        lines.append(f"  IMPLICATION: {bear['implication']}")
    lines.append("")
    lines.append(f"BULL CASE (probability: {bull.get('probability', '?')}):")
    for d in (bull.get("drivers") or []):
        lines.append(f"  - {d}")
    if bull.get("implication"):
        lines.append(f"  IMPLICATION: {bull['implication']}")
    if triggers:
        lines.append("")
        lines.append("STATE-CHANGE TRIGGERS:")
        for t in triggers:
            lines.append(f"  - [{t.get('direction','?')}] {t.get('event','?')}: {t.get('watch_for','?')}")
    if this_week:
        lines.append("")
        lines.append("THIS WEEK:")
        for w in this_week:
            lines.append(f"  - {w.get('item','?')} — {w.get('note','')}")
    if macro.get("falsification"):
        lines.append("")
        lines.append(f"FALSIFICATION: {macro['falsification']}")
    return "\n".join(lines)


def format_wave_context(wave: Optional[dict], ticker: str = "") -> str:
    """Render a wave_health row into a multi-line text block for prompt injection.
    Returns a labeled "(none)" string if wave is None."""
    if not wave:
        return f"(none — {ticker} not assigned to a wave OR wave_health not seeded for that wave)"
    meta = wave.get("_wave_meta") or {}
    lines = []
    wave_name = meta.get("name_cn") or meta.get("name_en") or f"wave_id={wave.get('wave_id')}"
    lines.append(f"WAVE: {wave_name} (#{meta.get('wave_number','?')})")
    if meta.get("chokepoint"):
        lines.append(f"  Chokepoint: {meta['chokepoint']}")
    if meta.get("timing_category"):
        lines.append(f"  Timing: {meta['timing_category']}")
    if wave.get("momentum_label") or wave.get("momentum_score") is not None:
        lines.append(f"  Momentum: {wave.get('momentum_label','?')} (avg 12mo return: {wave.get('momentum_score','?')})")
    if wave.get("crowding_score"):
        lines.append(f"  Crowding: {wave['crowding_score']}")
    if wave.get("avg_forward_pe") is not None:
        lines.append(f"  Forward P/E: {wave['avg_forward_pe']:.1f}x ({wave.get('pe_vs_5yr_mean','?')})")
    lines.append("")
    if wave.get("macro_beta") is not None:
        lines.append(f"MACRO BETA: {wave['macro_beta']:.2f}x")
        if wave.get("beta_methodology"):
            lines.append(f"  (methodology: {wave['beta_methodology']})")
    if wave.get("macro_translation"):
        lines.append(f"  Translation: {wave['macro_translation']}")
    if wave.get("why_drivers"):
        lines.append(f"  Why: {wave['why_drivers']}")
    if wave.get("regime_playbook"):
        lines.append(f"  Regime playbook: {wave['regime_playbook']}")

    diff = wave.get("differentiation") or []
    if diff:
        lines.append("")
        lines.append("INTRA-WAVE (per-ticker resilience + trailing returns):")
        for d in diff:
            tkr = d.get("ticker", "?")
            r12 = d.get("trailing_12mo_return")
            r18 = d.get("trailing_18mo_return")
            marker = " ◀" if tkr == ticker.upper() else ""
            r12_str = f"{r12:.2f}" if isinstance(r12, (int, float)) else "?"
            r18_str = f"{r18:.2f}" if isinstance(r18, (int, float)) else "?"
            lines.append(f"  - {tkr}: r12mo={r12_str}, r18mo={r18_str}, resilience={d.get('resilience','?')} — {d.get('reason','')}{marker}")

    signals = wave.get("watch_signals") or {}
    if signals:
        lines.append("")
        lines.append("WATCH SIGNALS (cycle-shift observables, not binary triggers):")
        for k, v in signals.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict):
                cur = v.get("current","?")
                thresh = v.get("threshold_bearish") or v.get("watch_for") or v.get("threshold_bullish") or "?"
                lines.append(f"  - {k}: current={cur}; watch={thresh}")
            else:
                lines.append(f"  - {k}: {v}")
    return "\n".join(lines)


def fetch_operator_notes(ticker: str) -> str:
    """Load per-ticker operator notes from data/operator_notes/{TICKER}.md.

    Returns the file body (with an optional leading H1 stripped) for injection
    as the [OPERATOR_NOTES] block in the 5 Socratic prompts. Returns a labeled
    "(none)" string when the file does not exist — the prompts handle the
    none-case explicitly and skip the section.

    Operator notes are Hume's SUBJECTIVE view on the ticker. The prompts treat
    them as input to test against the data, not as fact. See
    data/operator_notes/README.md for the contract.
    """
    path = OPERATOR_NOTES_DIR / f"{ticker.upper()}.md"
    if not path.exists():
        return f"(none — no operator note file at data/operator_notes/{ticker.upper()}.md)"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"  [operator_notes] WARN: could not read {path.name}: {e}", file=sys.stderr)
        return f"(none — operator note file present but unreadable: {e})"
    if not text:
        return f"(none — operator note file is empty)"
    # Strip a leading H1 if present so the body reads cleanly when concatenated
    # under the prompt's own "### [OPERATOR_NOTES]" header.
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        # drop the H1 and any immediately-following blank line
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip() or f"(none — operator note file body empty after title)"


def fetch_validated_corrections() -> str:
    """Load cross-ticker engine-verified factual corrections from data/validated_corrections.md.

    Unlike per-ticker operator_notes (subjective), this file contains corrections to
    common market narratives that engine research has confirmed. Loaded into EVERY
    Socratic run so corrections to claims about Company A do not get re-cited
    incorrectly when analyzing Company B that mentions Company A.

    Treatment in prompts: corrections are FACTS, not opinions. Models must treat
    them as ground truth. See data/validated_corrections.md for format.
    """
    path = VALIDATED_CORRECTIONS_PATH
    if not path.exists():
        return f"(none — no validated_corrections.md file at {path})"
    try:
        body = path.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"  [validated_corrections] WARN: could not read {path.name}: {e}", file=sys.stderr)
        return f"(none — validated_corrections file present but unreadable: {e})"
    if not body:
        return f"(none — validated_corrections file is empty)"
    lines = body.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip() or f"(none — validated_corrections body empty after title)"


# ────────────────────────────────────────────────────────────────────
# Context: build the placeholder dict each model gets
# ────────────────────────────────────────────────────────────────────

def build_context(ticker: str, *, override_suspect_recent: bool = False) -> dict:
    """Gather price, sector, market cap, company name for the three model prompts.

    override_suspect_recent: passed through to fetch_financials to bypass Module 1's
    recent-quarter sanity check. Use ONLY when operator has cross-checked against the
    10-Q. See main() --override-suspect-recent flag for full caveat.
    """
    from finance_data import fetch_financials

    fin = fetch_financials(ticker, override_suspect_recent=override_suspect_recent)
    spot = fin.price or 0.0
    sector = getattr(fin, "sector", "") or ""
    meta = get_ir_metadata(ticker)

    market_cap = None
    if hasattr(fin, "market_cap") and fin.market_cap:
        market_cap = fin.market_cap
    elif hasattr(fin, "quarterly_balance") and fin.quarterly_balance:
        shares = (fin.quarterly_balance[-1] or {}).get("Ordinary Shares Number")
        if shares and spot:
            market_cap = shares * spot

    if market_cap and market_cap >= 1e12:
        market_cap_str = f"${market_cap/1e12:.2f}T"
    elif market_cap and market_cap >= 1e9:
        market_cap_str = f"${market_cap/1e9:.2f}B"
    elif market_cap and market_cap >= 1e6:
        market_cap_str = f"${market_cap/1e6:.0f}M"
    else:
        market_cap_str = "n/a"

    # Phase 5.5 (2026-05-20): fetch macro + wave context from Supabase if available.
    # Graceful degradation: if tables not migrated or DB unreachable, fall back to
    # a labeled "(none)" string so prompts still render and the strict-fill guard
    # only fires on placeholders we forgot, not on legitimate absence of macro layer.
    macro_row = fetch_current_macro()
    wave_row = fetch_wave_context_for_ticker(ticker)
    macro_context = format_macro_context(macro_row)
    wave_context = format_wave_context(wave_row, ticker=ticker)

    # 2026-05-24: per-ticker operator notes (Hume's subjective view). Read from
    # data/operator_notes/{TICKER}.md if present; otherwise emit a labeled "(none)"
    # so the strict-fill guard accepts the placeholder. Prompts treat the notes as
    # input to test against the data, NOT as fact. See data/operator_notes/README.md.
    operator_notes = fetch_operator_notes(ticker)
    validated_corrections = fetch_validated_corrections()

    if macro_row:
        print(f"  [macro] regime={macro_row.get('regime_classification','?')} (id={macro_row.get('id','?')})", file=sys.stderr, flush=True)
    else:
        print("  [macro] not available — proceeding macro-blind", file=sys.stderr, flush=True)
    if wave_row:
        wmeta = wave_row.get("_wave_meta") or {}
        print(f"  [wave_health] {wmeta.get('name_cn','?')} (#{wmeta.get('wave_number','?')}) — beta={wave_row.get('macro_beta','?')}", file=sys.stderr, flush=True)
    else:
        print(f"  [wave_health] not available for {ticker} — proceeding wave-blind", file=sys.stderr, flush=True)
    if operator_notes.startswith("(none"):
        print(f"  [operator_notes] none for {ticker.upper()}", file=sys.stderr, flush=True)
    else:
        preview = operator_notes.replace("\n", " ")[:80]
        print(f"  [operator_notes] LOADED for {ticker.upper()} ({len(operator_notes)} chars): {preview}...", file=sys.stderr, flush=True)
    if validated_corrections.startswith("(none"):
        print(f"  [validated_corrections] none", file=sys.stderr, flush=True)
    else:
        print(f"  [validated_corrections] LOADED ({len(validated_corrections)} chars, cross-ticker facts)", file=sys.stderr, flush=True)

    return {
        "ticker": ticker.upper(),
        "price": f"${spot:.2f}",
        "spot_raw": spot,
        "sector": sector,
        "market_cap": market_cap_str,
        "market_cap_raw": market_cap,
        "company_name": meta.get("company_name", ticker),
        # Phase 5.5 — [MACRO_CONTEXT] / [WAVE_CONTEXT] placeholders live in all 5
        # Socratic prompts. 2026-05-24 added [OPERATOR_NOTES] same pattern.
        "macro_context": macro_context,
        "wave_context": wave_context,
        "operator_notes": operator_notes,
        "validated_corrections": validated_corrections,
        "macro_environment_id": macro_row.get("id") if macro_row else None,
        "wave_health_id": wave_row.get("id") if wave_row else None,
    }


# ────────────────────────────────────────────────────────────────────
# Round 1: three parallel model calls
# ────────────────────────────────────────────────────────────────────

def run_one_model(role: str, ctx: dict, allowed_domains: list[str]) -> dict:
    name_map = {
        "a": "model_a_fundamentals",
        "b": "model_b_regime",
        "c": "model_c_adversarial",
    }
    front, body = load_prompt(name_map[role])
    prompt = fill(body, label=f"model_{role}", **ctx)

    result = call_sonnet(
        prompt,
        model=front.get("model", SOCRATIC_MODEL),
        max_tokens=int(front.get("max_tokens", DEFAULT_MAX_TOKENS)),
        temperature=float(front.get("temperature", DEFAULT_TEMPERATURE)),
        max_iter=MAX_TOOL_ITER_PER_MODEL,
        allowed_domains=allowed_domains,
        label=f"model_{role}",
    )
    parsed = extract_json(result["text"], f"model_{role}")
    return {
        "role": role,
        "parsed": parsed,
        "text": result["text"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "web_search_count": result["web_search_count"],
        "prompt_version": front.get("version", "v1"),
    }


def run_round_1_parallel(ctx: dict, allowed_domains: list[str]) -> dict[str, dict]:
    """Fire the three Round-1 calls in parallel. Fail fast if any returns no JSON."""
    ticker = ctx["ticker"]
    print(f"  [round_1] firing 3 parallel Sonnet calls for {ticker}...", flush=True)
    results: dict[str, dict] = {}
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(run_one_model, role, ctx, allowed_domains): role for role in ("a", "b", "c")}
        for fut in cf.as_completed(futures):
            role = futures[fut]
            try:
                results[role] = fut.result()
            except Exception as e:
                raise RuntimeError(f"model_{role} failed: {e}") from e

    for role, r in results.items():
        if r["parsed"] is None:
            raise RuntimeError(f"model_{role} returned unparseable output; aborting Socratic run")

    return results


# ────────────────────────────────────────────────────────────────────
# Corpus callosum — classify disagreements
# ────────────────────────────────────────────────────────────────────

def run_corpus_callosum(ctx: dict, round_1: dict[str, dict]) -> dict:
    front, body = load_prompt("corpus_callosum")
    prompt = fill(
        body,
        label="corpus_callosum",
        ticker=ctx["ticker"],
        price=ctx["price"],
        macro_context=ctx.get("macro_context", "(none)"),
        operator_notes=ctx.get("operator_notes", "(none)"),
        validated_corrections=ctx.get("validated_corrections", "(none)"),
        model_a_json=json.dumps(round_1["a"]["parsed"], ensure_ascii=False, indent=2),
        model_b_json=json.dumps(round_1["b"]["parsed"], ensure_ascii=False, indent=2),
        model_c_json=json.dumps(round_1["c"]["parsed"], ensure_ascii=False, indent=2),
    )
    result = call_sonnet(
        prompt,
        model=front.get("model", SOCRATIC_MODEL),
        max_tokens=int(front.get("max_tokens", 2000)),
        temperature=float(front.get("temperature", 0.2)),
        max_iter=1,
        allowed_domains=None,  # CC compares JSONs; no web search needed
        label="corpus_callosum",
    )
    parsed = extract_json(result["text"], "corpus_callosum")
    if parsed is None:
        raise RuntimeError("corpus_callosum returned unparseable output")
    return {
        "parsed": parsed,
        "text": result["text"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "prompt_version": front.get("version", "v1"),
    }


# ────────────────────────────────────────────────────────────────────
# Persistence
# ────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────
# Phase 4: research round — resolve RESEARCH-type disagreements
# ────────────────────────────────────────────────────────────────────

def run_research_round(
    ctx: dict,
    cc_parsed: dict,
    allowed_domains: Optional[list[str]],
) -> list[dict]:
    """For each RESEARCH-type disagreement from corpus callosum, fire one
    Sonnet+web_search call and collect the finding. Sequential — usually
    only 1-5 questions per ticker, so parallel adds complexity for marginal
    speedup. JUDGMENT-type disagreements are NOT touched here; they fall
    through to Phase 5 (judgment card)."""
    front, body = load_prompt("research_question")
    research_disagreements = [
        d for d in cc_parsed.get("disagreements", [])
        if d.get("type") == "research"
    ]
    if not research_disagreements:
        print("  [research] no RESEARCH-type disagreements; skipping", flush=True)
        return []

    print(f"  [research] resolving {len(research_disagreements)} RESEARCH question(s)...", flush=True)
    findings: list[dict] = []
    for i, d in enumerate(research_disagreements, 1):
        query = d.get("research_query") or d.get("question") or ""
        if not query:
            continue
        prompt = fill(
            body,
            label=f"research_{i}",
            ticker=ctx["ticker"],
            price=ctx["price"],
            sector=ctx["sector"],
            research_question=query,
        )
        result = call_sonnet(
            prompt,
            model=front.get("model", SOCRATIC_MODEL),
            max_tokens=int(front.get("max_tokens", 3000)),
            temperature=float(front.get("temperature", 0.2)),
            max_iter=MAX_TOOL_ITER_PER_MODEL,
            allowed_domains=allowed_domains,
            label=f"research_{i}",
        )
        parsed = extract_json(result["text"], f"research_{i}")
        if parsed is None:
            # Non-fatal: record the question with a null finding so the
            # downstream rough_target_range can see what we couldn't resolve.
            print(f"  [research_{i}] WARN: could not parse finding; recording as unresolved", file=sys.stderr)
            findings.append({
                "question": query,
                "finding": None,
                "confidence": "INSUFFICIENT_PUBLIC_DATA",
                "sources_cited": [],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "web_search_count": result["web_search_count"],
            })
            continue

        parsed["input_tokens"] = result["input_tokens"]
        parsed["output_tokens"] = result["output_tokens"]
        parsed["web_search_count"] = result["web_search_count"]
        findings.append(parsed)
        conf = parsed.get("confidence", "?")
        snippet = (parsed.get("finding") or "")[:80]
        print(f"  [research_{i}] {conf}: {snippet}...", flush=True)

    return findings


# ────────────────────────────────────────────────────────────────────
# Phase 4: rough target range — wrap-up paragraph
# ────────────────────────────────────────────────────────────────────

def run_rough_target_range(
    ctx: dict,
    round_1: dict[str, dict],
    cc: dict,
    research_findings: list[dict],
) -> dict:
    """Final synthesis call. Takes Round-1 verdicts, corpus callosum output,
    and any research findings; produces the rough_target_range JSON.
    No web search — pure synthesis."""
    front, body = load_prompt("rough_target_range")
    prompt = fill(
        body,
        label="rough_target_range",
        ticker=ctx["ticker"],
        price=ctx["price"],
        macro_context=ctx.get("macro_context", "(none)"),
        wave_context=ctx.get("wave_context", "(none)"),
        operator_notes=ctx.get("operator_notes", "(none)"),
        validated_corrections=ctx.get("validated_corrections", "(none)"),
        model_a_json=json.dumps(round_1["a"]["parsed"], ensure_ascii=False, indent=2),
        model_b_json=json.dumps(round_1["b"]["parsed"], ensure_ascii=False, indent=2),
        model_c_json=json.dumps(round_1["c"]["parsed"], ensure_ascii=False, indent=2),
        cc_json=json.dumps(cc["parsed"], ensure_ascii=False, indent=2),
        research_findings=json.dumps(research_findings, ensure_ascii=False, indent=2) if research_findings else "(none)",
    )
    result = call_sonnet(
        prompt,
        model=front.get("model", SOCRATIC_MODEL),
        max_tokens=int(front.get("max_tokens", 4000)),
        temperature=float(front.get("temperature", 0.2)),
        max_iter=1,
        allowed_domains=None,  # synthesis, no search needed
        label="rough_target_range",
    )
    parsed = extract_json(result["text"], "rough_target_range")
    if parsed is None:
        raise RuntimeError("rough_target_range returned unparseable output")
    return {
        "parsed": parsed,
        "text": result["text"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "prompt_version": front.get("version", "v1"),
    }


def save_markdown(ticker: str, run_at: datetime, ctx: dict, round_1: dict, cc: dict, research_findings: list[dict], target: dict) -> Path:
    SOCRATIC_DIR.mkdir(parents=True, exist_ok=True)
    safe_ticker = ticker.upper().replace(".", "_")
    fname = f"{safe_ticker}_{run_at.strftime('%Y%m%d_%H%M%S')}.md"
    path = SOCRATIC_DIR / fname

    parts: list[str] = []
    parts.append(f"# Socratic Analysis — {ctx['ticker']} ({ctx['company_name']})")
    parts.append(
        f"_Run: {run_at.isoformat()}_  ·  spot **{ctx['price']}**  ·  "
        f"mkt cap **{ctx['market_cap']}**  ·  sector **{ctx['sector']}**"
    )
    parts.append("")
    parts.append("## Round 1 — Three Parallel Verdicts")
    for role in ("a", "b", "c"):
        r = round_1[role]
        parts.append(f"### Model {role.upper()}")
        parts.append("```json")
        parts.append(json.dumps(r["parsed"], ensure_ascii=False, indent=2))
        parts.append("```")
        parts.append("")
    parts.append("## Corpus Callosum")
    parts.append("```json")
    parts.append(json.dumps(cc["parsed"], ensure_ascii=False, indent=2))
    parts.append("```")
    parts.append("")
    parts.append("---")
    parts.append("**Tokens (in/out):**")
    for role in ("a", "b", "c"):
        r = round_1[role]
        parts.append(
            f"- model_{role}: {r['input_tokens']} / {r['output_tokens']}  "
            f"(web_search: {r['web_search_count']})"
        )
    parts.append(f"- corpus_callosum: {cc['input_tokens']} / {cc['output_tokens']}")
    rin = sum(r.get('input_tokens', 0) for r in research_findings)
    rout = sum(r.get('output_tokens', 0) for r in research_findings)
    if research_findings:
        parts.append(f"- research_round: {rin} / {rout}  ({len(research_findings)} question(s))")
    parts.append(f"- rough_target_range: {target['input_tokens']} / {target['output_tokens']}")

    # Append Phase 4 sections (research findings + rough target range)
    parts.append("")
    parts.append("## Research Findings")
    if not research_findings:
        parts.append("_No RESEARCH-type disagreements; section skipped._")
    else:
        for i, f in enumerate(research_findings, 1):
            parts.append(f"### {i}. {f.get('question','(unknown question)')}")
            parts.append("```json")
            parts.append(json.dumps({k: v for k, v in f.items() if k not in ('input_tokens','output_tokens','web_search_count')}, ensure_ascii=False, indent=2))
            parts.append("```")
            parts.append("")
    # Append target section
    parts.append("## Rough Target Range")
    parts.append("```json")
    parts.append(json.dumps(target['parsed'], ensure_ascii=False, indent=2))
    parts.append("```")

    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def write_to_supabase(
    ticker: str, run_at: datetime, ctx: dict, round_1: dict, cc: dict,
    research_findings: list[dict], target: dict, markdown_path: Path,
) -> Optional[int]:
    try:
        from supabase_helper import get_client
        sb = get_client()
    except ImportError:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SECRET_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY not set")
        sb = create_client(url, key)

    cc_parsed = cc["parsed"]
    row = {
        "ticker": ticker.upper(),
        "run_at": run_at.isoformat(),
        "mode": "socratic",
        "thesis_id": None,
        "model_a": round_1["a"]["parsed"],
        "model_b": round_1["b"]["parsed"],
        "model_c": round_1["c"]["parsed"],
        "agreements": cc_parsed.get("agreements", []),
        "disagreements": cc_parsed.get("disagreements", []),
        "research_findings": [
            {k: v for k, v in f.items() if k not in ("input_tokens", "output_tokens", "web_search_count")}
            for f in research_findings
        ],
        "rough_target_low": target["parsed"].get("rough_target_low"),
        "rough_target_high": target["parsed"].get("rough_target_high"),
        "downside_price": target["parsed"].get("downside_price"),
        "rough_target_paragraph": target["parsed"].get("rough_target_paragraph"),
        "final_verdict": None,  # left for human via judgment card (Phase 5)
        "prompt_versions": {
            "model_a": round_1["a"]["prompt_version"],
            "model_b": round_1["b"]["prompt_version"],
            "model_c": round_1["c"]["prompt_version"],
            "corpus_callosum": cc["prompt_version"],
            "research_question": "v1" if research_findings else None,
            "rough_target_range": target["prompt_version"],
        },
        "spot_at_run": ctx["spot_raw"],
        "input_tokens": (
            sum(round_1[r]["input_tokens"] for r in "abc")
            + cc["input_tokens"]
            + sum(f.get("input_tokens", 0) for f in research_findings)
            + target["input_tokens"]
        ),
        "output_tokens": (
            sum(round_1[r]["output_tokens"] for r in "abc")
            + cc["output_tokens"]
            + sum(f.get("output_tokens", 0) for f in research_findings)
            + target["output_tokens"]
        ),
        "web_search_count": (
            sum(round_1[r]["web_search_count"] for r in "abc")
            + sum(f.get("web_search_count", 0) for f in research_findings)
        ),
    }
    result = sb.table("socratic_analyses").insert(row).execute()
    if not result.data:
        print(
            "  [supabase] socratic_analyses insert returned empty data "
            "(RLS or schema drift). Markdown is saved locally; thesis still ok.",
            file=sys.stderr, flush=True,
        )
        return None
    return result.data[0].get("id")


# ────────────────────────────────────────────────────────────────────
# Orchestrator
# ────────────────────────────────────────────────────────────────────

def run_socratic(ticker: str, *, trigger_reason: str = "manual", supabase: bool = True,
                 override_suspect_recent: bool = False) -> dict:
    print(f"\n=== run_socratic: {ticker} ({trigger_reason}) ===", flush=True)
    run_at = datetime.now(timezone.utc)

    ctx = build_context(ticker, override_suspect_recent=override_suspect_recent)
    print(
        f"  spot={ctx['price']} sector={ctx['sector']} mkt_cap={ctx['market_cap']}",
        flush=True,
    )

    # Load the tier-based allowlist (matches run_thesis.load_allowed_domains).
    # An empty list crashes the Anthropic API with a 400 — pass None when empty.
    try:
        cfg = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        allowed_domains = (
            cfg.get("tier_1_filings", [])
            + cfg.get("tier_2_press", [])
            + cfg.get("tier_3_newswires", [])
            + cfg.get("tier_4_data", [])
        )
    except Exception:
        allowed_domains = []
    if not allowed_domains:
        allowed_domains = None  # tells call_sonnet to omit the tools block

    round_1 = run_round_1_parallel(ctx, allowed_domains)
    a_v = (round_1["a"]["parsed"] or {}).get("verdict")
    b_v = (round_1["b"]["parsed"] or {}).get("verdict")
    c_v = (round_1["c"]["parsed"] or {}).get("verdict")
    print(f"  [round_1] complete — A:{a_v}  B:{b_v}  C:{c_v}", flush=True)

    print("  [cc] running corpus callosum...", flush=True)
    cc = run_corpus_callosum(ctx, round_1)
    n_agree = len(cc["parsed"].get("agreements", []))
    n_disagree = len(cc["parsed"].get("disagreements", []))
    n_research = sum(1 for d in cc["parsed"].get("disagreements", []) if d.get("type") == "research")
    n_judgment = sum(1 for d in cc["parsed"].get("disagreements", []) if d.get("type") == "judgment")
    print(f"  [cc] complete — {n_agree} agreements, {n_disagree} disagreements ({n_research} research, {n_judgment} judgment)", flush=True)

    # ─── RECONSTRUCTED 2026-05-24 — orchestrator tail rebuilt from 2026-05-23 CHANGELOG ───
    # Truncation found at line 1062 mid-call to run_research_round. All four called
    # helpers (run_research_round, run_rough_target_range, save_markdown, write_to_supabase)
    # already exist above. This block wires them in the order documented in the
    # 2026-05-23 CHANGELOG. No new behavior. See CHANGELOG entry [2026-05-24] for the
    # full reconstruction log.

    # Phase 4: resolve RESEARCH-type disagreements with web search
    research_findings = run_research_round(ctx, cc["parsed"], allowed_domains)

    # Phase 4: produce the rough target range paragraph
    print("  [target] computing rough target range...", flush=True)
    target = run_rough_target_range(ctx, round_1, cc, research_findings)
    tp = target["parsed"]
    print(
        f"  [target] complete — rough range ${tp.get('rough_target_low')}-${tp.get('rough_target_high')}, "
        f"downside ${tp.get('downside_price')}",
        flush=True,
    )

    # Persist local markdown report (always — survives Supabase outage)
    markdown_path = save_markdown(ticker, run_at, ctx, round_1, cc, research_findings, target)
    print(f"  [markdown] saved → {markdown_path.relative_to(REPO_ROOT)}", flush=True)

    # Conditional Supabase write — gated by --no-supabase flag
    row_id: Optional[int] = None
    if supabase:
        try:
            row_id = write_to_supabase(
                ticker, run_at, ctx, round_1, cc, research_findings, target, markdown_path,
            )
            if row_id is not None:
                print(f"  [supabase] socratic_analyses.id={row_id} written", flush=True)
        except Exception as e:
            # Markdown is already saved locally; surface but don't abort.
            print(f"  [supabase] WARN: write failed — {e}", file=sys.stderr, flush=True)
    else:
        print("  [supabase] skipped (--no-supabase)", flush=True)

    print(f"=== run_socratic done: {ticker} ===\n", flush=True)

    return {
        "ticker": ticker.upper(),
        "run_at": run_at.isoformat(),
        "socratic_analyses_id": row_id,
        "markdown_path": str(markdown_path),
        "round_1": {role: round_1[role]["parsed"] or {} for role in "abc"},  # critic-fix: defensive consistent with line 1048
        "corpus_callosum": cc["parsed"],
        "research_findings": research_findings,
        "rough_target_range": target["parsed"],
    }


# ────────────────────────────────────────────────────────────────────
# CLI — RECONSTRUCTED 2026-05-24, pattern matches run_thesis.py main()
# ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run the Socratic 3-model engine on one ticker."
    )
    parser.add_argument("ticker", help="Ticker to run (e.g. LITE, CAMT, AXON, 6082.HK)")
    parser.add_argument(
        "--trigger-reason",
        default="manual",
        help=(
            "Free-text label recorded with the run for downstream filtering "
            "(e.g. 'manual', 'phase3_smoke', 'op_notes_verify_id16')."
        ),
    )
    parser.add_argument(
        "--no-supabase",
        action="store_true",
        help="Skip writing to Supabase (markdown report is still saved locally).",
    )
    parser.add_argument(
        "--override-suspect-recent",
        action="store_true",
        help=(
            "Bypass Module 1's recent-quarter sanity check. Use ONLY when the operator "
            "has cross-checked against the 10-Q and confirmed the apparent anomaly is "
            "real (e.g. post-spinoff jump like SNDK, post-IPO first quarter, M&A close, "
            "or early-stage commercial-revenue ramp from near-zero baseline like ASTS, "
            "RKLB, PL, BKSY, LUNR). For genuine provider bugs (e.g. MU yfinance/EODHD "
            "anomaly), the OVERRIDE produces a Socratic analysis built on bad numbers "
            "\u2014 DO NOT USE."
        ),
    )
    args = parser.parse_args()

    run_socratic(
        args.ticker,
        trigger_reason=args.trigger_reason,
        supabase=not args.no_supabase,
        override_suspect_recent=args.override_suspect_recent,
    )


if __name__ == "__main__":
    main()
