import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");
const DATA_DIR = path.join(process.cwd(), "data");
const LOCK_FILE = path.join(DATA_DIR, ".pipeline-running");
const PROGRESS_FILE = path.join(DATA_DIR, ".pipeline-progress");
const QUEUED_FILE = path.join(DATA_DIR, ".pipeline-queued");

// Stale lock timeout: if lock file is older than 15 minutes, consider it stale
const STALE_LOCK_MS = 15 * 60 * 1000;

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

  execFile("python", args, { cwd: process.cwd(), timeout: 600000 }, (error, stdout, stderr) => {
    if (error) console.error("[Pipeline] Error:", error.message);
    if (stdout) console.log("[Pipeline] stdout:", stdout.slice(-500));
    if (stderr) console.error("[Pipeline] stderr:", stderr.slice(-500));
    try { fs.unlinkSync(LOCK_FILE); } catch {}
    // Progress file is cleaned by the Python script itself
  });

  return NextResponse.json({ success: true, message: "Pipeline started" });
}
