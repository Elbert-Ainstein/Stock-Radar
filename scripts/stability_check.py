"""
stability_check.py — measure Socratic round-1 verdict STABILITY and the [CHAIN]
block's effect, before trusting either.

The seal/grade/calibration loop quietly assumes a single sealed verdict is stable.
Since the judgment models now run on opus-4-8 WITHOUT temperature control (it
rejects the param), that assumption is worth testing. This fires JUST the A/B/C
round (3 calls/iteration — no corpus callosum / research / target) K times under
chain-off and chain-on, then reports:
  - per-model verdict distribution + a CONSISTENCY score (modal frequency; 1.0 =
    perfectly stable),
  - the net directional lean per run + its stability,
  - whether the [CHAIN] block shifts the modal lean by MORE than the within-
    condition noise (signal) or not (noise).

Cost: K × 2 × 3 model calls (e.g. K=5 → 30 opus-4-8 calls). The aggregation is
PURE + unit-tested; the runner is guarded.

Usage:  python stability_check.py LITE --k 5
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Optional

try:
    from utils import load_env as _load_env
    _load_env()
except Exception:
    pass

# direction mapping reused from the seal layer so "lean" means the same thing here
try:
    from checkpoint_seal import verdict_direction, net_direction
except Exception:  # keep pure tests importable even if checkpoint_seal moves
    verdict_direction = None
    net_direction = None

# ── Pure aggregation ────────────────────────────────────────────────────────────

def modal_consistency(values: list, ignore_none: bool = True) -> tuple[Optional[str], float]:
    """(modal value, modal frequency). Frequency 1.0 = perfectly stable; 1/n = max
    spread. Empty -> (None, 0.0).

    ignore_none=True (per-model verdicts): drop Nones (e.g. model C has no verdict).
    ignore_none=False (the net LEAN): keep None as a category — a None lean means the
    models CONFLICTED that run, which is instability and must count, not be dropped.
    """
    vals = [v for v in values if v is not None] if ignore_none else list(values)
    if not vals:
        return None, 0.0
    c = Counter(vals)
    top, n = c.most_common(1)[0]
    return top, round(n / len(vals), 3)


def summarize_condition(runs: list[dict]) -> dict:
    """runs: list of {'a':verdict,'b':verdict,'c':verdict} across K iterations.

    Returns per-model distribution + consistency, and the net-lean distribution +
    consistency across runs (lean via net_direction over the 3 verdicts)."""
    per_model = {}
    for role in ("a", "b", "c"):
        verdicts = [r.get(role) for r in runs]
        dist = dict(Counter(v for v in verdicts if v is not None))
        modal, cons = modal_consistency(verdicts)
        per_model[role] = {"distribution": dist, "modal": modal, "consistency": cons}

    leans = []
    for r in runs:
        if net_direction is not None:
            # net_direction expects {a:{verdict:...}} shape
            shaped = {role: {"verdict": r.get(role)} for role in ("a", "b", "c")}
            leans.append(net_direction(shaped))
        else:
            leans.append(None)
    # keep None (= models conflicted that run) as a real category for the lean
    lean_modal, lean_cons = modal_consistency(leans, ignore_none=False)
    return {
        "n": len(runs),
        "per_model": per_model,
        # None = the A/B directional voters CONFLICTED that run — show it as a
        # real category ("conflict"), don't drop it (that hid 4/5 runs).
        "lean_distribution": dict(Counter((l if l is not None else "conflict") for l in leans)),
        "modal_lean": lean_modal,
        "lean_consistency": lean_cons,
    }


def compare_conditions(off: dict, on: dict, min_consistency: float = 0.6) -> dict:
    """Did the [CHAIN] block move the verdict by MORE than the within-condition noise?

    The shift is 'signal' only if the modal lean changed AND both conditions were
    internally consistent enough (>= min_consistency) that the change isn't just
    sampling jitter. Otherwise it's 'noise' or 'inconclusive (too noisy to tell)'.
    """
    off_lean, on_lean = off.get("modal_lean"), on.get("modal_lean")
    both_consistent = (off.get("lean_consistency", 0) >= min_consistency
                       and on.get("lean_consistency", 0) >= min_consistency)
    changed = off_lean != on_lean
    if not both_consistent:
        verdict = "inconclusive (within-condition variance too high to attribute)"
    elif changed:
        verdict = "signal (chain shifted the lean beyond the noise)"
    else:
        verdict = "no effect (lean unchanged, both conditions stable)"
    return {
        "off_modal_lean": off_lean, "on_modal_lean": on_lean,
        "off_lean_consistency": off.get("lean_consistency"),
        "on_lean_consistency": on.get("lean_consistency"),
        "chain_changed_lean": changed,
        "verdict": verdict,
    }


def render_report(ticker: str, off: dict, on: dict, cmp: dict) -> str:
    lines = [f"=== stability: {ticker} (K={off['n']} per condition) ==="]
    for name, s in (("chain OFF", off), ("chain ON", on)):
        ml = s["modal_lean"] if s["modal_lean"] is not None else "conflict/none"
        lines.append(f"\n[{name}]  modal lean={ml} "
                     f"(consistency {s['lean_consistency']:.0%})  lean dist={s['lean_distribution']}")
        for role in ("a", "b", "c"):
            m = s["per_model"][role]
            lines.append(f"  {role}: modal={m['modal']} consistency={m['consistency']:.0%} dist={m['distribution']}")
    lines.append(f"\nCHAIN EFFECT: {cmp['verdict']}")
    return "\n".join(lines)


# ── Guarded runner ──────────────────────────────────────────────────────────────

def _round_verdicts(ctx: dict, allowed_domains) -> dict:
    from run_socratic import run_round_1_parallel
    r = run_round_1_parallel(ctx, allowed_domains)
    return {role: (r[role].get("parsed") or {}).get("verdict") for role in ("a", "b", "c")}


def run_stability(ticker: str, k: int = 5, price: Optional[float] = None) -> dict:
    import json
    from run_socratic import build_context, SOURCES_PATH

    try:
        cfg = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        allowed = (cfg.get("tier_1_filings", []) + cfg.get("tier_2_press", [])
                   + cfg.get("tier_3_newswires", []) + cfg.get("tier_4_data", [])) or None
    except Exception:
        allowed = None

    if price is not None:
        print(f"  [stability] price pinned at ${price:.2f} — drift-free A/B", flush=True)

    out = {}
    for cond, include_chain in (("off", False), ("on", True)):
        ctx = build_context(ticker, include_chain=include_chain, spot_override=price)
        runs = []
        for i in range(k):
            try:
                v = _round_verdicts(ctx, allowed)
            except Exception as e:
                print(f"  [stability] {cond} run {i+1}: failed — {e}", flush=True)
                v = {"a": None, "b": None, "c": None}
            print(f"  [stability] chain {cond} {i+1}/{k}: A={v['a']} B={v['b']} C={v['c']}", flush=True)
            runs.append(v)
        out[cond] = summarize_condition(runs)
    cmp = compare_conditions(out["off"], out["on"])
    print("\n" + render_report(ticker, out["off"], out["on"], cmp))
    return {"off": out["off"], "on": out["on"], "comparison": cmp}


def main():
    ap = argparse.ArgumentParser(description="Measure Socratic round-1 verdict stability + chain effect.")
    ap.add_argument("ticker")
    ap.add_argument("--k", type=int, default=5, help="runs per condition (cost: k×2×3 model calls)")
    ap.add_argument("--price", type=float, default=None,
                    help="pin spot price across all conditions/runs (skip live fetch) so a "
                         "verdict-variance A/B isn't confounded by intraday drift; pass the "
                         "SAME value to the N=1 and N=5 runs for a clean comparison")
    args = ap.parse_args()
    run_stability(args.ticker, k=args.k, price=args.price)


if __name__ == "__main__":
    main()
