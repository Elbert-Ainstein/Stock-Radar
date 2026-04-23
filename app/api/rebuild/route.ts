import { NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

const TICKER_RE = /^[A-Z]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");
const DATA_DIR = path.join(process.cwd(), "data");
const LOCK_FILE = path.join(DATA_DIR, ".rebuild-running");
const PROGRESS_FILE = path.join(DATA_DIR, ".rebuild-progress");

// Stale lock timeout: rebuild is fast (~2-3 min), 10 min is generous
const STALE_LOCK_MS = 10 * 60 * 1000;

function isLockStale(): boolean {
  try {
    if (!fs.existsSync(LOCK_FILE)) return false;
    const stat = fs.statSync(LOCK_FILE);
    return Date.now() - stat.mtimeMs > STALE_LOCK_MS;
  } catch {
    return false;
  }
}

function cleanStaleLock(): void {
  try {
    fs.unlinkSync(LOCK_FILE);
    if (fs.existsSync(PROGRESS_FILE)) fs.unlinkSync(PROGRESS_FILE);
  } catch {}
}

function readProgress(): {
  stage: string;
  message: string;
  current: number;
  total: number;
  percent: number;
} | null {
  try {
    if (fs.existsSync(PROGRESS_FILE)) {
      const raw = fs.readFileSync(PROGRESS_FILE, "utf-8");
      return JSON.parse(raw);
    }
  } catch {}
  return null;
}

export async function GET() {
  if (isLockStale()) {
    console.log("[Rebuild] Cleaning stale lock file (>10min old)");
    cleanStaleLock();
  }

  const isRunning = fs.existsSync(LOCK_FILE);
  const progress = isRunning ? readProgress() : null;

  return NextResponse.json({
    running: isRunning,
    progress: progress || null,
  });
}

export async function POST(req: Request) {
  if (isLockStale()) {
    console.log("[Rebuild] Cleaning stale lock before new run");
    cleanStaleLock();
  }

  const body = await req.json().catch(() => ({}));
  const ticker: string | null = body.ticker || null;

  if (ticker && !isValidTicker(ticker)) {
    return NextResponse.json(
      { success: false, message: "Invalid ticker format" },
      { status: 400 }
    );
  }

  // Check if full pipeline is already running — don't compete
  const pipelineLock = path.join(DATA_DIR, ".pipeline-running");
  if (fs.existsSync(pipelineLock)) {
    return NextResponse.json(
      {
        success: false,
        message: "Full pipeline is running — wait for it to finish before rebuilding.",
        running: false,
      },
      { status: 409 }
    );
  }

  // Atomic lock
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(LOCK_FILE, new Date().toISOString(), { flag: "wx" });
  } catch {
    const progress = readProgress();
    return NextResponse.json(
      {
        success: false,
        message: "Rebuild already running",
        running: true,
        progress: progress || null,
      },
      { status: 409 }
    );
  }

  const scriptPath = path.join(SCRIPTS_DIR, "rebuild_analysis.py");
  const args = [scriptPath];
  if (ticker) {
    args.push("--ticker", ticker);
  }

  execFile("python", args, { cwd: process.cwd(), timeout: 300000 }, (error, stdout, stderr) => {
    if (error) console.error("[Rebuild] Error:", error.message);
    if (stdout) console.log("[Rebuild] stdout:", stdout.slice(-500));
    if (stderr) console.error("[Rebuild] stderr:", stderr.slice(-500));
    try {
      fs.unlinkSync(LOCK_FILE);
    } catch {}
  });

  return NextResponse.json({
    success: true,
    message: ticker
      ? `Rebuild started for ${ticker}`
      : "Full watchlist rebuild started",
  });
}
