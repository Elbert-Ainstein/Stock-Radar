#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Stock Radar — native scheduler entrypoint (embedded in the program, NOT the
# Claude app). Runs ONE maintenance job and logs it, so jobs run on the host
# regardless of any app being open. Install via crontab (see crontab.txt).
#
# Usage:  stockradar_cron.sh <grader|panel|prices>
#
# Python: defaults to `python3`. If you use conda/venv, export STOCKRADAR_PYTHON,
#   e.g.  export STOCKRADAR_PYTHON="$HOME/miniconda3/bin/python"
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

JOB="${1:-}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO/scripts"
LOGDIR="$REPO/data/cron"
PY="${STOCKRADAR_PYTHON:-python3}"
mkdir -p "$LOGDIR"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

case "$JOB" in
  grader) DESC="checkpoint grader (grade ripe T+30/60/90 seals)"; SCRIPT="run_checkpoint.py" ;;
  panel)  DESC="analyst panel refresh (cross-node [CHAIN] context)"; SCRIPT="analyst_panel.py" ;;
  prices) DESC="live price refresh"; SCRIPT="refresh_prices.py" ;;
  *) echo "usage: $0 <grader|panel|prices>" >&2; exit 2 ;;
esac

LOG="$LOGDIR/$JOB.log"
cd "$SCRIPTS" || { echo "[$(ts)] FAIL $JOB: cannot cd $SCRIPTS" >> "$LOG"; exit 1; }

# Self-update (2026-07-02): the cron host must never run stale code — "pull on
# the cron machine" was a recurring manual chore after every merge. --ff-only
# is safe: it refuses (and we log + continue on the CURRENT code) if the local
# checkout has diverged or has uncommitted work. Opt out: STOCKRADAR_NO_PULL=1.
if [ -z "${STOCKRADAR_NO_PULL:-}" ]; then
  if PULL_OUT=$(git -C "$REPO" pull --ff-only 2>&1); then
    case "$PULL_OUT" in
      *"Already up to date"*) : ;;
      *) echo "[$(ts)] SELF-UPDATE $JOB: $PULL_OUT" >> "$LOG" ;;
    esac
  else
    echo "[$(ts)] SELF-UPDATE SKIPPED $JOB (running current code): $PULL_OUT" >> "$LOG"
  fi
fi

echo "[$(ts)] START $JOB — $DESC" >> "$LOG"
if "$PY" "$SCRIPT" >> "$LOG" 2>&1; then
  echo "[$(ts)] OK $JOB" >> "$LOG"
else
  rc=$?
  echo "[$(ts)] FAIL $JOB (exit $rc)" >> "$LOG"
  exit "$rc"
fi
