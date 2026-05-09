import { NextRequest, NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

const TICKER_RE = /^[A-Z0-9]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");
const DATA_DIR = path.join(process.cwd(), "data");

// Per-ticker lock file pattern — multiple tickers can re-run in parallel,
// but the same ticker can only have one in-flight thesis run.
function lockPath(ticker: string): string {
  return path.join(DATA_DIR, `.thesis-running-${ticker.replace(/\./g, "_")}`);
}

function statusPath(ticker: string): string {
  return path.join(DATA_DIR, `.thesis-status-${ticker.replace(/\./g, "_")}.json`);
}

interface ThesisStatus {
  ticker: string;
  completed_at: string;
  exit_code: number | null;
  ok: boolean;
  error: string | null;
}

// Stale lock timeout: thesis run is ~60-120s. Server subprocess timeout below
// is 7min; this stale window must exceed that so a still-running subprocess
// is not declared "stale" while alive. Client poll TIMEOUT_MS is 8min.
const STALE_LOCK_MS = 9 * 60 * 1000;

function isLockStale(lf: string): boolean {
  try {
    if (!fs.existsSync(lf)) return false;
    const stat = fs.statSync(lf);
    return Date.now() - stat.mtimeMs > STALE_LOCK_MS;
  } catch {
    return false;
  }
}

const VALID_TRIGGER_REASONS = new Set([
  "manual",
  "earnings",
  "guidance_change",
  "contract",
  "kill_state_change",
  "scheduled",
]);

/**
 * POST /api/thesis/[ticker]/rerun
 *
 * Triggers `python scripts/run_thesis.py <TICKER> --trigger-reason <REASON>`
 * via subprocess (same pattern as /api/rebuild). Per-ticker lockfile prevents
 * duplicate concurrent runs on the same ticker.
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!ticker || !isValidTicker(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }

  let triggerReason = "manual";
  let overrideSuspectRecent = false;
  try {
    const body = await req.json();
    if (body && typeof body === "object") {
      if (body.trigger_reason) {
        const r = String(body.trigger_reason);
        if (VALID_TRIGGER_REASONS.has(r)) {
          triggerReason = r;
        }
      }
      // Operator-acknowledged override of the Module 1 sanity check.
      // Use ONLY when the operator has cross-checked against the 10-Q.
      // For genuine provider anomalies (e.g. MU's $23.86B Q1 FY26 vs real $8.7B),
      // this produces a thesis built on bad numbers — DO NOT USE.
      if (body.override_suspect_recent === true) {
        overrideSuspectRecent = true;
      }
    }
  } catch {
    // No body or bad JSON — keep defaults
  }

  const lf = lockPath(ticker);

  if (isLockStale(lf)) {
    console.log(`[thesis rerun] ${ticker}: cleaning stale lock`);
    try {
      fs.unlinkSync(lf);
    } catch {}
  }

  // Atomic lock acquisition
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(lf, new Date().toISOString(), { flag: "wx" });
  } catch {
    return NextResponse.json(
      {
        success: false,
        message: `Thesis run for ${ticker} already in flight`,
        running: true,
      },
      { status: 409 }
    );
  }

  const scriptPath = path.join(SCRIPTS_DIR, "run_thesis.py");
  const args = [scriptPath, ticker, "--trigger-reason", triggerReason];
  if (overrideSuspectRecent) {
    args.push("--override-suspect-recent");
  }

  // Fire-and-forget — caller polls GET to see when row appears.
  // Timeout 7min: aligned with client poll TIMEOUT_MS (8min) - one POLL_MS (7s)
  // so the server kills before the client gives up. STALE_LOCK_MS (9min) sits
  // above this so a live subprocess is never seen as stale.
  execFile(
    "python",
    args,
    { cwd: process.cwd(), timeout: 7 * 60 * 1000 },
    (error, stdout, stderr) => {
      if (error) console.error(`[thesis rerun ${ticker}] error:`, error.message);
      if (stdout) console.log(`[thesis rerun ${ticker}] stdout (last 500):`, stdout.slice(-500));
      if (stderr) console.error(`[thesis rerun ${ticker}] stderr (last 500):`, stderr.slice(-500));

      // PATCH V: write the status BEFORE removing the lockfile so the client's
      // poll never sees `running: false` without a corresponding status file.
      const errStr = error
        ? error.message + (stderr ? "\n" + stderr.slice(-300) : "")
        : null;
      const errCode = error
        ? (typeof (error as NodeJS.ErrnoException).code === "number"
            ? ((error as NodeJS.ErrnoException).code as unknown as number)
            : 1)
        : 0;
      const status: ThesisStatus = {
        ticker,
        completed_at: new Date().toISOString(),
        exit_code: errCode,
        ok: !error,
        error: errStr,
      };
      try {
        fs.writeFileSync(statusPath(ticker), JSON.stringify(status), "utf-8");
      } catch (e) {
        const m = e instanceof Error ? e.message : String(e);
        console.error(`[thesis rerun ${ticker}] failed to write status: ${m}`);
      }
      try {
        fs.unlinkSync(lf);
      } catch {}
    }
  );

  return NextResponse.json({
    success: true,
    message: `Thesis run started for ${ticker}${overrideSuspectRecent ? " (sanity-check override)" : ""}`,
    ticker,
    trigger_reason: triggerReason,
    override_suspect_recent: overrideSuspectRecent,
    poll_url: `/api/thesis/${ticker}`,
  });
}

/**
 * GET on the rerun endpoint returns the lock state (running or not).
 * Useful for the dashboard to disable the "Re-run thesis" button.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!ticker || !isValidTicker(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }
  const lf = lockPath(ticker);
  const running = fs.existsSync(lf) && !isLockStale(lf);

  // PATCH V: also include last-completed status so the client can distinguish
  // clean finish from silent subprocess failure.
  let lastStatus: ThesisStatus | null = null;
  if (!running) {
    try {
      const sp = statusPath(ticker);
      if (fs.existsSync(sp)) {
        lastStatus = JSON.parse(fs.readFileSync(sp, "utf-8"));
      }
    } catch (e) {
      console.warn(`[thesis rerun ${ticker}] failed to read status: ${e}`);
    }
  }

  return NextResponse.json({ ticker, running, last_status: lastStatus });
}
