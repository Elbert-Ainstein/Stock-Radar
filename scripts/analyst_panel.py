"""
analyst_panel.py — cross-node "chain" sense-making layer (thin vertical slice).

Every model in the system (Socratic A/B/C, Model D) reasons about ONE company.
Nothing maintains a standing view of the *chain* — where each supply-chain node
sits in its cycle, and how a node's state PROPAGATES to its neighbours (memory
tightness → optical demand → custom-silicon pull). This layer fills that gap.

Architecture (the key design choices, per the review of the original spec):
  - It is a CONTEXT PRODUCER, not a trade generator. Output is a structured
    `[CHAIN]` block injected into the per-stock judgment alongside [MACRO]/[WAVE]/
    [VIX] — the same mechanism that already moves Socratic verdicts. So it
    demonstrably *changes a decision*; it never emits a trade.
  - The LLM judges each node's cycle clock; the CROSS-NODE PROPAGATION is a pure,
    deterministic rule engine over those clocks + chain edges (auditable, tested).
  - Runs on its own low cadence (it persists to data/analyst_panel.json); per-stock
    runs only LOAD the latest block (cheap). Refresh with `python analyst_panel.py`.
  - Anchoring guard: prior duration estimates are kept as READ-ONLY history and are
    NOT fed back into generation (the documented memory-contamination failure mode).

Pure pieces (parse / propagate / render / load) are unit-tested. The node-analyst
LLM call and `run_panel` are guarded.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Load .env so standalone / cron runs pick up ANTHROPIC_API_KEY (and SUPABASE_*)
# the same way run_socratic/run_thesis do at import. Guarded: importing this module
# (e.g. for load_chain_context) must never hard-fail.
try:
    from utils import load_env as _load_env
    _load_env()
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PANEL_STATE_PATH = REPO_ROOT / "data" / "analyst_panel.json"

POSITIONS = ("accelerating", "peaking", "decelerating", "trough", "unknown")
CONFIDENCES = ("HIGH", "MEDIUM", "LOW")

# Full AI compute chain (7 nodes). Extensible — add nodes/edges to grow it.
# edges are directed: a->b means a's cycle state informs (propagates demand into) b.
# Demand leads at compute (hyperscaler GPU buildout) and pulls components; component
# nodes in turn pull passives/materials downstream.
DEFAULT_CHAIN: dict = {
    "name": "AI compute chain",
    "nodes": {
        "compute":        {"label": "Compute (GPU/CPU)",         "tickers": ["NVDA", "AMD"]},
        "memory":         {"label": "Memory (HBM/DRAM)",         "tickers": ["MU", "000660.KS", "005930.KS"]},
        "optical":        {"label": "Optical (EML/1.6T/3.2T)",   "tickers": ["LITE", "COHR"]},
        "custom_silicon": {"label": "Custom silicon (XPU/ASIC)", "tickers": ["MRVL", "AVGO"]},
        "power":          {"label": "Power & cooling (800V)",    "tickers": ["NVTS", "VRT"]},
        "passives":       {"label": "Passives (MLCC)",           "tickers": ["6981.T", "6976.T"]},
        "materials":      {"label": "Materials (substrates/ABF/InP)", "tickers": ["3110.T", "2802.T", "4005.T"]},
    },
    "edges": [
        # compute demand pulls the component nodes
        ["compute", "memory"], ["compute", "optical"], ["compute", "custom_silicon"], ["compute", "power"],
        # component production pulls passives/materials downstream
        ["memory", "passives"], ["passives", "materials"],
        ["optical", "materials"], ["custom_silicon", "materials"],
    ],
}

# Staleness: a persisted chain block older than this is treated as not-fresh.
CHAIN_STALE_DAYS = 7


@dataclass
class NodeClock:
    node: str
    position: str               # one of POSITIONS
    duration_quarters: Optional[float]
    confidence: str             # one of CONFIDENCES
    read: str                   # one-line view


# ── Pure: parse a model's node read ─────────────────────────────────────────────

def parse_node_clock(node: str, data: dict) -> NodeClock:
    """Validate + build a NodeClock from model JSON. Raises ValueError on bad input."""
    if not isinstance(data, dict):
        raise ValueError(f"{node}: expected an object")
    pos = str(data.get("position", "")).strip().lower()
    if pos not in POSITIONS:
        raise ValueError(f"{node}: position {pos!r} not in {POSITIONS}")
    conf = str(data.get("confidence", "")).strip().upper()
    if conf not in CONFIDENCES:
        raise ValueError(f"{node}: confidence {conf!r} not in {CONFIDENCES}")
    dur = data.get("duration_quarters")
    if isinstance(dur, bool):  # bool is an int subclass — float(True)==1.0 would slip through
        raise ValueError(f"{node}: duration_quarters must be a number, not a bool")
    if dur is not None:
        try:
            dur = float(dur)
        except (TypeError, ValueError):
            raise ValueError(f"{node}: duration_quarters not a number: {dur!r}")
        if not math.isfinite(dur):
            raise ValueError(f"{node}: duration_quarters must be finite")
        if dur < 0:
            raise ValueError(f"{node}: duration_quarters must be >= 0")
    # Defensive: strip braces from free-text so the block can never collide with a
    # downstream .format() (run_socratic's fill is []-placeholder based, so this is
    # belt-and-suspenders, but cheap and future-proof).
    read = str(data.get("read", "")).strip().replace("{", "(").replace("}", ")")
    return NodeClock(node=node, position=pos, duration_quarters=dur,
                     confidence=conf, read=read)


# ── Pure: cross-node propagation (the heart of the layer) ───────────────────────

def derive_propagation(clocks: dict[str, NodeClock], edges: list) -> list[dict]:
    """Deterministic cross-node flags from node cycle clocks + chain edges.

    For each edge a→b: an accelerating/peaking upstream is a demand TAILWIND for the
    downstream; a decelerating upstream is a HEADWIND; a large duration mismatch
    between adjacent nodes is a GAP worth reconciling (the disagreement-is-signal idea).
    """
    flags: list[dict] = []
    seen: set = set()
    for edge in edges:
        a, b = edge[0], edge[1]
        if a == b or (a, b) in seen:   # skip self-loops + duplicate edges
            continue
        seen.add((a, b))
        ca, cb = clocks.get(a), clocks.get(b)
        if ca is None or cb is None:
            continue
        dur_a = f"~{ca.duration_quarters:g}Q" if ca.duration_quarters is not None else "dur?"
        if ca.position in ("accelerating", "peaking"):
            flags.append({"type": "tailwind", "from": a, "to": b,
                          "note": f"{a} {ca.position} ({dur_a}) → sustained demand into {b}"})
        elif ca.position == "decelerating":
            flags.append({"type": "headwind", "from": a, "to": b,
                          "note": f"{a} decelerating → demand headwind building for {b}"})
        if (ca.duration_quarters is not None and cb.duration_quarters is not None
                and abs(ca.duration_quarters - cb.duration_quarters) >= 2):
            flags.append({"type": "gap", "from": a, "to": b,
                          "note": (f"duration gap: {a} {ca.duration_quarters:g}Q vs "
                                   f"{b} {cb.duration_quarters:g}Q — reconcile")})
    return flags


# ── Pure: render the [CHAIN] context block ──────────────────────────────────────

def render_chain_context(chain: dict, clocks: dict[str, NodeClock],
                         flags: list[dict], as_of: Optional[str] = None) -> str:
    lines = [f"[CHAIN: {chain.get('name', 'supply chain')}]"
             + (f"  (as of {as_of})" if as_of else "")]
    for key, cfg in chain.get("nodes", {}).items():
        c = clocks.get(key)
        if c is None:
            lines.append(f"- {cfg.get('label', key)}: (no read)")
            continue
        dur = f"~{c.duration_quarters:g}Q left" if c.duration_quarters is not None else "duration unknown"
        lines.append(f"- {cfg.get('label', key)}: {c.position}, {dur} ({c.confidence})"
                     + (f" — {c.read}" if c.read else ""))
    if flags:
        lines.append("Cross-node:")
        for f in flags:
            lines.append(f"  • {f['note']}")
    return "\n".join(lines)


# ── Persistence (with read-only history = the anchoring guard) ──────────────────

def save_panel_state(chain: dict, clocks: dict[str, NodeClock], flags: list[dict],
                     path: Path = PANEL_STATE_PATH) -> None:
    as_of = datetime.now(timezone.utc).isoformat()
    payload = {
        "as_of": as_of,
        "chain_name": chain.get("name"),
        "clocks": {k: asdict(v) for k, v in clocks.items()},
        "flags": flags,
        "context_block": render_chain_context(chain, clocks, flags, as_of=as_of[:10]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # prior estimates are preserved as read-only history, NOT fed into the next
    # generation (anchoring guard).
    history = []
    if path.exists():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
            history = (prior.get("history") or [])[-9:]
            history.append({"as_of": prior.get("as_of"),
                            "clocks": prior.get("clocks")})
        except Exception:
            history = []
    payload["history"] = history
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_chain_context(path: Path = PANEL_STATE_PATH,
                       stale_days: int = CHAIN_STALE_DAYS,
                       now: Optional[datetime] = None) -> Optional[str]:
    """Return the latest persisted [CHAIN] block for injection, or None if missing
    or stale. Cheap (a file read) — safe to call on every per-stock run."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    block = data.get("context_block")
    if not block:
        return None
    as_of = data.get("as_of")
    if as_of:
        try:
            dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
            now = now or datetime.now(timezone.utc)
            # total seconds, not .days (which truncates — a file 7d+1s old reads as 7)
            if (now - dt).total_seconds() > stale_days * 86400:
                return f"{block}\n  (stale: last refreshed {str(as_of)[:10]})"
        except Exception:
            pass
    return block


# ── Guarded: node analyst (LLM) + panel run ─────────────────────────────────────

NODE_PROMPT = """You are the analyst for the {label} node of the AI supply chain (representative
names: {tickers}). Give your CURRENT read of where this node sits in its cycle. Reason from
demand drivers, capacity, pricing, and inventory — not from any prior estimate.

Return ONLY JSON:
{{"position": "accelerating|peaking|decelerating|trough", "duration_quarters": <number of quarters
this phase likely lasts>, "confidence": "HIGH|MEDIUM|LOW", "read": "<one sentence>"}}
"""


def analyze_node(node_key: str, node_cfg: dict, *, model: str = "claude-opus-4-8") -> NodeClock:
    """One node's cycle read via the LLM. Raises on failure (caller marks it unknown)."""
    import os
    import re
    import anthropic
    from utils import create_message

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)
    prompt = NODE_PROMPT.format(label=node_cfg.get("label", node_key),
                                tickers=", ".join(node_cfg.get("tickers", [])))
    resp = create_message(client, model=model, max_tokens=400, temperature=0.2,
                          messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"{node_key}: no JSON in response")
    return parse_node_clock(node_key, json.loads(m.group(0)))


def run_panel(chain: dict = DEFAULT_CHAIN, *, persist: bool = True) -> dict:
    """Run the panel: each node's cycle read + cross-node propagation + persisted
    [CHAIN] block. Guarded per node (a failing node becomes 'unknown')."""
    clocks: dict[str, NodeClock] = {}
    for key, cfg in chain.get("nodes", {}).items():
        try:
            clocks[key] = analyze_node(key, cfg)
            c = clocks[key]
            print(f"  [panel] {key}: {c.position} ({c.confidence}) "
                  f"dur={c.duration_quarters}", flush=True)
        except Exception as e:
            print(f"  [panel] {key}: unknown — {e}", flush=True)
            clocks[key] = NodeClock(node=key, position="unknown", duration_quarters=None,
                                    confidence="LOW", read="(no read)")
    flags = derive_propagation(clocks, chain.get("edges", []))
    block = render_chain_context(chain, clocks, flags,
                                 as_of=datetime.now(timezone.utc).isoformat()[:10])
    if persist:
        save_panel_state(chain, clocks, flags)
    return {"clocks": clocks, "flags": flags, "context_block": block}


def main():
    r = run_panel()
    print("\n" + r["context_block"])
    print(f"\nsaved → {PANEL_STATE_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
