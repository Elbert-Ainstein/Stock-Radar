#!/usr/bin/env python3
"""
run_thesis.py - Run the V3 thesis prompt on a ticker via Claude API + web_search.

Pipeline:
  1. Fetch current price + sector via finance_data
  2. Look up company metadata via lib.ir_lookup (auto-discovers IR domain)
  3. Build prompt by filling [TICKER]/[PRICE]/[SECTOR]/etc placeholders
  4. Call Claude API with web_search tool, restricted to allowlist + IR domain
  5. Loop on stop_reason="tool_use" until end_turn
  6. Walk content blocks, concatenate text, regex-extract closing JSON block
  7. Save markdown to data/theses/{ticker}_{YYYYMMDD}.md
  8. Write parsed row to Supabase `theses` table
  9. Lazily enrich ir_cache.json with any IR-looking domains cited by the model

Usage:
    python scripts/run_thesis.py LITE
    python scripts/run_thesis.py LITE --trigger-reason earnings
    python scripts/run_thesis.py 6082.HK --no-supabase  # dry run, skip DB write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

# Ensure scripts/ on path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env, create_message

load_env()


# Windows: force UTF-8 on stdout/stderr so non-ASCII (em-dashes, smart
# quotes, foreign company names) doesn't trip the system encoding.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8')
        except Exception:
            pass

from lib.ir_lookup import get_ir_metadata, update_ir_domain  # noqa: E402
from lib.memory import get_memory, save_memory, format_prior_context  # noqa: E402

REPO_ROOT = HERE.parent
PROMPT_PATH = HERE / "prompts" / "thesis_v3.md"
SOURCES_PATH = HERE / "prompts" / "sources_allowlist.json"
THESES_DIR = REPO_ROOT / "data" / "theses"

ANTHROPIC_MODEL = "claude-opus-4-8"
ANTHROPIC_MODEL_MEMORY = "claude-sonnet-4-6"
MEMORY_PROMPT_PATH = HERE / "prompts" / "memory_update_v1.md"
MEMORY_MAX_TOKENS = 16000
MEMORY_TEMPERATURE = 0.0  # deterministic for bookkeeping pass
MAX_TOOL_ITER = 8           # ceiling on web_search loop
MAX_TOKENS = 16000
TEMPERATURE = 0.3


# ────────────────────────────────────────────────────────────────────
# Prompt loading + frontmatter parsing
# ────────────────────────────────────────────────────────────────────

def load_prompt_with_frontmatter() -> tuple[dict, str]:
    """Read thesis_v3.md, split YAML frontmatter from prompt body."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {"version": "unknown"}, text
    frontmatter = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)
    return frontmatter, body


def fill_placeholders(body: str, **fields: str) -> str:
    """Replace [TICKER] [PRICE] etc placeholders."""
    out = body
    for key, val in fields.items():
        out = out.replace(f"[{key.upper()}]", str(val))
    return out


def _archetype_override_block(archetype: str | None) -> str:
    """Build the [ARCHETYPE_OVERRIDE] block injected into thesis_v3.md.

    Empty when no override is set (so the placeholder leaves NO literal text — the
    prior bug: the unfilled placeholder shipped verbatim and the model valued
    regime-shift names like mature companies). For `transformational`, instruct
    Step-5 multiple selection to anchor to regime-shift comps and drop the +25%
    carve-out ceiling — the v3.4.4 design the frontmatter marked 'smoke test pending'.
    """
    if not archetype:
        return ""
    a = archetype.lower()
    if a == "transformational":
        return (
            "STRATEGIC ARCHETYPE OVERRIDE — this ticker is tagged "
            "**transformational** (regime-shift / right-tail), set by the operator in "
            "config/ticker_archetype_overrides.json.\n"
            "At Step 5 (multiple selection): anchor the forward multiple to regime-shift "
            "comparables — e.g. NVDA peak NTM forward ~59x (mid-2025), ASML pre-EUV "
            "35-45x — NOT to mature-company mean multiples, and DISABLE the +25% "
            "carve-out ceiling. This is a demand-regime change, not a cycle: size the "
            "multiple to the durability of the inflection. Keep FULL tactical rigor on "
            "NTM EPS, dilution, and entry price — the tag does not excuse an inflated "
            "multiple or hand-waved EPS; it only forbids anchoring to mature-company means."
        )
    return (
        f"STRATEGIC ARCHETYPE OVERRIDE — this ticker is tagged **{a}** by the operator "
        f"(config/ticker_archetype_overrides.json). Apply the {a} valuation framework at "
        f"Step 5; keep full tactical rigor on inputs."
    )


# ────────────────────────────────────────────────────────────────────
# Source allowlist
# ────────────────────────────────────────────────────────────────────

def load_allowed_domains(ir_domain: str = "") -> list[str]:
    """Load the global allowlist; optionally append a per-ticker IR domain."""
    cfg = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    domains = (
        cfg["tier_1_filings"]
        + cfg["tier_2_press"]
        + cfg["tier_3_newswires"] + cfg.get("tier_4_data", [])
    )
    if ir_domain:
        domains.append(ir_domain)
    return domains


# ────────────────────────────────────────────────────────────────────
# Claude API call with web_search tool
# ────────────────────────────────────────────────────────────────────

def call_claude_with_search(
    prompt: str,
    allowed_domains: list[str],
    max_iter: int = MAX_TOOL_ITER,
) -> dict:
    """Call Claude with the web_search tool; loop until end_turn or max_iter.

    Returns:
        {
          "text": concatenated text from all assistant messages,
          "raw_blocks": list of all content blocks (for debugging),
          "input_tokens": int,
          "output_tokens": int,
          "web_search_count": int,
          "stop_reason": last stop_reason,
        }
    """
    try:
        import anthropic
    except ImportError as e:
        raise ImportError("anthropic SDK required: pip install anthropic --break-system-packages") from e

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")

    client = anthropic.Anthropic(api_key=api_key)

    web_search_tool = {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": max_iter,
        "allowed_domains": allowed_domains,
    }

    messages = [{"role": "user", "content": prompt}]
    all_blocks = []
    text_parts = []
    input_tokens_total = 0
    output_tokens_total = 0
    web_search_count = 0
    stop_reason = ""

    for iteration in range(max_iter):
        print(f"  [run_thesis] API call {iteration + 1}/{max_iter}...", file=sys.stderr, flush=True)
        resp = create_message(
            client,
            model=ANTHROPIC_MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            tools=[web_search_tool],
            messages=messages,
        )

        input_tokens_total += resp.usage.input_tokens
        output_tokens_total += resp.usage.output_tokens
        stop_reason = resp.stop_reason

        # Walk content blocks, accumulate text + raw
        for block in resp.content:
            block_dict = _block_to_dict(block)
            all_blocks.append(block_dict)
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "server_tool_use" or block.type == "tool_use":
                if getattr(block, "name", "") == "web_search":
                    web_search_count += 1

        # If Claude is done, stop the loop
        if stop_reason == "end_turn":
            break

        # If tool was used (server-side web_search), Claude continues automatically;
        # we still need to add the assistant turn to history to extend the context
        # for any follow-up. The Anthropic SDK handles server-side tool use within
        # a single API call when the tool is server-managed (web_search_20250305 is
        # server-side), so when we get here with stop_reason == "end_turn" the loop
        # exits cleanly. If stop_reason is "tool_use" with a non-server tool, we'd
        # need to feed back results — but with web_search_20250305 that's not the case.
        # Add assistant message and continue if there's any other reason.
        messages.append({"role": "assistant", "content": resp.content})

        if stop_reason in ("max_tokens", "stop_sequence"):
            print(f"  [run_thesis] stop_reason={stop_reason}; aborting loop", file=sys.stderr)
            break

    return {
        "text": "\n\n".join(text_parts),
        "raw_blocks": all_blocks,
        "input_tokens": input_tokens_total,
        "output_tokens": output_tokens_total,
        "web_search_count": web_search_count,
        "stop_reason": stop_reason,
    }


def _block_to_dict(block) -> dict:
    """Serialize a content block (text / tool_use / tool_result) to a JSON-safe dict."""
    d = {"type": block.type}
    if block.type == "text":
        d["text"] = block.text
        # Citations may be attached
        cits = getattr(block, "citations", None)
        if cits:
            d["citations"] = [_citation_to_dict(c) for c in cits]
    elif block.type in ("tool_use", "server_tool_use"):
        d["name"] = getattr(block, "name", "")
        d["input"] = getattr(block, "input", {})
        d["id"] = getattr(block, "id", "")
    elif block.type == "web_search_tool_result":
        # The result content is a list of WebSearchResult objects
        content = getattr(block, "content", [])
        d["content"] = [_search_result_to_dict(r) for r in content]
        d["tool_use_id"] = getattr(block, "tool_use_id", "")
    else:
        # Unknown block type; persist what we can
        d["repr"] = repr(block)[:500]
    return d


def _citation_to_dict(c) -> dict:
    return {
        "url": getattr(c, "url", ""),
        "title": getattr(c, "title", ""),
        "cited_text": (getattr(c, "cited_text", "") or "")[:300],
    }


def _search_result_to_dict(r) -> dict:
    return {
        "url": getattr(r, "url", ""),
        "title": getattr(r, "title", ""),
        "type": getattr(r, "type", ""),
    }


# ────────────────────────────────────────────────────────────────────
# Output parsing
# ────────────────────────────────────────────────────────────────────

JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def extract_closing_json(text: str) -> Optional[dict]:
    """Find the LAST ```json {…} ``` block and parse it."""
    matches = list(JSON_FENCE_RE.finditer(text))
    if not matches:
        return None
    last = matches[-1].group(1)
    try:
        return json.loads(last)
    except json.JSONDecodeError as e:
        print(f"  [run_thesis] closing JSON parse failed: {e}", file=sys.stderr)
        return None


def _load_thesis_horizon(ticker: str) -> Optional[float]:
    """Per-name thesis horizon in years (config/thesis_horizons.json).

    Lesson L1 (2026-07-02): the clamp table's 12-18mo clock must be a declared,
    per-name parameter, not a silent constant. Returns None only when the file
    or key is genuinely absent; every OTHER failure warns loudly (review fix
    2026-07-02 — a trailing comma used to silently revert ALL names to the
    default clock while the operator believed the feature was active)."""
    import json as _json
    path = REPO_ROOT / "config" / "thesis_horizons.json"
    if not path.exists():
        return None
    try:
        data = _json.loads(path.read_text())
    except (OSError, ValueError) as e:
        print(f"  [thesis_horizon] WARNING: {path.name} unreadable ({e}) — ALL names "
              f"fall back to the default clock", file=sys.stderr, flush=True)
        return None
    v = data.get(ticker.upper())
    if v is None or isinstance(v, bool):  # bool is an int subclass — reject
        if isinstance(v, bool):
            print(f"  [thesis_horizon] WARNING: {ticker} horizon is boolean {v!r} — "
                  f"ignored, default clock used", file=sys.stderr, flush=True)
        return None
    try:
        return float(v)  # accepts int/float AND numeric strings like "3.0"
    except (TypeError, ValueError):
        print(f"  [thesis_horizon] WARNING: {ticker} horizon {v!r} is not numeric — "
              f"ignored, default clock used", file=sys.stderr, flush=True)
        return None


def thesis_output_usable(parsed: Optional[dict]) -> bool:
    """Truncation-guard predicate (2026-07-02, sprint 2.4): a thesis output is
    persistable only if the closing JSON carries at least one verdict field.
    A max_tokens truncation or parse failure yields {}/None -> refuse, so an
    all-null row never masks the previous good thesis in the latest-wins API."""
    p = parsed or {}
    return any(p.get(k) is not None for k in ("thesis_target", "conviction", "risk_adj_target"))


def extract_cited_domains(blocks: list[dict]) -> list[str]:
    """Pull the host of every URL Claude cited."""
    from urllib.parse import urlparse
    seen = set()
    for b in blocks:
        if b.get("type") == "text":
            for c in b.get("citations") or []:
                url = c.get("url", "")
                if url:
                    host = urlparse(url).netloc.lower().replace("www.", "")
                    if host:
                        seen.add(host)
        elif b.get("type") == "web_search_tool_result":
            for r in b.get("content") or []:
                url = r.get("url", "")
                if url:
                    host = urlparse(url).netloc.lower().replace("www.", "")
                    if host:
                        seen.add(host)
    return sorted(seen)


def coverage_quality(num_distinct_domains: int) -> str:
    if num_distinct_domains >= 5:
        return "HIGH"
    if num_distinct_domains >= 3:
        return "MEDIUM"
    return "LOW"


# ────────────────────────────────────────────────────────────────────
# Persistence
# ────────────────────────────────────────────────────────────────────

def save_markdown(ticker: str, run_at: datetime, body: str) -> Path:
    THESES_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{ticker.upper().replace('.', '_')}_{run_at.strftime('%Y%m%d_%H%M%S')}.md"
    path = THESES_DIR / fname
    path.write_text(body, encoding="utf-8")
    return path


def write_to_supabase(row: dict) -> int | None:
    """Insert a thesis row and return its assigned id (or None on failure).
    The id is needed by the outcome tracker (Module 8) to seed the matching
    thesis_outcomes row at save time.

    Failure modes that return None (caller MUST be told loudly):
      - The insert succeeded at the DB level but PostgREST returned empty
        `result.data` because of an RLS config that allows INSERT but not
        SELECT on the inserted row. In that case the thesis exists in the DB
        but we can't match it to a thesis_id, so outcome tracking is silently
        broken. Print a HARD WARNING in this branch — over weeks of runs the
        thesis_outcomes table would otherwise stay empty with no signal.
      - The returned row has no `id` key (column was renamed/removed in a
        migration that hasn't been applied uniformly — the schema-drift
        pattern that has bitten this codebase before). Same loud warning.
    """
    try:
        from supabase_helper import get_client
    except ImportError:
        # Fallback: lightweight inline Supabase client
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SECRET_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY not set")
        sb = create_client(url, key)
    else:
        sb = get_client()
    import re as _re
    result = None
    # Strip budget is DYNAMIC: one attempt per column + 1. The old fixed
    # range(5) tolerated at most 4 missing columns — the L4 run_parameters
    # column made it 6 potentially missing pre-migration, which would have
    # exhausted the budget and lost the ENTIRE verdict row (the exact
    # prediction_logger off-by-one from sprint 1.3, re-caught in review
    # 2026-07-08). The loop still exits on success or any non-column error.
    for _attempt in range(len(row) + 1):
        try:
            result = sb.table("theses").insert(row).execute()
            break
        except Exception as e:
            m = (_re.search(r"column \"?([a-zA-Z_][a-zA-Z0-9_]*)\"? .*does not exist", str(e))
                 or _re.search(r"Could not find the '([a-zA-Z_][a-zA-Z0-9_]*)' column", str(e)))
            if m and m.group(1) in row:
                bad = m.group(1)
                print(f"  [supabase] column '{bad}' missing in theses — stripping and retrying "
                      f"(apply the matching supabase migration to persist it).",
                      file=sys.stderr, flush=True)
                row = {k: v for k, v in row.items() if k != bad}
                continue
            raise
    if result is None:
        raise RuntimeError("theses insert failed after stripping unknown columns")
    if not result.data:
        # The insert may have succeeded (no exception raised) but PostgREST
        # returned an empty body. This typically means RLS blocks SELECT on
        # the freshly inserted row. The thesis is saved, but we have no id —
        # so outcome tracking can never seed its row. Make this LOUD.
        print(
            "  [supabase] HARD WARNING: theses insert returned empty data — "
            "likely RLS denies SELECT on the inserted row. Outcome tracking "
            "will be silently skipped for this thesis. Fix: ensure RLS allows "
            "the insert role to SELECT its own writes, OR run the inserter "
            "with the service-role key.",
            file=sys.stderr, flush=True,
        )
        return None
    inserted = result.data[0]
    if "id" not in inserted or inserted.get("id") is None:
        print(
            "  [supabase] HARD WARNING: insert returned a row but no 'id' "
            f"field (got keys: {sorted(inserted.keys())[:8]}). Schema drift "
            "suspected — outcome tracking will skip this thesis.",
            file=sys.stderr, flush=True,
        )
        return None
    return inserted["id"]


def write_socratic_auto(thesis_id: int | None, row: dict, parsed: dict) -> int | None:
    """Dual-write the thesis as an `auto`-mode row in socratic_analyses.

    BUILD_PLAN_v2 Phase 2 wiring (2026-05-15): the new 5-tab frontend reads
    from socratic_analyses for both auto and socratic modes. Auto-mode rows
    here carry the single-call thesis verdict in `model_a` (model_b/c null)
    so the UI doesn't need to know about modes.

    Best-effort. Failures must NOT abort the run â the canonical write is to
    `theses` (already done by write_to_supabase). This is a denormalized
    convenience copy. If it fails, the run still succeeded.
    """
    try:
        try:
            from supabase_helper import get_client
            sb = get_client()
        except ImportError:
            from supabase import create_client
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SECRET_KEY", "")
            if not url or not key:
                return None
            sb = create_client(url, key)

        model_a = {
            "role": "auto",
            "verdict": parsed.get("conviction"),
            "target_low": parsed.get("buy_below") or parsed.get("thesis_target"),
            "target_high": parsed.get("breakout_price") or parsed.get("thesis_target"),
            "thesis_target": parsed.get("thesis_target"),
            "risk_adj_target": parsed.get("risk_adj_target"),
            "risk_adj_ev_ratio": parsed.get("risk_adj_ev_ratio"),
            "position_size_pct": parsed.get("position_size_pct"),
            "confidence": parsed.get("conviction"),
            "filters": parsed.get("filters", {}),
            "top_risks_count": len(parsed.get("top_risks", []) or []),
            "top_catalysts_count": len(parsed.get("top_catalysts", []) or []),
        }

        socratic_row = {
            "ticker": row["ticker"],
            "run_at": row["run_at"],
            "mode": "auto",
            "thesis_id": thesis_id,
            "model_a": model_a,
            "model_b": None,
            "model_c": None,
            "agreements": [],
            "disagreements": [],
            "research_findings": [],
            "rough_target_low": parsed.get("buy_below") or parsed.get("thesis_target"),
            "rough_target_high": parsed.get("breakout_price") or parsed.get("thesis_target"),
            "downside_price": parsed.get("buy_below"),
            "final_verdict": _conviction_to_verdict(parsed.get("conviction")),
            "prompt_versions": {"auto": row.get("prompt_version", "unknown")},
            "spot_at_run": row.get("spot_at_run"),
            "input_tokens": row.get("input_tokens"),
            "output_tokens": row.get("output_tokens"),
            "web_search_count": row.get("web_search_count"),
        }

        result = sb.table("socratic_analyses").insert(socratic_row).execute()
        if not result.data:
            print(
                "  [supabase] socratic_analyses dual-write returned empty data "
                "(RLS or schema drift). Auto-mode row not stored in socratic_analyses; "
                "theses write succeeded so the canonical record is intact.",
                file=sys.stderr, flush=True,
            )
            return None
        return result.data[0].get("id")
    except Exception as e:
        print(f"  [WARN] socratic_analyses dual-write skipped: {e}", file=sys.stderr, flush=True)
        return None


def _conviction_to_verdict(conviction):
    """Map theses.conviction -> socratic_analyses.final_verdict enum."""
    if not conviction:
        return None
    c = conviction.upper()
    if c in ("HIGH", "MEDIUM"):
        return "proceed"
    if c in ("LOW", "LOW-MEDIUM"):
        return "watch"
    if c in ("BROKEN", "WEAK"):
        return "pass"
    return None



def _log_outcome_if_possible(thesis_id: int | None) -> None:
    """Best-effort outcome logging. Failures here must NOT abort the run —
    the thesis was successfully saved; outcome tracking is bookkeeping."""
    if thesis_id is None:
        return
    try:
        from lib.outcomes import log_thesis_outcome
        ok = log_thesis_outcome(thesis_id)
        if ok:
            print(f"  [outcomes] logged thesis_id={thesis_id} for forward-price tracking", flush=True)
        else:
            print(f"  [outcomes] WARN: log_thesis_outcome returned False for thesis_id={thesis_id}", flush=True)
    except Exception as e:
        print(f"  [outcomes] WARN: outcome logging failed: {e}", flush=True)


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────
# Memory-update pass (Sonnet, no web search)
# ────────────────────────────────────────────────────────────────────

def call_claude_memory_update(
    ticker: str,
    company_name: str,
    existing_memory: str,
    new_thesis_json: dict,
    new_thesis_markdown: str,
    new_run_date: str,
    new_prompt_version: str,
) -> str | None:
    """Run the memory-maintenance prompt to produce an updated memory.md.

    Returns the new memory markdown, or None on failure. Caller logs and
    leaves existing memory unchanged — never blocks the thesis run.

    Robustness:
      - placeholder substitution order: system-controlled placeholders FIRST,
        user-controlled [EXISTING_MEMORY] LAST so user-supplied content cannot
        accidentally re-trigger substitution (FIX 4 from review).
      - output validation: extract YAML frontmatter via regex (not naive
        startswith), parse it as YAML; reject the response if parse fails
        (FIX 3 from review).
    """
    try:
        import anthropic
    except ImportError:
        print("  [memory] anthropic SDK unavailable; skipping memory update", file=sys.stderr)
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  [memory] ANTHROPIC_API_KEY not set; skipping memory update", file=sys.stderr)
        return None

    if not MEMORY_PROMPT_PATH.exists():
        print(f"  [memory] prompt file missing: {MEMORY_PROMPT_PATH}", file=sys.stderr)
        return None

    template = MEMORY_PROMPT_PATH.read_text(encoding="utf-8")
    # Strip the maintenance prompt's own YAML frontmatter
    fm_match = re.match(r"^---\n.*?\n---\n", template, re.DOTALL)
    if fm_match:
        template = template[fm_match.end():]

    # FIX 4: substitute system-controlled placeholders FIRST, user content LAST.
    # Otherwise a user-supplied note containing literal "[NEW_THESIS_JSON]" would
    # get double-substituted.
    md_clipped = new_thesis_markdown[:30000]
    if len(new_thesis_markdown) > 30000:
        md_clipped += "\n\n... [truncated]"

    prompt = template
    prompt = prompt.replace("[NEW_THESIS_JSON]", json.dumps(new_thesis_json, indent=2))
    prompt = prompt.replace("[NEW_THESIS_MARKDOWN]", md_clipped)
    prompt = prompt.replace("[NEW_RUN_DATE]", new_run_date)
    prompt = prompt.replace("[NEW_PROMPT_VERSION]", new_prompt_version)
    prompt = prompt.replace("[TICKER]", ticker)
    prompt = prompt.replace("[COMPANY_NAME]", company_name)
    # Existing memory LAST, after every other placeholder is resolved
    prompt = prompt.replace(
        "[EXISTING_MEMORY]",
        existing_memory or "(no memory yet — first run on this ticker)",
    )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=ANTHROPIC_MODEL_MEMORY,
            max_tokens=MEMORY_MAX_TOKENS,
            temperature=MEMORY_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print(f"  [memory] update API call failed: {e}", file=sys.stderr)
        return None

    # PATCH I (round 4): if the response was truncated by max_tokens, refuse
    # the write. Otherwise the truncated output passes all downstream
    # validation gates — frontmatter is at the top, parses fine — but
    # everything past the cutoff is silently dropped, including potentially
    # `## Hume Notes` and the recent thesis history. Better to preserve
    # existing memory and surface the issue.
    if getattr(resp, "stop_reason", None) == "max_tokens":
        print(f"  [memory] response hit max_tokens ceiling ({MEMORY_MAX_TOKENS}); "
              "REFUSING WRITE — existing memory preserved. The maintenance prompt "
              "may need to drop more content via Rule 11, or MEMORY_MAX_TOKENS "
              "needs to rise.", file=sys.stderr)
        return None

    text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    text = "\n".join(text_parts).strip()
    if not text:
        print("  [memory] empty response; skipping write", file=sys.stderr)
        return None

    # FIX 3 (round 2): robust frontmatter detection.
    # Strip a possible prose preamble ("Here's the updated memory:") by
    # finding the first `---` line and slicing FROM THERE — but the close
    # marker must be the FIRST `^---$` AFTER the open marker, not anywhere
    # in the body. Anchor strictly with re.match on the sliced view.
    fm_start = re.search(r"^---\s*$", text, re.MULTILINE)
    if fm_start is None:
        print("  [memory] response has no YAML frontmatter; skipping write", file=sys.stderr)
        print(f"  [memory] first 200 chars: {text[:200]!r}", file=sys.stderr)
        return None
    text = text[fm_start.start():]

    # Anchored match: --- at start, then YAML body, then closing --- on its
    # own line. The non-greedy (.*?) finds the FIRST closing ---, not any
    # later body horizontal-rule. Without re.DOTALL, `.` does NOT match
    # newlines — but YAML frontmatter is always one or more lines, so we
    # explicitly use [\s\S] to span lines.
    fm_match = re.match(r"^---\s*\n([\s\S]*?)\n---\s*$", text, re.MULTILINE)
    if not fm_match:
        print("  [memory] frontmatter open/close markers not found at document start; skipping", file=sys.stderr)
        return None
    try:
        parsed_fm = yaml.safe_load(fm_match.group(1))
    except Exception as e:
        print(f"  [memory] frontmatter YAML invalid; skipping write: {e}", file=sys.stderr)
        return None

    # Type-check: frontmatter MUST be a dict. A bare string or list would mean
    # we sliced into body text and `yaml.safe_load` happened to accept it.
    if not isinstance(parsed_fm, dict):
        print(f"  [memory] frontmatter parsed but is not a dict (got {type(parsed_fm).__name__}); skipping write", file=sys.stderr)
        return None
    # Sanity check: warn (do not block) if ticker in frontmatter doesn't match.
    # Renames (SQ→BLOCK, FB→META) are legitimate; refusing all writes when
    # frontmatter is stale would silently brick the memory file forever.
    # The user still gets a visible signal via stderr.
    fm_ticker = str(parsed_fm.get("ticker", "")).upper()
    if fm_ticker and fm_ticker != ticker.upper():
        print(f"  [memory] WARN: frontmatter ticker mismatch "
              f"(doc={fm_ticker!r}, run={ticker.upper()!r}); proceeding with write. "
              f"If this is a rename, update the frontmatter manually next time you "
              f"edit the memory file.", file=sys.stderr)

    return text


def _build_verified_financials_block(fin, currency: str = "USD") -> str:
    """Build a 'USE THESE NUMBERS' snippet from fetch_financials output.

    The numerical inputs (recent quarterly revenue, margins, share count) come
    from scout-verified Supabase data, which has already passed the Module 1
    sanity check. This snippet is injected into the prompt at the
    `[VERIFIED_FINANCIALS]` placeholder so the body of the prompt (STEPs 0/2/4)
    can reference it explicitly as "the verified block above."

    Currency-safe: the column header uses the company's reporting currency
    code, and the magnitude scaling is chosen by currency:
      - USD/EUR/GBP/CHF/CAD/AUD: billions (÷1e9)
      - HKD/JPY/KRW/TWD/CNY/INR: billions still, but the $ symbol is dropped
        and the currency code is shown — these currencies have very different
        absolute magnitudes (e.g., 1.2B JPY ≈ 8M USD), and forcing dollar
        framing would anchor the model to a wrong-magnitude number.
    Per the squad red-team finding (2026-05-07), the prior version hard-coded
    `Revenue ($B)` and `/1e9` for all tickers, which produced "$4,200.00B" for
    a 4.2T KRW Korean stock and silently corrupted the model's anchoring.

    Negative-revenue rows are flagged with `(NEG)` in the row marker and the
    margin column is marked `n/a` — silently rendering them as 0% margin
    (the prior bug) hid distress signals.
    """
    if fin is None or not getattr(fin, 'quarterly_income', None):
        return ""

    # Resolve currency: prefer explicit fin.currency, fall back to passed-in.
    # Strip whitespace/case so e.g. "Hkd " → "HKD".
    fin_ccy = (getattr(fin, 'currency', None) or currency or "USD").strip().upper() or "USD"
    # Single-currency display only — the column header carries the currency code,
    # so the model is never anchored to a wrong magnitude.
    col_label = f"Rev ({fin_ccy}, B)"
    oi_label = f"OpInc ({fin_ccy}, B)"
    ni_label = f"NetInc ({fin_ccy}, B)"

    qi = fin.quarterly_income[-6:]  # most recent 6 quarters for context
    lines = [
        "## SCOUT-VERIFIED FINANCIALS (authoritative — do not override with web search)",
        "",
        f"All values in {fin_ccy}. Source: 10-Q/10-K actuals via fetch_financials.",
        "These figures have passed the Module 1 revenue sanity check (size-aware:",
        ">2× trailing-avg / >2.5× YoY for large-caps). Per STEP 2 of the analysis,",
        "anchor your forward build to this table within rounding precision.",
        "Web search is for narrative, guidance language, and competitor context —",
        "not for replacing these numerical inputs UNLESS a brand-new earnings",
        "release (post-dating the most recent row) has been filed; in that case",
        "follow the STEP 2 escape hatch.",
        "",
        f"| Quarter | {col_label:>14} | {oi_label:>15} | OpMargin | {ni_label:>15} | Flag |",
        "|---------|----------------|-----------------|----------|-----------------|------|",
    ]
    for p in qi:
        rev_raw = p.get("Total Revenue")
        oi_raw = p.get("Operating Income")
        ni_raw = p.get("Net Income")
        # Coerce None → display blanks, not silent zeros that lie about the data.
        rev = (rev_raw or 0) / 1e9
        oi = (oi_raw or 0) / 1e9
        ni = (ni_raw or 0) / 1e9
        flag = ""
        if rev_raw is None:
            flag = "MISSING"
            margin_str = "n/a"
        elif rev_raw < 0:
            # Negative revenue is a real signal — restatement, contra-revenue,
            # or a known data-provider bug (e.g. yfinance MU TTM inflation).
            # Don't whitewash it as 0% margin.
            flag = "NEG_REV"
            margin_str = "n/a"
        elif rev_raw == 0:
            flag = "ZERO_REV"
            margin_str = "n/a"
        elif oi_raw is None:
            flag = "OI_MISSING"
            margin_str = "n/a"
        else:
            margin_str = f"{(oi / rev * 100):>6.1f}%"
        period_str = str(p.get('period', '?'))[:7]
        lines.append(
            f"| {period_str:<7} | {rev:>14.2f} | {oi:>15.2f} | "
            f"{margin_str:>8} | {ni:>15.2f} | {flag:<6} |"
        )

    # Latest share count if available — scale to millions, label currency-agnostic
    if hasattr(fin, 'quarterly_balance') and fin.quarterly_balance:
        latest_bs = fin.quarterly_balance[-1]
        shares = latest_bs.get("Ordinary Shares Number")
        if shares:
            lines.append("")
            lines.append(f"**Latest diluted shares outstanding:** {shares/1e6:.1f}M (use as STEP 4 starting point)")

    if hasattr(fin, 'warnings') and fin.warnings:
        recent_warnings = [w for w in fin.warnings if "OVERRIDE" in w or "FALLBACK" in w]
        if recent_warnings:
            lines.append("")
            lines.append("**Provenance flags:**")
            for w in recent_warnings:
                lines.append(f"- {w[:160]}")

    return "\n".join(lines)


def run_one(ticker: str, *, trigger_reason: str = "manual", supabase: bool = True,
            dry_run: bool = False, override_suspect_recent: bool = False) -> dict:
    print(f"\n=== run_thesis: {ticker} ===", flush=True)

    # 1. Fetch financials → spot price + sector
    # (Module 5 cleanup 2026-05-07: dropped stale `as_of=None` kwarg — the
    # signature was simplified during the provider-abstraction refactor and
    # this call site was never updated, blocking dry-runs with TypeError.)
    from finance_data import fetch_financials, fetch_live_price
    fin = fetch_financials(ticker, override_suspect_recent=override_suspect_recent)
    spot = fin.price or 0.0
    sector = getattr(fin, "sector", "") or ""
    # Use a LIVE quote for spot — fin.price is the EOD provider close (~1 day stale),
    # which distorts the trade-asymmetry ratio on volatile days.
    _live = fetch_live_price(ticker)
    spot_source = "eod_provider"  # L4: which price the verdict was judged at
    if _live:
        if spot and abs(_live - spot) / spot > 0.01:
            print(f"  [price] live ${_live:.2f} vs EOD provider ${spot:.2f} "
                  f"({(_live/spot - 1) * 100:+.1f}%) — using live", flush=True)
        spot = _live
        spot_source = "live"
    print(f"  spot={spot:.2f} sector={sector}", flush=True)

    # 2. IR metadata (auto-discover)
    meta = get_ir_metadata(ticker)
    print(f"  company={meta['company_name']!r} ir_domain={meta['ir_domain']!r}", flush=True)

    # 3. Build prompt
    frontmatter, body = load_prompt_with_frontmatter()
    prompt_version = frontmatter.get("version", "unknown")
    # 3a (NEW): read prior memory document, if any, for PRIOR CONTEXT injection
    memory_md = get_memory(ticker)
    memory_section = format_prior_context(memory_md) if memory_md else ""
    if memory_md:
        print(f"  memory: {len(memory_md)} chars (prior runs detected)", flush=True)
    # L7 (2026-07-08): operator hypotheses front door. Active hypotheses that
    # name this ticker ride into the prompt at the same prior-context slot
    # (thesis_v3.md untouched; empty folder = byte-identical prompt). Guarded:
    # a malformed hypothesis file must never fail a thesis run.
    try:
        from hypotheses import load_hypotheses, active_for_ticker, format_hypotheses_block
        _hyps = load_hypotheses()
        _active = active_for_ticker(ticker, _hyps)
        _hyp_block = format_hypotheses_block(ticker, _hyps)
        if _hyp_block:
            memory_section = (memory_section or "") + "\n" + _hyp_block
            print(f"  [hypotheses] injected {len(_active)} active "
                  f"hypothesis(es) for {ticker}: "
                  f"{', '.join(h['name'] for h in _active)}", flush=True)
    except Exception as e:
        print(f"  [hypotheses] WARN: skipped — {e}", file=sys.stderr, flush=True)

    # Build scout-verified financials block from Module 1 fetch (already passed
    # the recent-quarter sanity check). Inject at the [VERIFIED_FINANCIALS]
    # placeholder in thesis_v3.md (added v3.3, 2026-05-07). The prompt body
    # references the block explicitly in STEP 0 / STEP 2 / STEP 4, so the model
    # treats it as authoritative for historical numerical inputs.
    # Prior version (Module 5 v1) prepended the block to the prompt body; the
    # squad critic found this was invisible to the prompt — STEP 0 told the
    # model to web-search for the same numbers, with no anchor pointing back
    # to the injected table. Anchoring is now via placeholder + body text.
    verified_block = _build_verified_financials_block(fin, currency=meta.get("currency", "USD"))

    # Inject the operator archetype override into the prompt's Step-5 multiple
    # layer. The engine (V2) and kill gate (D1) already route on this; the THESIS
    # PROMPT was the missing leg — an unfilled [ARCHETYPE_OVERRIDE] made the model
    # value regime-shift names like mature companies (LITE -> ~$406 on a ~25x mult).
    try:
        from target_engine import _load_archetype_override
        _arch = _load_archetype_override(ticker)
    except Exception:
        _arch = None
    if _arch:
        print(f"  archetype override: {_arch} (injected into thesis prompt)", flush=True)

    prompt = fill_placeholders(
        body,
        ticker=ticker,
        company_name=meta["company_name"],
        exchange=meta["exchange"],
        currency=meta["currency"],
        price=f"{spot:.2f}",
        sector=sector or "Unknown",
        memory_section=memory_section,
        verified_financials=verified_block,
        archetype_override=_archetype_override_block(_arch),
    )

    # 4. Claude API call with web_search
    domains = load_allowed_domains(ir_domain=meta["ir_domain"])
    print(f"  domains: {len(domains)} entries", flush=True)
    if dry_run:
        print(f"  [DRY RUN] would call Claude with {len(prompt)} char prompt", flush=True)
        return {"dry_run": True, "prompt_length": len(prompt)}

    result = call_claude_with_search(prompt, domains)

    # 5. Parse output
    text = result["text"]
    parsed = extract_closing_json(text) or {}
    # 2026-07-02 truncation guard (sprint 2.4): a max_tokens truncation or an
    # unparseable closing JSON used to persist an all-null verdict row that
    # masked the previous good thesis in the latest-wins API. Fail loudly
    # instead — no row is written, yesterday's thesis stays authoritative.
    if not thesis_output_usable(parsed):
        raise RuntimeError(
            f"thesis output unusable for {ticker}: stop_reason="
            f"{result.get('stop_reason')!r}, closing JSON "
            f"{'missing' if not parsed else 'has no verdict fields'} "
            f"({len(text)} chars of text) — refusing to persist an all-null row"
        )
    if result.get("stop_reason") == "max_tokens":
        print(f"  [run_thesis] WARN: {ticker} output hit max_tokens but closing JSON "
              f"parsed with verdict fields — proceeding", file=sys.stderr, flush=True)

    # 2026-07-02 — HARD GATE ENFORCED IN CODE (sprint 2.1). The Step-12 clamp
    # table was prompt-prose only: nothing recomputed risk_adj_ev_ratio (both
    # operands in hand right here) and nothing clamped downward, so a model
    # arithmetic slip or optimistic self-report bypassed the gate (audit §4.2).
    # enforce_trade_gate is pure and never raises — a hard gate must not fail
    # open via an exception path. Runs BEFORE the kill gate so D1 reads the
    # honest ratio when deciding an archetype-routed relax.
    # Lesson L1 (2026-07-02): the gate is judged on the thesis's OWN clock —
    # per-name horizon from config/thesis_horizons.json, default 1.25y
    # (identical to the original table), stated with every verdict.
    # ALWAYS pass an explicit operator horizon (config or default): review fix
    # 2026-07-02 — the gate must never fall through to a model-emitted clock.
    from trade_gate import DEFAULT_HORIZON_YEARS, enforce_trade_gate, format_enforcement
    _h_cfg = _load_thesis_horizon(ticker)
    parsed, _tg = enforce_trade_gate(
        parsed, spot,
        horizon_years=_h_cfg if _h_cfg is not None else DEFAULT_HORIZON_YEARS,
    )
    if _tg:
        print(f"  [trade_gate] {ticker}: {format_enforcement(_tg)}", flush=True)
        if (_tg.get("conviction_after") == "BROKEN"
                and parsed.get("buy_below") in (None, 0)):
            print(f"  [trade_gate] WARN: {ticker} clamped to BROKEN without a "
                  f"buy_below price — not actionable (prompt requires one)",
                  file=sys.stderr, flush=True)

    # D1 (2026-06-03): archetype-routed kill gate. A ratio-driven BROKEN on a
    # regime-shift / pre-revenue name is relaxed deterministically (a Hard Gate
    # belongs in code, not model prose). The structured override travels with the
    # record so the checkpoint grader reads the routed verdict, not the raw BROKEN.
    try:
        from kill_gate import apply_kill_gate, is_pre_revenue
        from target_engine import _load_archetype_override
        _arch = _load_archetype_override(ticker)
        try:
            _ttm = fin.ttm_revenue()
        except Exception:
            _ttm = None
        parsed, _kgo = apply_kill_gate(parsed, _arch, pre_revenue=is_pre_revenue(_ttm))
        if _kgo:
            print(f"  [kill_gate] {ticker}: {_kgo['raw_verdict']} -> {_kgo['routed_verdict']} "
                  f"({_kgo['reason']})", flush=True)
        elif str(parsed.get("conviction") or "").upper() == "BROKEN":
            # Visibility for the no-op case: show WHY the gate didn't relax, so a
            # run is a real wiring check (did it see the archetype + ratio?).
            print(f"  [kill_gate] {ticker}: BROKEN left unchanged — archetype={_arch!r}, "
                  f"ratio={parsed.get('risk_adj_ev_ratio')}, "
                  f"strategic={parsed.get('strategic_conviction')!r} "
                  f"(transformational floor 0.60; pre_rev={is_pre_revenue(_ttm)})", flush=True)
    except Exception as e:
        print(f"  [kill_gate] WARN: skipped — {e}", file=sys.stderr, flush=True)

    # Model D (optionality / vision lens) — transformational names ONLY, additive.
    # Presents a vision CEILING alongside the engine FLOOR; it never overrides the
    # conviction/target. Guarded: a failure, or a missing diluted share count, just
    # skips it. One extra Opus call, gated to regime-shift names only (cost-aware).
    try:
        from model_d_generate import should_run_model_d, model_d_for_ticker
        if should_run_model_d(_arch):
            _shares = getattr(fin, "shares_diluted", None)
            if _shares and _shares > 0:
                # Bracket clock note (review 2026-07-02): floor_horizon_years
                # deliberately stays at its 1.25y default — risk_adj_target is
                # still prompt-pinned to a 12-18-month date regardless of
                # config/thesis_horizons.json (the gate scales conservative-
                # only for the same reason). Thread the configured horizon
                # here ONLY when the prompt becomes horizon-aware (L3 batch).
                _eng = parsed.get("risk_adj_target") or parsed.get("thesis_target")
                _md = model_d_for_ticker(ticker, context=text[:12000],
                                         shares=float(_shares), engine_target=_eng)
                parsed["model_d_bracket"] = _md["bracket"]
                b = _md["bracket"]
                print(f"  [model_d] vision ceiling ${b.get('vision_ceiling')} (PV) vs engine floor "
                      f"${b.get('engine_floor')} (${b.get('engine_floor_pv')} PV) — "
                      f"{b.get('vision_over_floor_x')}x like-for-like "
                      f"(raw {b.get('vision_over_floor_x_raw')}x) — additive, not a verdict",
                      flush=True)
            else:
                print("  [model_d] skipped — no diluted share count", flush=True)
    except Exception as e:
        print(f"  [model_d] skipped — {e}", file=sys.stderr, flush=True)

    # L5 (2026-07-02, advisory): kill triggers must be dated external signposts.
    try:
        from kill_condition_eval import lint_kill_triggers
        _kt = parsed.get("kill_triggers") or []
        _lint = lint_kill_triggers(_kt, _arch)
        if _lint:
            print(f"  [kill_lint] {ticker}: {len(_lint)}/{len(_kt)} trigger(s) below "
                  f"signpost grade (dated, external, falsifiable):", flush=True)
            for _w in _lint[:5]:
                print(f"    - {_w}", flush=True)
    except Exception as _le:
        print(f"  [kill_lint] skipped — {_le}", file=sys.stderr, flush=True)

    # L4 (2026-07-08): every run emits its parameter block — horizon clock,
    # post-scaling clamp table, archetype/dcf_role, allowlist size — logged
    # AND persisted (theses.run_parameters, strip-and-retry safe until the
    # 2026-07-08 migration is applied). No invisible opinions.
    try:
        from run_parameters import (build_thesis_run_parameters,
                                    load_archetype_and_dcf_role, diagnose_verdict)
        _, _dcf_role = load_archetype_and_dcf_role(ticker)
        run_params = build_thesis_run_parameters(
            ticker=ticker, prompt_version=prompt_version,
            model=ANTHROPIC_MODEL, temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
            spot=spot, spot_source=spot_source,
            horizon_config=_load_thesis_horizon(ticker),
            horizon_used=parsed.get("thesis_horizon_years"),
            horizon_fallback=(_tg or {}).get("horizon_fallback"),
            archetype=_arch, dcf_role=_dcf_role,
            allowlist_size=len(domains), ir_domain_present=bool(meta["ir_domain"]),
            memory_chars=len(memory_md or ""),
            web_search_max_uses=MAX_TOOL_ITER,
        )
        print(f"  [params] {json.dumps(run_params, default=str)}", flush=True)
        # Per-run zero-actionable visibility: state which gate killed it and
        # what would have to change, instead of a bare BROKEN.
        if not (parsed.get("position_size_pct") or 0):
            _diag = diagnose_verdict({**parsed, "ticker": ticker, "spot_at_run": spot})
            print(f"  [gate_diagnosis] killed by {_diag.get('killed_by')}", flush=True)
            for _c in _diag.get("what_would_change", []):
                print(f"    → {_c}", flush=True)
    except Exception as e:
        run_params = None
        print(f"  [params] WARN: parameter block failed — {e}", file=sys.stderr, flush=True)

    cited = extract_cited_domains(result["raw_blocks"])
    coverage = coverage_quality(len(cited))
    print(f"  cited domains ({len(cited)}, {coverage}): {', '.join(cited[:8])}{'...' if len(cited) > 8 else ''}", flush=True)

    # 6. Save markdown
    run_at = datetime.now(timezone.utc)
    md_path = save_markdown(ticker, run_at, text)
    print(f"  saved markdown → {md_path.relative_to(REPO_ROOT)}", flush=True)

    # 7. Lazy IR-domain enrichment: if any cited domain looks like an IR site
    # for this company, persist it to the cache for future runs.
    if not meta["ir_domain"]:
        company_lower = meta["company_name"].lower().split()[0] if meta["company_name"] else ""
        for dom in cited:
            # Precedence fix (2026-07-08): the old `a and b and c or d` bound as
            # `(a and b and c) or d`, so with an EMPTY company name the second
            # clause ("" in anything → True) cached the first cited domain as
            # the IR site. Both branches require a company name.
            if company_lower and ((company_lower in dom and "investor" in dom)
                                  or company_lower in dom.replace("-", "")):
                update_ir_domain(ticker, dom)
                print(f"  enriched ir_cache: {ticker} → {dom}", flush=True)
                break

    # 8. Build Supabase row
    row = {
        "ticker": ticker.upper(),
        "run_at": run_at.isoformat(),
        "prompt_version": prompt_version,
        "thesis_target": parsed.get("thesis_target"),
        "breakout_price": parsed.get("breakout_price"),
        "risk_adj_target": parsed.get("risk_adj_target"),
        "conviction": parsed.get("conviction"),                       # Type B — trade-level (price-dependent)
        "strategic_conviction": parsed.get("strategic_conviction"),   # Type A — structural (price-independent); was computed then dropped
        "risk_adj_ev_ratio": parsed.get("risk_adj_ev_ratio"),         # the trade-asymmetry ratio that drives the BROKEN clamp; persist it so the verdict is auditable
        "thesis_horizon_years": parsed.get("thesis_horizon_years"),   # L1: the clock this verdict was judged on (gate thresholds are annualized-equivalent)
        "position_size_pct": parsed.get("position_size_pct"),
        "buy_below": parsed.get("buy_below"),
        "trim_above": parsed.get("trim_above"),
        "filters": parsed.get("filters", {}),
        "top_risks": parsed.get("top_risks", []),
        "top_catalysts": parsed.get("top_catalysts", []),
        "kill_triggers": parsed.get("kill_triggers", []),
        "kill_gate_override": parsed.get("kill_gate_override"),  # D1: structured override (or None)
        "model_d_bracket": parsed.get("model_d_bracket"),        # Model D: vision-vs-floor bracket (or None)
        "run_parameters": run_params,                            # L4: the parameters this verdict was judged under (or None)
        "spot_at_run": spot,
        "trigger_reason": trigger_reason,
        "markdown_path": str(md_path.relative_to(REPO_ROOT)),
        "raw_response_blocks": result["raw_blocks"],
        "coverage_quality": coverage,
        "cited_domains": cited,
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "web_search_count": result["web_search_count"],
    }

    if supabase:
        try:
            thesis_id = write_to_supabase(row)
            _log_outcome_if_possible(thesis_id)
            print("  wrote row to Supabase theses", flush=True)
            # BUILD_PLAN_v2 Phase 2: dual-write to socratic_analyses (mode=auto)
            # Best-effort; failures here do not abort the run.
            sa_id = write_socratic_auto(thesis_id, row, parsed)
            if sa_id is not None:
                print(f"  wrote socratic_analyses row (auto mode, id={sa_id})", flush=True)
        except Exception as e:
            print(f"  [WARN] Supabase write failed: {e}", file=sys.stderr)

    print(f"  thesis_target={parsed.get('thesis_target')} conviction={parsed.get('conviction')} "
          f"position={parsed.get('position_size_pct')}%", flush=True)
    print(f"  tokens in/out: {result['input_tokens']}/{result['output_tokens']}, "
          f"web_searches: {result['web_search_count']}", flush=True)

    # 9 (NEW): memory update — runs AFTER Supabase persistence so failure here
    # never blocks the thesis from being saved.
    try:
        from lib.memory import extract_hume_notes
        prior_notes = extract_hume_notes(memory_md or "")

        new_memory = call_claude_memory_update(
            ticker=ticker.upper(),
            company_name=meta["company_name"],
            existing_memory=memory_md or "",
            new_thesis_json=parsed,
            new_thesis_markdown=text,
            new_run_date=run_at.strftime("%Y-%m-%d"),
            new_prompt_version=prompt_version,
        )
        if new_memory:
            from lib.memory import normalize_notes
            new_notes = extract_hume_notes(new_memory)
            prior_norm = normalize_notes(prior_notes)
            new_norm = normalize_notes(new_notes)
            if prior_notes and not new_notes:
                print("  [memory] HARD WARNING: prior memory had `## Hume Notes` "
                      "but new memory does not. REFUSING WRITE — existing memory "
                      "preserved. Re-run after fixing the maintenance prompt.",
                      file=sys.stderr)
            elif prior_notes and new_notes and prior_norm != new_norm:
                print("  [memory] HARD WARNING: `## Hume Notes` content was "
                      "MODIFIED (should be preserved verbatim). REFUSING WRITE.",
                      file=sys.stderr)
            else:
                if not prior_notes and new_notes:
                    print(f"  [memory] INFO: new memory has a `## Hume Notes` "
                          f"section that wasn't in the prior memory. If you did "
                          f"NOT write this, edit "
                          f"data/memory/{ticker.upper().replace('.', '_')}.md "
                          f"and delete the `## Hume Notes` section before the "
                          f"next thesis run — otherwise it will be preserved as "
                          f"if you wrote it.",
                          file=sys.stderr, flush=True)
                mp = save_memory(ticker, new_memory)
                print(f"  updated memory → {mp.relative_to(REPO_ROOT)}", flush=True)
        else:
            print("  [memory] no update (skipped or failed) — existing memory unchanged", flush=True)
    except Exception as e:
        print(f"  [memory] update failed: {e}", file=sys.stderr)

    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", help="Ticker to run (e.g. LITE, AEHR, 6082.HK)")
    parser.add_argument("--trigger-reason", default="manual",
                        choices=["manual", "earnings", "guidance_change", "contract", "kill_state_change", "scheduled"])
    parser.add_argument("--no-supabase", action="store_true", help="Skip writing to Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Build prompt but skip API call")
    parser.add_argument(
        "--override-suspect-recent",
        action="store_true",
        help=(
            "Bypass Module 1's recent-quarter sanity check. Use ONLY when the operator "
            "has cross-checked against the 10-Q and confirmed the apparent anomaly is "
            "real (e.g. post-spinoff jump like SNDK, post-IPO first quarter, M&A close). "
            "For genuine provider bugs (e.g. MU yfinance/EODHD anomaly), the OVERRIDE "
            "produces a thesis built on bad numbers — DO NOT USE."
        ),
    )
    args = parser.parse_args()

    run_one(
        args.ticker,
        trigger_reason=args.trigger_reason,
        supabase=not args.no_supabase,
        dry_run=args.dry_run,
        override_suspect_recent=args.override_suspect_recent,
    )


if __name__ == "__main__":
    main()
