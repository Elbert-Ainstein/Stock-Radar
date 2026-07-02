# Native scheduling (host cron)

Scheduling lives **in the program**, on the host — not in the Claude app. The
Claude-app scheduler only fires while that app is open; a research system that has
to grade seals and refresh the panel every day needs to run independently. These
jobs are deterministic scripts the system already has; cron just invokes them.

## Jobs

| Job | Script | Cadence | What it does |
|---|---|---|---|
| `grader` | `run_checkpoint.py` | daily 07:00 | Grades sealed predictions ripened to T+30/60/90 (idempotent; catches up). |
| `panel` | `analyst_panel.py` | Mon/Wed/Fri 06:30 | Refreshes the cross-node `[CHAIN]` context the Socratic layer loads. Low cadence = thinking time. |
| `prices` | `refresh_prices.py` | (optional) weekday hourly | Live price refresh for the dashboard/DB. Off by default. |

Each run appends to `data/cron/<job>.log` with UTC `START / OK / FAIL` markers.

## Install

```bash
# one-time: make the runner executable
chmod +x scripts/cron/stockradar_cron.sh

# if you use conda/venv, point the runner at that interpreter:
export STOCKRADAR_PYTHON="$HOME/miniconda3/bin/python"

# install the schedule (merge with any existing crontab):
crontab -l 2>/dev/null > /tmp/cur_cron || true
cat scripts/cron/crontab.txt >> /tmp/cur_cron
crontab /tmp/cur_cron

# verify
crontab -l
```

Run a job by hand to test it:
```bash
scripts/cron/stockradar_cron.sh grader   # then check data/cron/grader.log
```

## Supersedes the Claude-app tasks

This replaces the app-scheduled **daily checkpoint grader**. Once cron is installed,
delete that task from the Claude app's *Scheduled* panel to avoid double-running.

The one-time **AXON T+30 review** is a *reasoning* task (a judgment post-mortem),
not a deterministic script — it's reasonable to keep that one in the Claude app, or
later convert it to a script that calls the model. Recurring deterministic
maintenance (grading, panel refresh) belongs here.

## Notes
- macOS may require granting `cron` Full Disk Access (System Settings → Privacy)
  to read the repo, depending on its location.
- The runner `cd`s into `scripts/` and loads `.env` via the program's own
  `utils.load_env()`, so secrets stay in `.env` (never in the crontab).
