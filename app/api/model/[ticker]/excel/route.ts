import { NextRequest, NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";
import { promisify } from "util";

const execFileP = promisify(execFile);
const PROJECT_DIR = process.cwd();

const TICKER_RE = /^[A-Z]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

/**
 * GET /api/model/[ticker]/excel
 *
 * Builds the institutional-grade Excel model via scripts/model_export.py and streams
 * the .xlsx back to the browser. Every forecast cell is a live formula
 * referencing the Assumptions tab — the user can tweak inputs in Excel and
 * see the target move.
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

  // Horizon: only 12, 24, 36 allowed; defaults to 12
  const url = new URL(_req.url);
  let horizonMonths = 12;
  const horizonRaw = url.searchParams.get("horizon");
  if (horizonRaw) {
    const n = Number(horizonRaw);
    if ([12, 24, 36].includes(n)) horizonMonths = n;
  }

  const outPath = path.join(PROJECT_DIR, "out", `${ticker}_model.xlsx`);

  try {
    await execFileP(
      "python",
      [path.join(PROJECT_DIR, "scripts", "model_export.py"), ticker, `horizon_months=${horizonMonths}`],
      {
        cwd: PROJECT_DIR,
        maxBuffer: 5_000_000,
        timeout: 120_000,
      }
    );
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { error: `model_export.py failed: ${msg}`, ticker },
      { status: 500 }
    );
  }

  if (!fs.existsSync(outPath)) {
    return NextResponse.json(
      { error: `expected output file not found: ${outPath}` },
      { status: 500 }
    );
  }

  const buf = fs.readFileSync(outPath);
  return new NextResponse(buf, {
    status: 200,
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="${ticker}_model.xlsx"`,
      "Cache-Control": "no-store",
    },
  });
}
