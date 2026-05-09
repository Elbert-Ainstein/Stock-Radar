"""
memory.py - Per-ticker memory document load/save helpers.

Memory documents live at data/memory/{TICKER}.md and accumulate analytical
context across thesis runs. See docs/engine-audit-final/memory-design.md
for the format spec and decay rules.

The runner (scripts/run_thesis.py) calls these:
  - get_memory(ticker) before building the prompt (stage 3a)
  - save_memory(ticker, new_content) after the maintenance pass (stage 9)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_DIR = REPO_ROOT / "data" / "memory"


def _normalize_ticker(ticker: str) -> str:
    """Make a filesystem-safe ticker filename. '6082.HK' -> '6082_HK'."""
    return ticker.upper().replace(".", "_")


def memory_path(ticker: str) -> Path:
    """Return the path to a ticker's memory document."""
    return MEMORY_DIR / f"{_normalize_ticker(ticker)}.md"


def get_memory(ticker: str) -> Optional[str]:
    """Read data/memory/{TICKER}.md if it exists, else None.

    Returns the raw markdown (frontmatter + body) so the runner can pass
    it straight into the [MEMORY_SECTION] placeholder.
    """
    p = memory_path(ticker)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        # Corrupted memory file - log and treat as empty.
        # Memory is INFORMATIVE context, not authoritative — not having it
        # never blocks a thesis run.
        import sys
        print(f"  [memory] WARN: failed to read {p}: {e}", file=sys.stderr)
        return None


def save_memory(ticker: str, content: str) -> Path:
    """Atomically write data/memory/{TICKER}.md.

    Uses write-to-temp-then-rename so a partial write can't corrupt the file.
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    p = memory_path(ticker)
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(p)  # atomic on POSIX; on Windows it's also atomic since 3.3
    return p


def format_prior_context(memory_md: str) -> str:
    """Wrap a memory document in the 'PRIOR CONTEXT' block the prompt expects.

    Empty memory -> empty string (so the placeholder vanishes cleanly when
    no memory exists yet).
    """
    if not memory_md or not memory_md.strip():
        return ""
    return (
        "\n\nPRIOR CONTEXT FOR THIS TICKER\n"
        "\n"
        "Below is a memory document accumulated from previous analyses of this "
        "ticker. Treat it as informative but not authoritative.\n"
        "\n"
        "Re-derive your analysis from current data. Explicitly note where current "
        "evidence converges with or diverges from prior. If a prior conclusion no "
        "longer holds, say so and explain why.\n"
        "\n"
        "Pay particular attention to: (a) thesis-target trajectory — is your "
        "current derivation consistent with the trend, or does it represent a "
        "break? (b) open catalysts/risks — has anything fired, gone stale, or "
        "been resolved? (c) the 'Open Questions' section — does the new evidence "
        "answer any of these?\n"
        "\n"
        "--- BEGIN MEMORY ---\n"
        f"{memory_md.strip()}\n"
        "--- END MEMORY ---\n"
    )


# ─── Hume Notes section detection (for the maintenance prompt) ───
# The memory-update prompt is told to preserve `## Hume Notes` verbatim.
# This helper exists so other code can sanity-check that preservation
# happened (defensive — used in tests once we add them).

HUME_NOTES_RE = re.compile(r"(^[ \t]*## Hume Notes\s*$.*?)(?=^[ \t]*## |\Z)", re.MULTILINE | re.DOTALL)


def normalize_notes(text: Optional[str]) -> str:
    """Whitespace-normalize a notes block for stable equality comparison.

    Aggressive: drops ALL blank lines, strips per-line whitespace, joins
    only the non-empty content lines. Two notes are "equal" if their
    non-empty content lines match in order. Paragraph-break drift, trailing
    whitespace, leading indentation are all ignored.

    Used by run_thesis.py Stage 9 to avoid false-positive HARD WARNINGs
    on harmless reformatting while still firing on real content changes.
    """
    if not text:
        return ""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return "\n".join(lines)


def extract_hume_notes(memory_md: str) -> Optional[str]:
    """If the memory has a `## Hume Notes` section, return its full text.
    Otherwise return None.
    """
    if not memory_md:
        return None
    m = HUME_NOTES_RE.search(memory_md)
    return m.group(1).rstrip() if m else None



# ────────────────────────────────────────────────────────────────────
# Hume Notes section: read/write helpers for the dashboard PUT endpoint.
# These bypass the Sonnet maintenance pass — direct file ops on the
# `## Hume Notes` section only. Other sections of memory.md are untouched.
# ────────────────────────────────────────────────────────────────────

# Header that appears between blocks in a fresh memory file (used when
# creating one from scratch in set_hume_notes if no memory exists yet).
_FRESH_MEMORY_TEMPLATE = """---
ticker: {ticker}
last_run: null
runs_count: 0
prompt_versions_seen: []
---

## Stable Facts
(populated on first thesis run)

{notes_block}
"""


def get_hume_notes_only(ticker: str) -> str:
    """Return just the body of `## Hume Notes` (without the heading line),
    or empty string if no notes exist.

    Used by GET /api/thesis/[ticker]/notes — the dashboard only wants the
    user-editable body, not the heading + frontmatter.
    """
    md = get_memory(ticker)
    if not md:
        return ""
    section = extract_hume_notes(md)
    if not section:
        return ""
    # Strip the leading `## Hume Notes` line (and any blank line right after)
    lines = section.split("\n")
    if lines and lines[0].strip().startswith("## Hume Notes"):
        lines = lines[1:]
    # Strip leading blank lines
    while lines and not lines[0].strip():
        lines = lines[1:]
    return "\n".join(lines).rstrip()


def _sanitize_notes_body(body: str) -> str:
    """Downgrade any `^## ` heading inside a user's notes body to `### `.

    Reason: HUME_NOTES_RE terminates capture at the next `^[ \t]*## ` line.
    A user-written `## My Subheading` inside their notes would prematurely
    end the section on read-back, silently truncating everything after it
    in the UI (and on subsequent saves). Downgrading to `### ` (level-3)
    is the cheapest fix — preserves the user's structure, doesn't trip
    the section-break regex.

    Round-trips through this function are idempotent: `### ` is unaffected.
    """
    if not body:
        return body
    # Match the same `^[ \t]*## ` pattern the HUME_NOTES_RE terminator uses,
    # so a tab-prefixed `\t## Foo` (paste from an indenting editor) is also
    # downgraded — otherwise it would still trip the section regex on read.
    return re.sub(r"^([ \t]*)## ", r"\1### ", body, flags=re.MULTILINE)


def set_hume_notes(ticker: str, notes_body: str) -> Path:
    """Write the `## Hume Notes` section in data/memory/{TICKER}.md.

    Behavior:
      - notes_body empty/whitespace → REMOVES the section entirely (idempotent)
      - section already exists → REPLACES the body in place
      - section does not exist → APPENDS at end of memory file
      - memory file does not exist → creates a stub with frontmatter + notes

    Atomic write (write-temp-then-rename). Returns the path written.
    """
    # Sanitize: downgrade `^## ` lines so HUME_NOTES_RE can't be tricked
    # into terminating early on read-back (would silently truncate UI).
    notes_body = _sanitize_notes_body((notes_body or "").rstrip())
    has_notes = bool(notes_body.strip())

    md = get_memory(ticker)

    if md is None:
        # Bootstrap: no memory file yet
        if not has_notes:
            # Nothing to write — return path without creating a file
            return memory_path(ticker)
        new_section = f"## Hume Notes\n{notes_body}\n"
        new_doc = _FRESH_MEMORY_TEMPLATE.format(ticker=ticker.upper(), notes_block=new_section)
        return save_memory(ticker, new_doc)

    # Memory exists; either replace, remove, or append the section
    existing_section = HUME_NOTES_RE.search(md)

    if existing_section is None:
        # No existing notes section
        if not has_notes:
            # Nothing to do
            return memory_path(ticker)
        # Append at end (preserve trailing newline behavior)
        suffix = "" if md.endswith("\n") else "\n"
        new_doc = md + suffix + f"\n## Hume Notes\n{notes_body}\n"
        return save_memory(ticker, new_doc)

    # Existing section: replace or remove
    if not has_notes:
        # Remove the section entirely. Slice it out and clean up double blank lines.
        before = md[:existing_section.start()].rstrip() + "\n"
        after = md[existing_section.end():].lstrip()
        new_doc = (before + ("\n" + after if after else "")).rstrip() + "\n"
        return save_memory(ticker, new_doc)

    # Replace body — keep the heading line
    new_section = f"## Hume Notes\n{notes_body}\n"
    new_doc = md[:existing_section.start()] + new_section + md[existing_section.end():]
    # Make sure exactly one blank line follows the new section before next ## or EOF
    new_doc = re.sub(r"\n## Hume Notes\n.*?(?=\n[ \t]*## |\Z)", lambda m: m.group(0).rstrip() + "\n\n", new_doc, count=1, flags=re.DOTALL)
    return save_memory(ticker, new_doc)


if __name__ == "__main__":
    # Smoke test
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "LITE"
    p = memory_path(t)
    print(f"path: {p}")
    print(f"exists: {p.exists()}")
    md = get_memory(t)
    print(f"memory length: {len(md) if md else 0} chars")
    print(f"hume notes: {bool(extract_hume_notes(md or ''))}")
