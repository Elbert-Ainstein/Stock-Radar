import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

const TICKER_RE = /^[A-Z]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");
const DATA_DIR = path.join(process.cwd(), "data");
const LOCK_FILE = path.join(DATA_DIR, ".pipeline-running");
const QUEUED_FILE = path.join(DATA_DIR, ".pipeline-queued");

/**
 * Try to atomically create a lock file. Returns true if we acquired the lock,
 * false if it already exists. Uses wx flag (exclusive create) to prevent TOCTOU race.
 */
function tryAcquireLock(): boolean {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(LOCK_FILE, new Date().toISOString(), { flag: "wx" });
    return true;
  } catch {
    // EEXIST = lock already held; any other error = treat as locked
    return false;
  }
}

/**
 * Safely append a ticker to the queue file with read-then-write atomicity.
 * Uses a temp file + rename to prevent partial writes from concurrent access.
 */
function safeQueueTicker(ticker: string): void {
  let queued: string[] = [];
  try {
    if (fs.existsSync(QUEUED_FILE)) {
      queued = JSON.parse(fs.readFileSync(QUEUED_FILE, "utf-8"));
    }
  } catch {}
  if (!queued.includes(ticker)) {
    queued.push(ticker);
    const tmpFile = QUEUED_FILE + ".tmp";
    fs.writeFileSync(tmpFile, JSON.stringify(queued), "utf-8");
    fs.renameSync(tmpFile, QUEUED_FILE);
  }
}

export async function POST(request: Request) {
  try {
    const { ticker, name, sector } = await request.json();

    if (!ticker || !name) {
      return NextResponse.json({ error: "ticker and name required" }, { status: 400 });
    }

    if (!isValidTicker(ticker)) {
      return NextResponse.json({ error: "Invalid ticker format" }, { status: 400 });
    }

    // Check if already exists
    const { data: existing } = await supabase
      .from("stocks")
      .select("ticker")
      .eq("ticker", ticker)
      .eq("active", true)
      .maybeSingle();

    if (existing) {
      return NextResponse.json({ error: "Stock already in watchlist" }, { status: 409 });
    }

    // Insert new stock with placeholder structure
    const { error: insertErr } = await supabase.from("stocks").upsert({
      ticker,
      name,
      sector: sector || "Unknown",
      thesis: "Added to watchlist — pipeline will generate thesis and analysis.",
      kill_condition: "TBD — will be generated after pipeline analysis",
      tags: [sector || "Unknown"],
      target_price: null,
      timeline_years: 3,
      valuation_method: "pe",
      target_multiple: 20,
      target_notes: "Placeholder — run pipeline to generate model defaults",
      model_defaults: {
        revenue_b: 1.0,
        op_margin: 0.20,
        tax_rate: 0.21,
        shares_m: 200,
        pe_multiple: 20,
      },
      scenarios: {
        bull: { probability: 0.25, price: 0, trigger: "TBD" },
        base: { probability: 0.50, price: 0, trigger: "TBD" },
        bear: { probability: 0.25, price: 0, trigger: "TBD" },
      },
      criteria: [],
      active: true,
    }, { onConflict: "ticker" });

    if (insertErr) {
      return NextResponse.json({ error: insertErr.message }, { status: 500 });
    }

    // Try to atomically acquire lock for mini-pipeline
    // If lock already exists (pipeline or another add is running), queue instead
    const gotLock = tryAcquireLock();

    if (!gotLock) {
      // Pipeline or another mini-pipeline is running — queue this ticker
      safeQueueTicker(ticker);
      return NextResponse.json({
        success: true,
        ticker,
        pipelineStatus: "queued",
        message: `${ticker} added. Pipeline is running — ${ticker} will be analyzed when it finishes.`,
      });
    }

    // We acquired the lock — run mini-pipeline for this stock
    try {
      const scriptPath = path.join(SCRIPTS_DIR, "run_pipeline.py");

      execFile("python", [scriptPath, "--ticker", ticker], { cwd: process.cwd(), timeout: 120000 }, (error) => {
        if (error) console.error(`Mini-pipeline error for ${ticker}:`, error.message);
        else console.log(`Mini-pipeline completed for ${ticker}`);
        try { fs.unlinkSync(LOCK_FILE); } catch {}
      });

      return NextResponse.json({
        success: true,
        ticker,
        pipelineStatus: "running",
        message: `${ticker} added. Running quant scout + analyst + model generation...`,
      });
    } catch {
      // Release lock if we couldn't start the process
      try { fs.unlinkSync(LOCK_FILE); } catch {}
      return NextResponse.json({
        success: true,
        ticker,
        pipelineStatus: "failed",
        message: `${ticker} added but pipeline could not start.`,
      });
    }
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
