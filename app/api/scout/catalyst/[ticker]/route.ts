/**
 * /api/scout/catalyst/[ticker]
 *
 * Runs the catalyst scout (scripts/scout_catalyst.py) for a single ticker,
 * then reads back the freshly written signal from Supabase and returns the
 * structured catalyst events as JSON. Lets you test contract/order detection
 * on demand without waiting for the nightly pipeline.
 *
 * GET /api/scout/catalyst/LITE              → default 90-day window
 * GET /api/scout/catalyst/LITE?days=180     → 180-day window
 */
import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { execFile } from "child_process";
import { promisify } from "util";
import path from "path";

export const dynamic = "force-dynamic";

const execFileP = promisify(execFile);

const SCRIPT = path.join(process.cwd(), "scripts", "scout_catalyst.py");

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
  let days = 90;
  const daysRaw = url.searchParams.get("days");
  if (daysRaw) {
    const n = Number(daysRaw);
    if (Number.isFinite(n) && n >= 7 && n <= 365) days = Math.floor(n);
  }

  // 1. Shell out to the scout. Use a generous timeout — Perplexity + Claude
  //    calls can easily take 30s combined on a ticker with many 8-Ks.
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
    if (stderr && !stdout.includes("CATALYST SUMMARY")) {
      // Surface stderr only when the run clearly didn't complete.
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

  // 2. Read back the latest catalyst signal for this ticker from Supabase.
  //    The scout writes signals via utils.save_signals → supabase_helper.
  const { data: signals, error: readErr } = await supabase
    .from("signals")
    .select("*")
    .eq("ticker", tkr)
    .eq("scout", "catalyst")
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
          events: signal.data?.catalyst_events ?? [],
          edgarCount: signal.data?.edgar_count ?? 0,
          pplxCount: signal.data?.pplx_count ?? 0,
          citations: signal.data?.citations ?? [],
        }
      : null,
    scriptError,
    stdoutTail,
  });
}
