import { NextRequest, NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";
import { promisify } from "util";

const execFileP = promisify(execFile);
const SCRIPTS_DIR = path.join(process.cwd(), "scripts");

const TICKER_RE = /^[A-Z]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

/**
 * GET /api/model/[ticker]?rev_growth_y1=0.25&ev_ebitda_multiple=22
 *
 * Returns the full JSON payload produced by target_api.py — the brief view
 * (sliders), deduction chain, forecast tables, and capitalization.
 *
 * Query-string keys are passed through as driver overrides. Only numeric
 * values are forwarded; everything else is ignored.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!ticker || !isValidTicker(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }

  // Collect driver overrides + horizon from the query string
  const url = new URL(req.url);
  const overrideArgs: string[] = [];

  // Horizon: only 12, 24, 36 are allowed
  const horizonRaw = url.searchParams.get("horizon");
  let horizonMonths = 12;
  if (horizonRaw) {
    const n = Number(horizonRaw);
    if ([12, 24, 36].includes(n)) horizonMonths = n;
  }
  overrideArgs.push(`horizon_months=${horizonMonths}`);

  for (const [k, v] of url.searchParams.entries()) {
    if (k === "horizon") continue;
    const n = Number(v);
    if (!Number.isFinite(n)) continue;
    // Allowlist of safe driver keys — prevents command-injection via arbitrary keys
    if (!/^[a-z_]+$/.test(k)) continue;
    overrideArgs.push(`${k}=${n}`);
  }

  const scriptPath = path.join(SCRIPTS_DIR, "target_api.py");
  try {
    const { stdout } = await execFileP("python", [scriptPath, ticker, ...overrideArgs], {
      cwd: path.dirname(SCRIPTS_DIR),
      maxBuffer: 5_000_000,
      timeout: 60_000,
    });
    const payload = JSON.parse(stdout);
    return NextResponse.json(payload);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { error: `target_api.py failed: ${msg}`, ticker },
      { status: 500 }
    );
  }
}
