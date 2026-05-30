#!/usr/bin/env python3
"""
run_architecture_experiment.py — automated V3.4.2 vs V4 spike comparison
across multiple tickers. One command, full experiment.

Per Hume request 2026-05-10: replace the 50-command manual experiment with
one script that runs both architectures, parses outputs, and aggregates a
comparison matrix. Resume-safe (writes per-ticker results incrementally so
Ctrl+C doesn't lose progress).

USAGE
=====
    # Run both architectures across 5 tickers
    python scripts/run_architecture_experiment.py --tickers AMD,COHR,ALAB,AMAT,U

    # Run only V3.4.2 (Phase 1 of staged experiment)
    python scripts/run_architecture_experiment.py --tickers AMD,COHR,ALAB --variants v342

    # Run V4 spike only on the ones where V3.4.2 emitted HIGH/MEDIUM
    python scripts/run_architecture_experiment.py --tickers AMD,COHR --skip-v4-on-broken

    # Preview cost before running
    python scripts/run_architecture_experiment.py --tickers AMD,COHR,ALAB --dry-run

    # Resume from a previous run (re-uses output dir; skips already-done tickers)
    python scripts/run_architecture_experiment.py --tickers AMD,COHR --resume <TIMESTAMP>

OUTPUTS
=======
data/architecture_experiments/<TIMESTAMP>/
  ├── matrix.md             — comparison table across all tickers
  ├── per_ticker/
  │     └── <TICKER>_comparison.md   — full V3.4.2 vs V4 side-by-side
  ├── progress.json         — for resume
  └── results.csv           — machine-readable matrix
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


# ─── Cost estimates (rough, from observed runs today) ────────────────
# V3.4.2: 1 Sonnet + 7 web searches ≈ $3-5 per run
# V4 spike: 4 Sonnet calls (R1×2, R2×2) ≈ $12-20 per run
COST_V342 = 4.0       # midpoint $/run
COST_V4_SPIKE = 16.0  # midpoint $/run


def parse_v342_output(ticker: str) -> dict:
    """Read the most recent V3.4.2 thesis markdown, parse closing JSON."""
    theses_dir = REPO_ROOT / "data" / "theses"
    candidates = sorted(theses_dir.glob(f"{ticker}_*.md"))
    if not candidates:
        return {"error": f"no V3.4.2 markdown found for {ticker}"}
    latest = candidates[-1]
    text = latest.read_text(encoding="utf-8")
    m = re.search(r"```json\s*(\{[\s\S]+?\})\s*```", text)
    if not m:
        return {"markdown_path": str(latest.relative_to(REPO_ROOT)),
                "error": "no closing JSON found"}
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        return {"markdown_path": str(latest.relative_to(REPO_ROOT)),
                "error": f"JSON parse failed: {e}"}
    return {"markdown_path": str(latest.relative_to(REPO_ROOT)), "json": data}


def parse_v4_tactical(v4_out_dir: Path) -> dict:
    """Read round2_tactical.md from V4 spike output, extract structured fields."""
    f = v4_out_dir / "round2_tactical.md"
    if not f.exists():
        return {"error": "round2_tactical.md not found"}
    text = f.read_text(encoding="utf-8")

    state_match = re.search(r"STATE:\s*(AGREED|PROPOSING|STUCK)", text, re.I)
    state = state_match.group(1).upper() if state_match else "?"

    def grab(label: str) -> str | None:
        # Try multiple patterns: bold-table, bold-colon, plain colon
        # Allow $, digits, %, and common conviction tokens.
        VAL = r"\*?\*?(\$?[\d,.]+\s*\(.*?\)|\$?[\d,.]+|HIGH|MEDIUM|MODERATE|LOW|BROKEN|STRONG|WEAK|0%?|\d+%?)"
        patterns = [
            rf"\*\*{label}\*\*\s*\|\s*{VAL}",
            rf"\|\s*\*?\*?{label}\*?\*?\s*\|\s*{VAL}",
            rf"\*\*{label}\*\*\s*[:=]\s*{VAL}",
            rf"\b{label}\b\s*[:=]\s*{VAL}",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                return m.group(1).strip()
        return None

    return {
        "state": state,
        "trade_target": grab("trade_target") or grab("trade target"),
        "trade_conviction": grab("trade_conviction") or grab("trade conviction"),
        "position_size_pct": grab("position_size_pct") or grab("position size"),
        "buy_below": grab("buy_below") or grab("buy below"),
        "tactical_path": str(f.relative_to(REPO_ROOT)),
    }


def write_per_ticker_comparison(out_root: Path, ticker: str,
                                 v342_data: dict, v4_data: dict | None) -> None:
    p = out_root / "per_ticker" / f"{ticker}_comparison.md"
    p.parent.mkdir(parents=True, exist_ok=True)

    j = v342_data.get("json", {})
    lines = [
        f"# {ticker} — V3.4.2 vs V4 spike comparison",
        "",
        "## V3.4.2 (production single-call)",
        "",
    ]
    if v342_data.get("error"):
        lines.append(f"**Error:** {v342_data['error']}")
    else:
        lines.extend([
            f"- thesis_target: **{j.get('thesis_target', '?')}**",
            f"- conviction: **{j.get('conviction', '?')}**",
            f"- strategic_conviction: {j.get('strategic_conviction', '(not in output — pre-v3.4.2 run?)')}",
            f"- position_size_pct: **{j.get('position_size_pct', '?')}%**",
            f"- buy_below: {j.get('buy_below', '?')}",
            f"- trim_above: {j.get('trim_above', '?')}",
            f"- markdown: `{v342_data.get('markdown_path', '?')}`",
        ])
    lines.append("")
    lines.append("## V4 spike (two-agent dialogue, 2-round bounded)")
    lines.append("")
    if v4_data is None:
        lines.append("**SKIPPED** (V3.4.2 emitted BROKEN; --skip-v4-on-broken active)")
    elif v4_data.get("error"):
        lines.append(f"**Error:** {v4_data['error']}")
    else:
        lines.extend([
            f"- state (Tactical R2): **{v4_data.get('state', '?')}**",
            f"- trade_target: **{v4_data.get('trade_target', '?')}**",
            f"- trade_conviction: **{v4_data.get('trade_conviction', '?')}**",
            f"- position_size_pct: **{v4_data.get('position_size_pct', '?')}**",
            f"- buy_below: {v4_data.get('buy_below', '?')}",
            f"- tactical markdown: `{v4_data.get('tactical_path', '?')}`",
        ])
    lines.append("")
    lines.append("## Convergence assessment")
    lines.append("")
    if v4_data is None:
        lines.append("Skipped (V3.4.2 BROKEN; V4 not run).")
    elif v342_data.get("error") or v4_data.get("error"):
        lines.append("One or both architectures errored; cannot compare.")
    else:
        v342_conv = (j.get("conviction") or "?").upper()
        v4_conv = (v4_data.get("trade_conviction") or "?").upper()
        # Normalize MEDIUM/MODERATE
        norm = {"MODERATE": "MEDIUM"}
        v342_conv_n = norm.get(v342_conv, v342_conv)
        v4_conv_n = norm.get(v4_conv, v4_conv)
        if v342_conv_n == v4_conv_n and v342_conv_n != "?":
            lines.append(f"**CONVERGENT** — both architectures emitted {v342_conv_n} conviction.")
        else:
            lines.append(f"**DIVERGENT** — V3.4.2={v342_conv_n}, V4 Tactical={v4_conv_n}.")
            lines.append("")
            lines.append("This is the AXON-pattern: secular near-fair-value cases where V4's negative-EV math overrides V3.4.2's strategic-bias-leak. See REPORT.md Appendix C.")
    p.write_text("\n".join(lines), encoding="utf-8")


def write_aggregate_matrix(out_root: Path, results: list, failures: list,
                           tickers: list, variants: set, ts: str) -> Path:
    matrix_path = out_root / "matrix.md"
    lines = [
        "# Architecture experiment — V3.4.2 vs V4 spike",
        "",
        f"**Run:** {ts}",
        f"**Tickers:** {', '.join(tickers)}",
        f"**Variants:** {', '.join(sorted(variants))}",
        "",
        "## Comparison matrix",
        "",
        "| Ticker | V3.4.2 target | V3.4.2 conv | V3.4.2 strat | V3.4.2 size | V4 state | V4 target | V4 conv | V4 size | V4 buy_below |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| **{r['ticker']}** | {r.get('v342_target', '?')} | "
            f"{r.get('v342_conviction', '?')} | {r.get('v342_strategic', '?')} | "
            f"{r.get('v342_position', '?')}% | {r.get('v4_state', 'skipped')} | "
            f"{r.get('v4_target', '?')} | {r.get('v4_conviction', '?')} | "
            f"{r.get('v4_position', '?')} | {r.get('v4_buy_below', '?')} |"
        )

    # Convergence summary
    convergent = []
    divergent = []
    for r in results:
        v342_c = (r.get("v342_conviction") or "").upper()
        v4_c = (r.get("v4_conviction") or "").upper()
        if v4_c in ("", "SKIPPED", "?", None):
            continue
        norm = {"MODERATE": "MEDIUM"}
        if norm.get(v342_c, v342_c) == norm.get(v4_c, v4_c):
            convergent.append(r["ticker"])
        else:
            divergent.append(r["ticker"])

    lines.extend([
        "",
        "## Convergence summary",
        "",
        f"- **CONVERGENT** (both architectures same conviction): {len(convergent)} — {', '.join(convergent) or '(none)'}",
        f"- **DIVERGENT** (architectures differ on conviction): {len(divergent)} — {', '.join(divergent) or '(none)'}",
        "",
    ])

    if failures:
        lines.append("## Failures")
        lines.append("")
        for t, variant, err in failures:
            lines.append(f"- {t} ({variant}): {err[:200]}")
        lines.append("")

    lines.append("## Per-ticker detail")
    lines.append("")
    for r in results:
        lines.append(f"- [{r['ticker']}](per_ticker/{r['ticker']}_comparison.md)")

    matrix_path.write_text("\n".join(lines), encoding="utf-8")
    return matrix_path


def write_progress(out_root: Path, results: list, failures: list, completed: list) -> None:
    progress = {
        "completed_tickers": completed,
        "results": results,
        "failures": failures,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_root / "progress.json").write_text(json.dumps(progress, indent=2, default=str), encoding="utf-8")


def load_progress(out_root: Path) -> tuple[list, list, list]:
    p = out_root / "progress.json"
    if not p.exists():
        return [], [], []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("results", []), data.get("failures", []), data.get("completed_tickers", [])


def main() -> int:
    ap = argparse.ArgumentParser(description="Architecture experiment runner")
    ap.add_argument("--tickers", required=True, help="comma-separated ticker list")
    ap.add_argument("--variants", default="v342,v4_spike",
                    help="which architectures to run (default: both)")
    ap.add_argument("--skip-v4-on-broken", action="store_true",
                    help="skip V4 spike when V3.4.2 emits BROKEN (saves cost)")
    ap.add_argument("--dry-run", action="store_true", help="preview cost without running")
    ap.add_argument("--resume", default=None, help="resume from prior timestamp dir")
    ap.add_argument("--continue-on-error", action="store_true", default=True,
                    help="don't abort whole experiment on per-ticker failure (default: True)")
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    variants = set(v.strip() for v in args.variants.split(","))

    # Cost preview
    n_v342 = len(tickers) if "v342" in variants else 0
    n_v4 = len(tickers) if "v4_spike" in variants else 0
    if args.skip_v4_on_broken:
        n_v4_max = n_v4
        n_v4 = "?"  # depends on V3.4.2 outputs
    cost_estimate = n_v342 * COST_V342 + (n_v4 if isinstance(n_v4, int) else 0) * COST_V4_SPIKE

    if args.dry_run:
        print("=" * 70)
        print("DRY RUN — preview")
        print("=" * 70)
        print(f"Tickers ({len(tickers)}): {', '.join(tickers)}")
        print(f"Variants: {sorted(variants)}")
        print(f"Skip V4 on BROKEN: {args.skip_v4_on_broken}")
        print()
        print(f"Estimated cost:")
        print(f"  V3.4.2 ({n_v342} runs × ~${COST_V342}): ~${n_v342 * COST_V342:.0f}")
        if isinstance(n_v4, int):
            print(f"  V4 spike ({n_v4} runs × ~${COST_V4_SPIKE}): ~${n_v4 * COST_V4_SPIKE:.0f}")
        else:
            print(f"  V4 spike (≤{n_v4_max} runs × ~${COST_V4_SPIKE}): up to ~${n_v4_max * COST_V4_SPIKE:.0f}")
            print(f"  (lower if some emit BROKEN — V4 will be skipped on those)")
        if isinstance(n_v4, int):
            print(f"  TOTAL: ~${cost_estimate:.0f}")
        else:
            print(f"  TOTAL: ~${n_v342 * COST_V342:.0f} to ~${n_v342 * COST_V342 + n_v4_max * COST_V4_SPIKE:.0f}")
        print()
        print("Run without --dry-run to execute.")
        return 0

    # Lazy import — only after dry-run check, to allow --dry-run without env
    from run_thesis import run_one as run_v342
    from run_thesis_v4_spike import run_v4_spike

    # Set up output dir
    if args.resume:
        out_root = REPO_ROOT / "data" / "architecture_experiments" / args.resume
        if not out_root.exists():
            print(f"ERROR: --resume dir not found: {out_root}")
            return 1
        ts = args.resume
        results, failures, completed = load_progress(out_root)
        print(f"Resuming from {out_root.relative_to(REPO_ROOT)} ({len(completed)} tickers already done)")
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_root = REPO_ROOT / "data" / "architecture_experiments" / ts
        out_root.mkdir(parents=True, exist_ok=True)
        results, failures, completed = [], [], []

    print("=" * 70)
    print(f"ARCHITECTURE EXPERIMENT — {len(tickers)} tickers")
    print(f"Output: {out_root.relative_to(REPO_ROOT)}")
    print("=" * 70)
    print()

    skip_set = set(completed)
    overall_start = time.time()

    for i, ticker in enumerate(tickers, 1):
        if ticker in skip_set:
            print(f"[{i}/{len(tickers)}] {ticker} — already done (resume), skipping")
            continue

        print(f"\n[{i}/{len(tickers)}] === {ticker} ===")
        ticker_start = time.time()
        v342_data = None
        v4_data = None

        # ── V3.4.2 run ──
        if "v342" in variants:
            print(f"  → V3.4.2 production run...")
            try:
                run_v342(ticker, trigger_reason="experiment", supabase=True)
                v342_data = parse_v342_output(ticker)
                if v342_data.get("error"):
                    print(f"    ! parse warning: {v342_data['error']}")
                else:
                    j = v342_data.get("json", {})
                    print(f"    ✓ V3.4.2: target={j.get('thesis_target')}, "
                          f"conv={j.get('conviction')}, "
                          f"size={j.get('position_size_pct')}%, "
                          f"strat={j.get('strategic_conviction', 'n/a')}")
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"    ✗ V3.4.2 FAILED: {e}")
                failures.append([ticker, "v342", str(e)[:200]])
                if not args.continue_on_error:
                    break

        # ── Decide V4 ──
        run_v4 = "v4_spike" in variants
        if run_v4 and args.skip_v4_on_broken and v342_data and not v342_data.get("error"):
            j = v342_data.get("json", {})
            if (j.get("conviction") or "").upper() == "BROKEN":
                print(f"    ⊘ SKIP V4 (V3.4.2=BROKEN, --skip-v4-on-broken active)")
                run_v4 = False

        if run_v4:
            print(f"  → V4 spike run (4 LLM calls)...")
            try:
                v4_dir = run_v4_spike(ticker)
                v4_data = parse_v4_tactical(v4_dir)
                if v4_data.get("error"):
                    print(f"    ! V4 parse warning: {v4_data['error']}")
                else:
                    print(f"    ✓ V4 Tactical: state={v4_data.get('state')}, "
                          f"target={v4_data.get('trade_target')}, "
                          f"conv={v4_data.get('trade_conviction')}, "
                          f"size={v4_data.get('position_size_pct')}, "
                          f"buy_below={v4_data.get('buy_below')}")
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"    ✗ V4 FAILED: {e}")
                failures.append([ticker, "v4_spike", str(e)[:200]])
                if not args.continue_on_error:
                    break

        # ── Per-ticker comparison ──
        write_per_ticker_comparison(out_root, ticker, v342_data or {}, v4_data)

        # ── Stage row for matrix ──
        j = (v342_data or {}).get("json", {})
        row = {
            "ticker": ticker,
            "v342_target": j.get("thesis_target"),
            "v342_conviction": j.get("conviction"),
            "v342_strategic": j.get("strategic_conviction"),
            "v342_position": j.get("position_size_pct"),
            "v4_state": v4_data.get("state") if v4_data else "skipped",
            "v4_target": v4_data.get("trade_target") if v4_data else None,
            "v4_conviction": v4_data.get("trade_conviction") if v4_data else None,
            "v4_position": v4_data.get("position_size_pct") if v4_data else None,
            "v4_buy_below": v4_data.get("buy_below") if v4_data else None,
        }
        results.append(row)
        completed.append(ticker)

        # Persist after each ticker (resume-safe)
        write_progress(out_root, results, failures, completed)
        write_aggregate_matrix(out_root, results, failures, tickers, variants, ts)

        elapsed = time.time() - ticker_start
        print(f"  ⏱ {elapsed:.1f}s for this ticker")

    # ── Final aggregate ──
    matrix_path = write_aggregate_matrix(out_root, results, failures, tickers, variants, ts)
    overall_elapsed = time.time() - overall_start

    print()
    print("=" * 70)
    print(f"DONE — {len(results)} tickers processed, {len(failures)} failures")
    print(f"Total time: {overall_elapsed/60:.1f} min")
    print(f"Matrix: {matrix_path.relative_to(REPO_ROOT)}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[experiment] interrupted by user — partial results saved")
        sys.exit(130)
