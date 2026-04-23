/**
 * /api/scout/moat/[ticker]
 *
 * Runs the moat scout (scripts/scout_moat.py) for a single ticker, then
 * reads back the freshly written signal from Supabase and returns the
 * structured moat events as JSON. Lets you test moat detection on demand
 * without waiting for the nightly pipeline.
 *
 * GET /api/scout/moat/AMD               → default 180-day window
 * GET /api/scout/moat/LITE?days=90      → 90-day window
 */
import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { execFile } from "child_process";
import { promisify } from "util";
import path from "path";

export const dynamic = "force-dynamic";

const execFileP = promisify(execFile);

const SCRIPT = path.join(process.cwd(), "scripts", "scout_moat.py");

const TICKER_RE = /^[A-Z]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

export async function GET(
  req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const tkr = ticker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!tkr || !isValidTicker(tkr)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }

  const url = new URL(req.url);
  let days = 180;
  const daysRaw = url.searchParams.get("days");
  if (daysRaw) {
    const n = Number(daysRaw);
    if (Number.isFinite(n) && n >= 7 && n <= 540) days = Math.floor(n);
  }

  // 1. Shell out to the scout. 180s budget accommodates Perplexity + Claude
  //    enrichment calls on a ticker with many moat events.
  const started = Date.now();
  let stdoutTail = "";
  let scriptError: string | null = null;

  try {
    const { stdout, stderr } = await execFileP(
      "python",
      [SCRIPT, "--ticker", tkr, "--days", String(days)],
      {
        cwd: process.cwd(),
        timeout: 180_000,
        maxBuffer: 5 * 1024 * 1024,
      }
    );
    stdoutTail = (stdout || "").split("\n").slice(-40).join("\n");
    if (stderr && !stdout.includes("MOAT SUMMARY")) {
      scriptError = stderr.split("\n").slice(-20).join("\n");
    }
  } catch (e: any) {
    scriptError = (e?.stderr || e?.message || String(e))
      .toString()
      .split("\n")
      .slice(-20)
      .join("\n");
  }

  const elapsedMs = Date.now() - started;

  // 2. Read back latest moat signal from Supabase.
  const { data: signals, error: readErr } = await supabase
    .from("signals")
    .select("*")
    .eq("ticker", tkr)
    .eq("scout", "moat")
    .order("created_at", { ascending: false })
    .limit(1);

  if (readErr) {
    return NextResponse.json(
      {
        ticker: tkr,
        ok: false,
        error: `DB read failed: ${readErr.message}`,
        scriptError,
        stdoutTail,
        elapsedMs,
      },
      { status: 500 }
    );
  }

  const signal = signals?.[0] ?? null;

  return NextResponse.json({
    ticker: tkr,
    ok: !!signal,
    windowDays: days,
    elapsedMs,
    signal: signal
      ? {
          scout: signal.scout,
          ai: signal.ai,
          overallSignal: signal.signal,
          summary: signal.summary,
          createdAt: signal.created_at,
          events: signal.data?.moat_events ?? signal.data?.events ?? [],
          strengthScore: signal.data?.strength_score ?? 0,
          pplxCount: signal.data?.pplx_count ?? 0,
          citations: signal.data?.citations ?? [],
        }
      : null,
    scriptError,
    stdoutTail,
  });
}
