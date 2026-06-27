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
echo "[$(ts)] START $JOB — $DESC" >> "$LOG"
if "$PY" "$SCRIPT" >> "$LOG" 2>&1; then
  echo "[$(ts)] OK $JOB" >> "$LOG"
else
  rc=$?
  echo "[$(ts)] FAIL $JOB (exit $rc)" >> "$LOG"
  exit "$rc"
fi
