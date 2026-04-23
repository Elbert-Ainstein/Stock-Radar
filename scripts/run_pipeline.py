#!/usr/bin/env python3
"""
Master Pipeline Runner
Runs all scouts in parallel, then the analyst sequentially.
Writes progress to .pipeline-progress for the dashboard to poll.

Usage:
    python scripts/run_pipeline.py                # smart mode (default) — archetype-aware scout routing
    python scripts/run_pipeline.py --full         # force all scouts for every stock
    python scripts/run_pipeline.py --fast         # minimal scout set (always-tier only, fastest)
    python scripts/run_pipeline.py --free         # only free scouts (no API keys needed)
    python scripts/run_pipeline.py --ticker AAPL  # run pipeline for a single new stock
"""
import sys
import os
import json
import time
import uuid
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

# ─── Ensure utils loads .env early ───
from utils import load_env, set_run_id
load_env()

from observability import PipelineMetrics, ScoutMetrics

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROGRESS_FILE = DATA_DIR / ".pipeline-progress"
QUEUED_FILE = DATA_DIR / ".pipeline-queued"


def _write_progress(stage: str, message: str, current: int, total: int):
    """Write current pipeline progress to file for dashboard polling.

    Progress-file writes are non-critical — the dashboard poll is a nice-to-
    have, not a hard dependency. Swallow any filesystem errors (e.g. sandbox
    restrictions, read-only mounts, permission quirks) so a failed progress
    write doesn't abort an otherwise-healthy pipeline run.
    """
    progress = {
        "stage": stage,
        "message": message,
        "current": current,
        "total": total,
        "percent": round((current / total) * 100) if total > 0 else 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PROGRESS_FILE.write_text(json.dumps(progress), encoding="utf-8")
    except Exception as e:
        # Sandbox can block specific filenames; never fatal.
        print(f"  [progress] could not write {PROGRESS_FILE.name}: {e}")
    # Always print to terminal regardless of file-write success
    bar_width = 30
    filled = int(bar_width * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)
    pct = progress["percent"]
    print(f"\n  [{bar}] {pct}% — {message}")


def _clear_progress():
    """Remove progress file when pipeline finishes. Non-fatal on failure."""
    try:
        PROGRESS_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _read_queued_tickers() -> list[str]:
    """Read tickers that were added while pipeline was running."""
    try:
        if QUEUED_FILE.exists():
            data = json.loads(QUEUED_FILE.read_text(encoding="utf-8"))
            QUEUED_FILE.unlink(missing_ok=True)
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _try_supabase_start(run_id: str, scouts: list[str], free_only: bool) -> bool:
    """Try to record pipeline start in Supabase."""
    try:
        from supabase_helper import start_pipeline_run
        start_pipeline_run(run_id, scouts, free_only)
        return True
    except Exception as e:
        print(f"  [DB] Could not record pipeline start: {e}")
        return False


def _try_supabase_complete(run_id: str, success: bool, stock_count: int,
                           scout_details: dict, error: str | None, log_tail: str, duration: float):
    """Try to record pipeline completion in Supabase."""
    try:
        from supabase_helper import complete_pipeline_run
        complete_pipeline_run(run_id, success, stock_count, scout_details, error, log_tail, duration)
    except Exception as e:
        print(f"  [DB] Could not record pipeline completion: {e}")


def run_single_ticker(ticker: str):
    """Run pipeline for a single newly-added stock."""
    # Set up a run_id so signals/analysis can be saved to Supabase
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_mini_" + uuid.uuid4().hex[:4]
    set_run_id(run_id)

    print(f"\n{'='*60}")
    print(f"  MINI-PIPELINE for {ticker}  (run: {run_id})")
    print(f"{'='*60}")

    _write_progress("quant", f"Running quant scout for {ticker}...", 1, 4)
    try:
        from scout_quant import main as run_quant
        run_quant()
        print(f"  [OK] Quant scout done for {ticker}")
    except Exception as e:
        print(f"  [FAIL] Quant scout failed for {ticker}: {e}")

    _write_progress("analyst", f"Running analyst for {ticker}...", 2, 4)
    try:
        from analyst import main as run_analyst
        run_analyst()
        print(f"  [OK] Analyst done for {ticker}")
    except Exception as e:
        print(f"  [FAIL] Analyst failed for {ticker}: {e}")

    _write_progress("model", f"Generating target model for {ticker}...", 3, 4)
    try:
        from generate_model import generate_for_ticker
        result = generate_for_ticker(ticker)
        if result:
            print(f"  [OK] Model generated for {ticker}")
        else:
            print(f"  [WARN] Model generation returned no result for {ticker}")
    except Exception as e:
        print(f"  [FAIL] Model generation failed for {ticker}: {e}")
        import traceback
        traceback.print_exc()

    _write_progress("done", f"{ticker} pipeline complete", 4, 4)
    print(f"\n  Mini-pipeline for {ticker} complete!")


def run():
    free_only = "--free" in sys.argv
    # Default is smart routing (archetype-aware). Use --full to force all scouts,
    # or --fast for minimum viable signal set only.
    force_full = "--full" in sys.argv
    smart_mode = not force_full
    research_mode = "fast" if "--fast" in sys.argv else ("full" if force_full else "smart")
    single_ticker = None
    if "--ticker" in sys.argv:
        idx = sys.argv.index("--ticker")
        if idx + 1 < len(sys.argv):
            single_ticker = sys.argv[idx + 1].upper()

    # Single-ticker mode (called from stock add)
    if single_ticker:
        run_single_ticker(single_ticker)
        _clear_progress()
        return

    # Generate unique run ID
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    set_run_id(run_id)

    # Determine which scouts will run
    scouts = ["quant", "insider", "social"]
    if not free_only:
        scouts += ["news", "catalyst", "moat", "fundamentals", "youtube"]
    scouts.append("analyst")  # analyst is always run
    scouts.append("feedback")  # feedback loop (outcome tracking + accuracy)
    if not free_only:
        scouts.append("models")  # target price model generation
    total_stages = len(scouts)

    metrics = PipelineMetrics()

    mode_label = f"  Mode: {research_mode}" if smart_mode else ""
    print("+" + "=" * 58 + "+")
    print("|   STOCK RADAR — DAILY PIPELINE                           |")
    print("|   " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f"  Run: {run_id}              |")
    print(f"|   Stages: {total_stages} ({', '.join(scouts)})                     |")
    if smart_mode:
        print(f"|   Research mode: {research_mode:<40s}|")
    print("+" + "=" * 58 + "+")

    start = time.time()
    _try_supabase_start(run_id, scouts, free_only)

    error_msg = None
    stock_count = 0
    stage_idx = 0

    try:
        # ─── Parallel Scout Execution ─────────────────────────────────
        # All scouts are independent (different data sources), so we run
        # them concurrently to cut wall-clock time by ~80%.

        # Build the default (full) scout list
        all_scout_specs = [
            ("quant", "scout_quant"),
            ("insider", "scout_insider"),
            ("social", "scout_social"),
        ]
        if not free_only:
            all_scout_specs += [
                ("news", "scout_news"),
                ("catalyst", "scout_catalyst"),
                ("moat", "scout_moat"),
                ("fundamentals", "scout_fundamentals"),
                ("youtube", "scout_youtube"),
            ]

        # Smart/fast mode: use research_manager to select scouts
        research_plans = {}  # ticker -> ResearchPlan (populated in smart mode)
        if smart_mode:
            from research_manager import (
                plan_research, SCOUT_MODULE_MAP,
                detect_conflicts, check_sufficiency,
                print_conflict_warnings, print_sufficiency_report,
            )
            # Load archetypes from Supabase to route per-stock
            archetypes_by_ticker = {}
            try:
                from utils import get_watchlist as _get_wl_smart
                wl_smart = _get_wl_smart()
                for stock in wl_smart:
                    t = stock["ticker"]
                    arch = stock.get("archetype")  # jsonb or None
                    plan = plan_research(t, archetype=arch, mode=research_mode)
                    research_plans[t] = plan
                    if arch and isinstance(arch, dict):
                        archetypes_by_ticker[t] = arch.get("primary")
                    print(f"  [plan] {t}: {plan.rationale}")
            except Exception as e:
                print(f"  [research_manager] Could not load archetypes: {e}")
                print("  Falling back to full scout set.")
                smart_mode = False  # disable smart routing, fall through to default

        if smart_mode and research_plans:
            # Union of all scouts needed across all stocks
            needed_scouts = set()
            for plan in research_plans.values():
                needed_scouts.update(plan.scouts_to_run)
            # Filter scout_specs to only the needed scouts
            available = {name for name, _ in all_scout_specs}
            scout_specs = [
                (name, mod) for name, mod in all_scout_specs
                if name in needed_scouts
            ]
            skipped = available - {name for name, _ in scout_specs}
            if skipped:
                print(f"\n  [smart] Skipping scouts not needed by any stock: {', '.join(sorted(skipped))}")
            # Also include filings if needed and not already present
            needed_but_missing = needed_scouts - available
            for s in needed_but_missing:
                if s in SCOUT_MODULE_MAP and not free_only:
                    scout_specs.append((s, SCOUT_MODULE_MAP[s]))
        else:
            scout_specs = all_scout_specs

        def _run_scout(name, import_path, main_func_name="main"):
            """Run a single scout module, returning (name, success, error_msg)."""
            t0 = time.monotonic()
            try:
                mod = __import__(import_path)
                getattr(mod, main_func_name)()
                t1 = time.monotonic()
                metrics.record_scout_run(ScoutMetrics(
                    scout_name=name, start_time=t0, end_time=t1,
                    duration_s=t1 - t0, success=True,
                ))
                return (name, True, None)
            except Exception as e:
                t1 = time.monotonic()
                metrics.record_scout_run(ScoutMetrics(
                    scout_name=name, start_time=t0, end_time=t1,
                    duration_s=t1 - t0, success=False, error_msg=str(e),
                ))
                return (name, False, str(e))

        num_scouts = len(scout_specs)
        stage_idx += 1
        _write_progress("scouts", f"Running {num_scouts} scouts in parallel...", stage_idx, total_stages)
        print("\n\n" + "=" * 60)
        print(f"  RUNNING {num_scouts} SCOUTS IN PARALLEL")
        print("=" * 60)

        scout_results = {}
        SCOUT_TIMEOUT = 600  # 10-minute max for all scouts combined
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_scouts) as executor:
            futures = {
                executor.submit(_run_scout, name, mod): name
                for name, mod in scout_specs
            }
            try:
                for future in concurrent.futures.as_completed(futures, timeout=SCOUT_TIMEOUT):
                    name = futures[future]
                    result_tuple = future.result()
                    scout_results[name] = result_tuple
                    status = "OK" if result_tuple[1] else f"FAIL: {result_tuple[2]}"
                    print(f"  [{status}] {name}")
            except concurrent.futures.TimeoutError:
                # Some scouts didn't finish in time — mark them as failed
                completed_names = set(scout_results.keys())
                for f, name in futures.items():
                    if name not in completed_names:
                        scout_results[name] = (name, False, f"Timed out after {SCOUT_TIMEOUT}s")
                        print(f"  [TIMEOUT] {name} — killed after {SCOUT_TIMEOUT}s")
                        f.cancel()

        # Summary of scout results
        succeeded = [n for n, (_, ok, _) in scout_results.items() if ok]
        failed = [n for n, (_, ok, _) in scout_results.items() if not ok]
        print(f"\n  Scouts complete: {len(succeeded)} succeeded, {len(failed)} failed")
        if failed:
            print(f"  Failed scouts: {', '.join(failed)}")
            for n in failed:
                print(f"    - {n}: {scout_results[n][2]}")

        # ─── Research Manager: Conflict & Sufficiency Analysis ─────
        if smart_mode and research_plans:
            print("\n" + "-" * 60)
            print("  RESEARCH MANAGER — POST-SCOUT ANALYSIS")
            print("-" * 60)
            # Conflict detection (runs once on the global scout results)
            conflicts = detect_conflicts(scout_results)
            print_conflict_warnings(conflicts)
            # Sufficiency check per archetype (use the most common primary)
            for ticker, plan in research_plans.items():
                arch_primary = plan.archetype_primary
                suff = check_sufficiency(arch_primary, scout_results)
                if not suff.sufficient or suff.missing_recommended:
                    print_sufficiency_report(suff, arch_primary)
            print("-" * 60)

        # Advance stage_idx past the parallel scouts block (scouts count as 1 stage
        # in progress, but we keep old total_stages for a meaningful progress bar)
        stage_idx = num_scouts

        # ─── Sequential Post-Scout Stages ─────────────────────────────
        # Analyst, feedback loop, and model generation depend on scout outputs
        # and MUST run after all scouts complete.

        # Analyst
        stage_idx += 1
        _write_progress("analyst", "Running Analyst — aggregating scores & generating composite...", stage_idx, total_stages)
        print("\n\n" + "=" * 60)
        print("  RUNNING ANALYST: AGGREGATION & SCORING")
        print("=" * 60)
        from analyst import main as run_analyst
        result = run_analyst()
        stock_count = len(result) if result else 0

        # Feedback Loop — evaluate signal outcomes & compute scout accuracy
        stage_idx += 1
        _write_progress("feedback", "Running Feedback Loop — evaluating signal outcomes & scout accuracy...", stage_idx, total_stages)
        print("\n\n" + "=" * 60)
        print("  RUNNING FEEDBACK LOOP: SIGNAL OUTCOME TRACKING")
        print("=" * 60)
        try:
            from feedback_loop import run_feedback_loop
            fb_result = run_feedback_loop()
            print(f"  [OK] Feedback loop: {fb_result['outcomes']['evaluated']} outcomes, "
                  f"{fb_result['accuracy_rows']} accuracy rows")
        except Exception as e:
            print(f"  Feedback loop failed: {e}")
            print("  Continuing without feedback data...")

        # Target Price Model Generation (requires Perplexity + Claude keys)
        if not free_only:
            stage_idx += 1
            _write_progress("models", "Generating target price models via Perplexity + Claude...", stage_idx, total_stages)
            print("\n\n" + "=" * 60)
            print("  RUNNING MODEL GENERATOR: TARGET PRICE MODELS")
            print("=" * 60)
            try:
                from generate_model import generate_for_ticker
                from utils import get_watchlist as _get_wl
                wl = _get_wl()
                model_count = 0
                for s in wl:
                    t = s["ticker"]
                    _write_progress("models", f"Generating model for {t}...", stage_idx, total_stages)
                    try:
                        m = generate_for_ticker(t, metrics=metrics)
                        if m:
                            model_count += 1
                            print(f"  [OK] {t} model generated")
                        else:
                            print(f"  [SKIP] {t} — no model returned")
                    except Exception as me:
                        print(f"  [FAIL] {t} model error: {me}")
                print(f"\n  Models generated: {model_count}/{len(wl)}")
            except Exception as e:
                print(f"  Model generation stage failed: {e}")
                print("  Continuing without model updates...")

    except Exception as e:
        error_msg = str(e)
        print(f"\n  PIPELINE ERROR: {e}")

    elapsed = time.time() - start
    success = error_msg is None

    # Collect observability summary and record completion in Supabase
    try:
        scout_details = metrics.summarize()
    except Exception:
        scout_details = {}
    _try_supabase_complete(run_id, success, stock_count, scout_details, error_msg, "", elapsed)

    # Print observability summary before final status
    try:
        metrics.print_summary()
    except Exception as obs_err:
        print(f"  [observability] Could not print summary: {obs_err}")

    if success:
        _write_progress("complete", f"Pipeline complete — {stock_count} stocks analyzed in {elapsed:.1f}s", total_stages, total_stages)
        print(f"\n\n{'='*60}")
        print(f"  ✓ PIPELINE COMPLETE in {elapsed:.1f}s  |  Run: {run_id}")
        print(f"  {stock_count} stocks analyzed")
        print(f"{'='*60}")
    else:
        _write_progress("error", f"Pipeline failed: {error_msg}", stage_idx, total_stages)
        print(f"\n  ✗ PIPELINE FAILED after {elapsed:.1f}s: {error_msg}")

    # Check for stocks queued during this run
    queued = _read_queued_tickers()
    if queued:
        print(f"\n  Found {len(queued)} stock(s) queued during pipeline: {', '.join(queued)}")
        for t in queued:
            _write_progress("queued", f"Running queued pipeline for {t}...", 0, 1)
            run_single_ticker(t)

    _clear_progress()


if __name__ == "__main__":
    run()
