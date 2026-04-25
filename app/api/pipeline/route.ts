import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { execFile, execSync } from "child_process";
import path from "path";
import fs from "fs";

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");
const DATA_DIR = path.join(process.cwd(), "data");
const LOCK_FILE = path.join(DATA_DIR, ".pipeline-running");
const PROGRESS_FILE = path.join(DATA_DIR, ".pipeline-progress");
const QUEUED_FILE = path.join(DATA_DIR, ".pipeline-queued");

// Stale lock timeout: with 50 stocks, the full pipeline can take 2+ hours
const STALE_LOCK_MS = 150 * 60 * 1000; // 2.5 hours

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
    // Also clean progress file
    if (fs.existsSync(PROGRESS_FILE)) fs.unlinkSync(PROGRESS_FILE);
  } catch {}
}

function readProgress(): { stage: string; message: string; current: number; total: number; percent: number } | null {
  try {
    if (fs.existsSync(PROGRESS_FILE)) {
      const raw = fs.readFileSync(PROGRESS_FILE, "utf-8");
      return JSON.parse(raw);
    }
  } catch {}
  return null;
}

export async function GET() {
  // Auto-clean stale locks
  if (isLockStale()) {
    console.log("[Pipeline] Cleaning stale lock file (>15min old)");
    cleanStaleLock();
  }

  const isRunning = fs.existsSync(LOCK_FILE);
  const progress = isRunning ? readProgress() : null;

  // Get latest run from Supabase
  const { data: run } = await supabase
    .from("pipeline_runs")
    .select("run_id, started_at, completed_at, success")
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  return NextResponse.json({
    running: isRunning,
    progress: progress || null,
    lastRun: run?.completed_at || run?.started_at || "",
    lastRunSuccess: run?.success ?? null,
  });
}

export async function POST(req: Request) {
  // Auto-clean stale locks
  if (isLockStale()) {
    console.log("[Pipeline] Cleaning stale lock before new run");
    cleanStaleLock();
  }

  const body = await req.json().catch(() => ({}));
  const freeOnly = body.freeOnly ?? false;

  // Atomic lock acquisition — prevents TOCTOU race on rapid double-clicks
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(LOCK_FILE, new Date().toISOString(), { flag: "wx" });
  } catch {
    // Lock already exists — pipeline is running
    const progress = readProgress();
    return NextResponse.json({
      success: false,
      message: "Pipeline already running",
      running: true,
      progress: progress || null,
    }, { status: 409 });
  }

  const scriptPath = path.join(SCRIPTS_DIR, "run_pipeline.py");
  const args = [scriptPath];
  if (freeOnly) {
    args.push("--free");
  }

  // 2 hours — 50 stocks × ~2 min each for model generation alone
  execFile("python", args, { cwd: process.cwd(), timeout: 7200000, maxBuffer: 10_000_000 }, (error, stdout, stderr) => {
    if (error) {
      const isTimeout = error.message?.includes("TIMEOUT") || error.killed;
      console.error("[Pipeline] Error:", isTimeout ? "Process timed out after 2 hours" : error.message);
    }
    if (stdout) console.log("[Pipeline] stdout:", stdout.slice(-2000));
    if (stderr) console.error("[Pipeline] stderr:", stderr.slice(-2000));
    try { fs.unlinkSync(LOCK_FILE); } catch {}
    // Progress file is cleaned by the Python script itself
  });

  return NextResponse.json({ success: true, message: "Pipeline started" });
}

export async function DELETE() {
  // Force-stop any running pipeline process and clean up lock files.
  // Kills all Python processes matching run_pipeline.py, scout_*, analyst, generate_model.
  const killed: string[] = [];

  const patterns = [
    "run_pipeline.py",
    "scout_quant",
    "scout_news",
    "scout_catalyst",
    "scout_moat",
    "scout_fundamentals",
    "scout_insider",
    "scout_social",
    "scout_youtube",
    "scout_filings",
    "analyst.py",
    "generate_model.py",
  ];

  for (const pat of patterns) {
    try {
      execSync(`pkill -f "${pat}"`, { timeout: 5000 });
      killed.push(pat);
    } catch {
      // pkill returns non-zero if no matching process — not an error
    }
  }

  // Clean up lock and progress files
  try { fs.unlinkSync(LOCK_FILE); } catch {}
  try { fs.unlinkSync(PROGRESS_FILE); } catch {}

  // Clean up any cancel files
  try {
    const files = fs.readdirSync(DATA_DIR);
    for (const f of files) {
      if (f.startsWith(".pipeline-cancel-")) {
        try { fs.unlinkSync(path.join(DATA_DIR, f)); } catch {}
      }
    }
  } catch {}

  return NextResponse.json({
    success: true,
    message: `Pipeline stopped. Killed: ${killed.length > 0 ? killed.join(", ") : "no active processes found"}.`,
    killed,
  });
}
