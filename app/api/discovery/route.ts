import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");
const DATA_DIR = path.join(process.cwd(), "data");
const LOCK_FILE = path.join(DATA_DIR, ".discovery-running");
const PROGRESS_FILE = path.join(DATA_DIR, ".discovery-progress");
const JSON_FALLBACK = path.join(DATA_DIR, "discovery_latest.json");

const STALE_LOCK_MS = 45 * 60 * 1000; // 45 min (3-stage scan can be longer)

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

function readProgress() {
  try {
    if (fs.existsSync(PROGRESS_FILE)) {
      return JSON.parse(fs.readFileSync(PROGRESS_FILE, "utf-8"));
    }
  } catch {}
  return null;
}

// GET /api/discovery — returns latest discovery candidates
export async function GET() {
  if (isLockStale()) cleanStaleLock();

  const isRunning = fs.existsSync(LOCK_FILE);
  const progress = isRunning ? readProgress() : null;

  let candidates: any[] = [];
  let lastRunAt = "";

  try {
    // Get latest run_id
    const { data: latestRow } = await supabase
      .from("discovery_candidates")
      .select("run_id, scanned_at")
      .order("scanned_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (latestRow) {
      lastRunAt = latestRow.scanned_at;
      const { data: rows } = await supabase
        .from("discovery_candidates")
        .select("*")
        .eq("run_id", latestRow.run_id)
        .order("quant_score", { ascending: false });

      candidates = rows || [];
    }
  } catch (e) {
    console.log("[Discovery] Supabase query failed, trying JSON fallback");
  }

  // JSON fallback
  if (candidates.length === 0) {
    try {
      if (fs.existsSync(JSON_FALLBACK)) {
        const raw = JSON.parse(fs.readFileSync(JSON_FALLBACK, "utf-8"));
        lastRunAt = raw.scanned_at || "";
        candidates = (raw.candidates || []).map((c: any, i: number) => ({
          ticker: c.ticker,
          name: c.data?.name || "",
          sector: c.data?.sector || "",
          industry: c.data?.industry || "",
          price: c.data?.price || 0,
          change_pct: c.data?.change_pct || 0,
          market_cap_b: c.data?.market_cap_b || 0,
          revenue_growth_pct: c.data?.revenue_growth_pct || 0,
          earnings_growth_pct: c.data?.earnings_growth_pct || 0,
          gross_margin_pct: c.data?.gross_margin_pct || 0,
          operating_margin_pct: c.data?.operating_margin_pct || 0,
          forward_pe: c.data?.forward_pe || null,
          ps_ratio: c.data?.ps_ratio || null,
          peg_ratio: c.data?.peg_ratio || null,
          distance_from_high_pct: c.data?.distance_from_high_pct || 0,
          short_pct: c.data?.short_pct || 0,
          quant_score: c.scores?.composite || 0,
          scores: c.scores || {},
          signal: c.signal || "neutral",
          summary: c.summary || "",
          stage: c._stage || "candidate",
          rank: c._rank || i + 1,
          // AI fields
          ai_confidence: c.ai_confidence || null,
          thesis: c.thesis || null,
          kill_condition: c.kill_condition || null,
          catalysts: c.catalysts || [],
          target_range: c.target_range || {},
          tags: c.tags || [],
          // HQ location for globe
          hq_city: c.data?.hq_city || "",
          hq_state: c.data?.hq_state || "",
          hq_country: c.data?.hq_country || "",
        }));
      }
    } catch {}
  }

  const shortlist = candidates.filter((c: any) => c.stage === "shortlist" || c.stage === "validated");
  const validated = candidates.filter((c: any) => c.stage === "validated");

  return NextResponse.json({
    running: isRunning,
    progress,
    lastRunAt,
    totalCandidates: candidates.length,
    shortlistCount: shortlist.length,
    validatedCount: validated.length,
    candidates,
  });
}

// POST /api/discovery — trigger a discovery scan
export async function POST(req: Request) {
  if (isLockStale()) cleanStaleLock();

  const body = await req.json().catch(() => ({}));
  const quick = body.quick ?? false;
  const aiTopN = body.aiTopN ?? 10;

  // Atomic lock
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(LOCK_FILE, new Date().toISOString(), { flag: "wx" });
  } catch {
    return NextResponse.json({
      success: false,
      message: "Discovery scan already running",
      running: true,
      progress: readProgress(),
    }, { status: 409 });
  }

  // Validate aiTopN is a safe integer
  const safeAiTopN = Number.isInteger(Number(aiTopN)) && Number(aiTopN) > 0 ? String(Math.floor(Number(aiTopN))) : "10";

  const scriptPath = path.join(SCRIPTS_DIR, "scout_discovery.py");
  const args = [scriptPath];
  if (quick) {
    args.push("--quick");
  } else {
    args.push("--ai-top", safeAiTopN);
  }

  execFile("python", args, { cwd: process.cwd(), timeout: 2700000 }, (error, stdout, stderr) => {
    if (error) console.error("[Discovery] Error:", error.message);
    if (stdout) console.log("[Discovery] stdout:", stdout.slice(-2000));
    if (stderr) console.error("[Discovery] stderr:", stderr.slice(-500));
    try { fs.unlinkSync(LOCK_FILE); } catch {}
  });

  return NextResponse.json({
    success: true,
    message: quick ? "Quick scan started (Stages 1+2, no AI)" : `Full scan started (AI top ${aiTopN})`,
  });
}

// PUT /api/discovery — add a discovered candidate to watchlist
export async function PUT(req: Request) {
  try {
    const body = await req.json();
    const { ticker } = body;

    if (!ticker) {
      return NextResponse.json({ error: "ticker required" }, { status: 400 });
    }

    // Load candidate data from discovery_candidates
    const { data: candidate } = await supabase
      .from("discovery_candidates")
      .select("*")
      .eq("ticker", ticker)
      .order("scanned_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (!candidate) {
      return NextResponse.json({ error: "Candidate not found" }, { status: 404 });
    }

    // Check if already on watchlist
    const { data: existing } = await supabase
      .from("stocks")
      .select("ticker")
      .eq("ticker", ticker)
      .maybeSingle();

    if (existing) {
      // Reactivate if soft-deleted
      await supabase
        .from("stocks")
        .update({ active: true })
        .eq("ticker", ticker);
      return NextResponse.json({ success: true, message: `${ticker} reactivated on watchlist` });
    }

    // Build stock row from candidate data
    const stock: Record<string, any> = {
      ticker: candidate.ticker,
      name: candidate.name || ticker,
      sector: candidate.sector || "",
      thesis: candidate.thesis || "",
      kill_condition: candidate.kill_condition || "",
      tags: candidate.tags || [],
      active: true,
    };

    // If AI validation produced a target range, set target_price to base case
    if (candidate.target_range?.base) {
      stock.target_price = candidate.target_range.base;
      stock.scenarios = {
        bull: { price: candidate.target_range.high || 0, probability: 0.25 },
        base: { price: candidate.target_range.base || 0, probability: 0.50 },
        bear: { price: candidate.target_range.low || 0, probability: 0.25 },
      };
    }

    const { error } = await supabase
      .from("stocks")
      .upsert(stock, { onConflict: "ticker" });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    // Mark candidate as "promoted" in discovery table
    await supabase
      .from("discovery_candidates")
      .update({ stage: "promoted" })
      .eq("ticker", ticker)
      .eq("run_id", candidate.run_id);

    return NextResponse.json({
      success: true,
      message: `${ticker} added to watchlist`,
      stock,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
