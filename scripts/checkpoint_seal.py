"""
checkpoint_seal.py — Rescoped Async Checkpoint Feedback (P0 + P1).

Seals the reasoning fingerprint + system version of a Socratic analysis into
the EXISTING prediction_log table (we extend, not duplicate — see
docs/CHECKPOINT_FEEDBACK_ASSESSMENT_2026-06-01.md).

Design notes baked in from the rescope resolutions:
  - Decision 1 (cohort key): judgment = Socratic prompt_versions (model_a/b/c +
    corpus_callosum) + a content hash of the judgment FILES analyst.py,
    target_engine.py, kill_condition_eval.py. run_socratic.py is deliberately
    NOT in the file set (it churns as orchestration; its judgment content is
    already captured by prompt_versions). [Flag 2]
  - Decision 2 (conviction): a computed proxy = mean(model confidence) ×
    direction-agreement, sealed with conviction_source="proxy" so the judgment
    card can later overwrite with conviction_source="human" and nothing ever
    compares the two as the same measurement.
  - P0 date-pinning: close_on_or_after() returns (price, exact_date_used) so a
    grade can never silently use the wrong day.

The pure functions here have no network/DB/IO side effects (except the two
clearly-marked git/file helpers) and are unit-tested in test_checkpoint_seal.py.
The single DB-touching entry point, seal_socratic_prediction(), is best-effort
and never raises into the caller.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

# Files whose change constitutes a judgment-layer change (cohort-resetting).
# Socratic orchestration (run_socratic.py) is intentionally excluded — its
# judgment content is captured via prompt_versions instead.
JUDGMENT_FILES = ("analyst.py", "target_engine.py", "kill_condition_eval.py")

# Socratic prompt_versions keys that count toward the cohort key.
JUDGMENT_PROMPT_KEYS = ("model_a", "model_b", "model_c", "corpus_callosum")

# Judgment prompt files whose `model:` frontmatter pins the reasoner. A model
# swap here (e.g. sonnet-4-6 -> opus-4-8) is a clock-resetting change and must
# trip a cohort break automatically — independent of whether the prompt VERSION
# string was bumped. Mapped cohort-key key -> prompt filename.
JUDGMENT_PROMPT_FILES = {
    "model_a": "model_a_fundamentals.md",
    "model_b": "model_b_regime.md",
    "model_c": "model_c_adversarial.md",
    "corpus_callosum": "corpus_callosum.md",
}

# Confidence string -> numeric, for the conviction proxy.
_CONFIDENCE_SCORE = {"HIGH": 1.0, "MEDIUM": 0.66, "MED": 0.66, "LOW": 0.33}

# Verdict -> direction. Covers the ACTUAL enums the Socratic models emit:
#   Model A (fundamentals): OVERVALUED / FAIRLY_VALUED / UNDERVALUED
#   Model B (regime):       REGIME_UPSIDE / NO_REGIME_SHIFT / REGIME_DOWNSIDE
#   (Model C is adversarial and emits NO verdict — it is not a directional voter.)
# Plus Chinese + generic synonyms for robustness. Unknown -> None (excluded).
_VERDICT_DIRECTION = {
    # Model A
    "undervalued": 1, "fairly_valued": 0, "fairly valued": 0, "overvalued": -1,
    # Model B
    "regime_upside": 1, "no_regime_shift": 0, "regime_downside": -1,
    # Chinese + generic
    "低估": 1, "公允价值": 0, "高估": -1,
    "upside": 1, "downside": -1, "buy": 1, "sell": -1, "fair": 0, "hold": 0, "neutral": 0,
}


# ── Pure helpers ───────────────────────────────────────────────────────────────

def confidence_score(label: Optional[str]) -> float:
    """Map a HIGH/MEDIUM/LOW confidence label to a number; default 0.5."""
    if not label:
        return 0.5
    return _CONFIDENCE_SCORE.get(str(label).strip().upper(), 0.5)


def verdict_direction(verdict: Optional[str]) -> Optional[int]:
    """Map a verdict label to -1/0/+1, or None if unrecognised."""
    if verdict is None:
        return None
    return _VERDICT_DIRECTION.get(str(verdict).strip().lower() if str(verdict).isascii()
                                 else str(verdict).strip())


def _models(round_1: dict) -> dict[str, dict]:
    """Return {a,b,c: parsed-model-dict}, tolerating missing/None entries."""
    out = {}
    for role in ("a", "b", "c"):
        m = (round_1 or {}).get(role)
        # Accept either shape: result["round_1"] holds the parsed dict directly,
        # while the internal round_1 wraps it as {"parsed": {...}}. Unwrap if wrapped.
        if isinstance(m, dict) and "parsed" in m and isinstance(m["parsed"], dict):
            m = m["parsed"]
        out[role] = m if isinstance(m, dict) else {}
    return out


def direction_agreement(round_1: dict) -> float:
    """Fraction of *recognised-verdict* models sharing the modal direction.

    Denominator is the number of models that expressed a recognised verdict, not
    the raw model count — so 1 unparseable verdict doesn't silently deflate the
    score. Three recognised: unanimous -> 1.0, 2-vs-1 -> 0.667, all-different ->
    0.333. None recognised -> 0.0 (no agreement signal).
    """
    dirs = [verdict_direction(m.get("verdict")) for m in _models(round_1).values()]
    dirs = [d for d in dirs if d is not None]
    if not dirs:
        return 0.0
    modal = max(set(dirs), key=dirs.count)
    return round(dirs.count(modal) / len(dirs), 3)


def conviction_proxy(round_1: dict) -> float:
    """Computed conviction = mean(directional-voter confidence) × direction-agreement.

    Scoped to the models that actually emit a recognised directional verdict
    (A fundamentals, B regime) — the adversarial model C has no verdict and is
    excluded so its bear-case confidence doesn't pollute the score. Range 0..1.
    Sealed with conviction_source="proxy" — a proxy, not a human verdict, so the
    judgment card can overwrite it.
    """
    directional = [m for m in _models(round_1).values()
                   if verdict_direction(m.get("verdict")) is not None]
    if not directional:
        return 0.0
    confs = [confidence_score(m.get("confidence")) for m in directional]
    mean_conf = sum(confs) / len(confs)
    return round(mean_conf * direction_agreement(round_1), 3)


def directional_conflict(round_1: dict) -> Optional[bool]:
    """Do the directional voters (A, B) disagree on direction?

    True if the recognised directional verdicts span more than one direction,
    False if they all agree, None if fewer than two are recognised. This is the
    meaningful 2-voter signal in this architecture (C casts no directional vote),
    complementing `dissenting_model` which only fires with 3 recognised verdicts.
    """
    dirs = [verdict_direction(m.get("verdict")) for m in _models(round_1).values()]
    dirs = [d for d in dirs if d is not None]
    if len(dirs) < 2:
        return None
    return len(set(dirs)) > 1


def dissenting_model(round_1: dict) -> Optional[str]:
    """Which model ('a'/'b'/'c') dissents from the majority direction, if any.

    Returns the single role whose direction differs from a clear 2-vs-1 majority.
    None when unanimous, all-different, or no clear majority.
    """
    by_role = {r: verdict_direction(m.get("verdict")) for r, m in _models(round_1).items()}
    known = {r: d for r, d in by_role.items() if d is not None}
    if len(known) < 3:
        return None
    dirs = list(known.values())
    modal = max(set(dirs), key=dirs.count)
    minority = [r for r, d in known.items() if d != modal]
    return minority[0] if len(minority) == 1 else None


def unresolved_questions(disagreements: Optional[Iterable[dict]]) -> list[str]:
    """Judgment-type disagreements the corpus callosum did not resolve."""
    out = []
    for d in disagreements or []:
        if isinstance(d, dict) and d.get("type") == "judgment":
            q = d.get("question")
            if q:
                out.append(q)
    return out


_DIR_WORD = {1: "up", -1: "down", 0: "flat"}


def net_direction(round_1: dict) -> Optional[str]:
    """The directional lean the models agree on: 'up'/'down'/'flat', or None.

    None when the directional voters genuinely conflict (e.g. A overvalued vs B
    regime-upside) or none expressed a recognised verdict. This is the honest
    thesis direction to grade against — far better than a band midpoint that can
    sit on top of the reference price.
    """
    dirs = [verdict_direction(m.get("verdict")) for m in _models(round_1).values()]
    dirs = [d for d in dirs if d is not None]
    if not dirs:
        return None
    nonzero = {d for d in dirs if d != 0}
    if len(nonzero) > 1:
        return None  # real conflict — no net lean
    modal = max(set(dirs), key=dirs.count)
    return _DIR_WORD.get(modal)


def reasoning_fingerprint(round_1: dict, disagreements: Optional[Iterable[dict]]) -> dict:
    """Assemble the process-insight fingerprint from already-captured data."""
    models = _models(round_1)
    return {
        "dissenting_model": dissenting_model(round_1),
        "directional_conflict": directional_conflict(round_1),
        "directional_lean": net_direction(round_1),  # graded against by run_checkpoint
        "unresolved_questions": unresolved_questions(disagreements),
        "model_confidences": {r: m.get("confidence") for r, m in models.items()},
        # Self-consistency (P1): modal frequency of each model's mode-of-N verdict
        # (None when SELF_CONSISTENCY_N=1, i.e. a single un-aggregated sample), so
        # the grader can later down-weight low-consistency seals.
        "model_consistencies": {r: m.get("consistency") for r, m in models.items()},
        "conviction": conviction_proxy(round_1),
        "conviction_source": "proxy",
    }


def compute_cohort_key(
    prompt_versions: Optional[dict],
    judgment_file_hash: str,
    model_ids: Optional[dict] = None,
) -> str:
    """Stable short key for the judgment cohort.

    Combines three judgment signals; a change in any one yields a new key (a
    cohort break):
      - the Socratic prompt VERSION strings (operator-controlled granularity),
      - a content hash of the judgment FILES (analyst/target_engine/kill_eval),
      - the resolved MODEL ids per judgment prompt (so a model swap always resets
        the clock, even if no version string was bumped).
    """
    pv = prompt_versions or {}
    subset = {k: pv.get(k) for k in JUDGMENT_PROMPT_KEYS}
    payload = json.dumps(
        {"pv": subset, "files": judgment_file_hash, "models": model_ids or {}},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def resolve_model_ids(models_used: Optional[dict], frontmatter_ids: Optional[dict]) -> dict:
    """Prefer the models that ACTUALLY ran over the intended frontmatter.

    If the run reported `models_used` with at least one non-null value, use it
    (so a same-provider fallback is reflected in the cohort key + fingerprint);
    otherwise fall back to the intended frontmatter models.
    """
    mu = models_used or {}
    return mu if any(mu.values()) else (frontmatter_ids or {})


def judgment_model_ids(repo_root: Path) -> dict:
    """Resolved `model:` frontmatter of each judgment prompt -> for the cohort key.

    Reads the `model:` line from the first few lines of each judgment prompt's
    YAML frontmatter. Missing file / missing line -> None for that key. This is
    where the Socratic reasoner is actually pinned, so editing it (the act of
    swapping models) changes the cohort key automatically.
    """
    out: dict[str, Optional[str]] = {}
    for key, fname in JUDGMENT_PROMPT_FILES.items():
        p = Path(repo_root) / "scripts" / "prompts" / "socratic" / fname
        model = None
        try:
            for line in p.read_text(encoding="utf-8").splitlines()[:15]:
                s = line.strip()
                if s.startswith("model:"):
                    model = s.split(":", 1)[1].strip()
                    break
        except FileNotFoundError:
            model = None
        out[key] = model
    return out


def _to_date(d: Any) -> Optional[date]:
    """Normalise a date-ish value to a date; None if unparseable.

    Accepts date/datetime objects and ISO strings ('YYYY-MM-DD' or with a time
    suffix). Non-ISO formats (e.g. '6/8/2026') return None and are skipped rather
    than silently mis-compared lexicographically.
    """
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d)[:10])
    except (ValueError, TypeError):
        return None


def close_on_or_after(series: list[tuple[str, float]], target: date) -> Optional[tuple[float, str]]:
    """Date-pinned price pick (P0 grading fix).

    `series` is [(date, close), ...] (any order); dates may be ISO strings or
    date/datetime objects. Returns the close on the earliest trading day ON OR
    AFTER `target`, with the exact date used (ISO string) — never silently the
    first row in a window, and never a mis-parsed date. Rows whose date can't be
    parsed as ISO are skipped. Returns None if nothing valid on/after target.
    """
    target_d = _to_date(target)
    if target_d is None:
        return None
    candidates = []
    for d, c in series:
        dd = _to_date(d)
        if dd is not None and dd >= target_d:
            candidates.append((dd, float(c)))
    if not candidates:
        return None
    candidates.sort()
    dd, c = candidates[0]
    return float(c), dd.isoformat()


# ── IO helpers (isolated; covered by tests via tmp files) ──────────────────────

def file_content_hash(repo_root: Path, filenames: Iterable[str] = JUDGMENT_FILES) -> str:
    """Short content hash of the judgment files under repo_root/scripts.

    Missing files contribute a sentinel so their later appearance still changes
    the hash. Deterministic and order-independent.
    """
    h = hashlib.sha256()
    for name in sorted(filenames):
        p = Path(repo_root) / "scripts" / name
        try:
            h.update(name.encode("utf-8"))
            h.update(p.read_bytes())
        except FileNotFoundError:
            h.update(f"{name}::MISSING".encode("utf-8"))
    return h.hexdigest()[:16]


def git_system_version(repo_root: Path) -> str:
    """git short hash of HEAD, or 'unknown' if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=5,
        )
        v = out.stdout.strip()
        return v or "unknown"
    except Exception:
        return "unknown"


def build_seal_snapshot(
    *,
    ticker: str,
    run_id: str,
    ref_price: Optional[float],
    target_low: Optional[float],
    target_high: Optional[float],
    target_base: Optional[float],
    round_1: dict,
    disagreements: Optional[Iterable[dict]],
    prompt_versions: Optional[dict],
    socratic_analysis_id: Optional[int],
    system_version: str,
    cohort_key: str,
    prev_cohort_key: Optional[str],
) -> dict:
    """Assemble the prediction_log snapshot dict (pure; no IO)."""
    return {
        "ticker": ticker.upper(),
        "run_id": run_id,
        "current_price": ref_price,            # sealed ref_price = price the system saw
        "target_low": target_low,
        "target_high": target_high,
        "target_base": target_base,
        "system_version": system_version,
        "reasoning_fingerprint": reasoning_fingerprint(round_1, disagreements),
        "cohort_key": cohort_key,
        "version_cohort_break": (prev_cohort_key is not None and cohort_key != prev_cohort_key),
        "socratic_analysis_id": socratic_analysis_id,
    }


# ── DB entry point (best-effort; never raises into caller) ─────────────────────

# Sentinel: the previous-cohort query failed, so break-detection is UNKNOWN
# (distinct from "no prior seal exists", which is a legitimate None).
_QUERY_FAILED = object()


def _previous_cohort_key(sb, ticker: str):
    """Return the ticker's most recent cohort_key, None if there is no prior
    seal, or _QUERY_FAILED if the lookup errored (so we don't mistake a DB
    outage for a first-ever seal and suppress a real cohort break)."""
    try:
        resp = (
            sb.table("prediction_log")
            .select("cohort_key")
            .eq("ticker", ticker.upper())
            .not_.is_("cohort_key", "null")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0].get("cohort_key")
        return None
    except Exception:
        return _QUERY_FAILED


def seal_socratic_prediction(result: dict, *, repo_root: Optional[Path] = None) -> Optional[dict]:
    """Seal a completed Socratic run into prediction_log. Best-effort.

    `result` is the dict returned by run_socratic.run_socratic(). Returns the
    written row, or None on any failure (logged, never raised).
    """
    try:
        from prediction_logger import log_prediction
        from supabase_helper import get_client

        repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
        sb = get_client()

        ticker = result["ticker"]
        socratic_id = result.get("socratic_analyses_id")
        round_1 = result.get("round_1", {})
        cc = result.get("corpus_callosum", {}) or {}
        disagreements = cc.get("disagreements", [])
        target = result.get("rough_target_range", {}) or {}
        prompt_versions = result.get("prompt_versions") or {}

        system_version = git_system_version(repo_root)
        # Prefer the models that ACTUALLY ran (captured per call); fall back to the
        # intended frontmatter only if the run didn't report them. This keeps the
        # cohort key honest when the same-provider fallback fired.
        model_ids = resolve_model_ids(result.get("models_used"), judgment_model_ids(repo_root))
        cohort_key = compute_cohort_key(
            prompt_versions,
            file_content_hash(repo_root),
            model_ids,
        )
        prev = _previous_cohort_key(sb, ticker)
        prev_known = prev is not _QUERY_FAILED

        snapshot = build_seal_snapshot(
            ticker=ticker,
            run_id=f"soc-{socratic_id}" if socratic_id is not None else result.get("run_at", "soc-unknown"),
            ref_price=result.get("ref_price"),
            target_low=target.get("rough_target_low"),
            target_high=target.get("rough_target_high"),
            target_base=None,
            round_1=round_1,
            disagreements=disagreements,
            prompt_versions=prompt_versions,
            socratic_analysis_id=socratic_id,
            system_version=system_version,
            cohort_key=cohort_key,
            prev_cohort_key=(None if not prev_known else prev),
        )
        # If the prior-cohort lookup failed, break-detection is unknown, not False.
        if not prev_known:
            snapshot["version_cohort_break"] = None
        # Record the models that produced this verdict inside the fingerprint, so a
        # fallback is auditable in the sealed record itself.
        snapshot["reasoning_fingerprint"]["models_used"] = model_ids
        row = log_prediction(ticker, snapshot)
        if row:
            print(f"  [checkpoint_seal] sealed {ticker} "
                  f"(ver={system_version}, cohort={cohort_key[:8]}, "
                  f"break={snapshot['version_cohort_break']})", flush=True)
        return row or None
    except Exception as e:  # never break the pipeline
        import sys
        print(f"  [checkpoint_seal] WARN: seal skipped — {e}", file=sys.stderr, flush=True)
        return None
