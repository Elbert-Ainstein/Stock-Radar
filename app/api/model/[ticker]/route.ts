import { NextRequest, NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";
import { promisify } from "util";
import { MAX_TARGET_PRICE_RATIO, MAX_TARGET_CHANGE_FRAC } from "@/lib/registries";

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

  // Archetype override (string, not numeric — handled separately)
  const archetypeRaw = url.searchParams.get("archetype");
  if (archetypeRaw && /^[a-z_]+$/.test(archetypeRaw)) {
    overrideArgs.push(`archetype=${archetypeRaw}`);
  }

  for (const [k, v] of url.searchParams.entries()) {
    if (k === "horizon" || k === "archetype") continue;
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

    // ─── Circuit breaker: Engine → Frontend ───
    // Annotate the payload with data quality flags before sending to the UI.
    const cb_warnings: string[] = [];
    const cb_flags: string[] = [];

    const target = payload?.target;
    if (target) {
      const basePrice = target.base;
      const currentPrice = target.current_price;

      // 1. Extreme prediction check
      if (basePrice && currentPrice && currentPrice > 0) {
        const ratio = basePrice / currentPrice;
        if (ratio > MAX_TARGET_PRICE_RATIO) {
          cb_warnings.push(
            `EXTREME_TARGET: base target $${Math.round(basePrice)} is ${ratio.toFixed(1)}x current price $${Math.round(currentPrice)}`
          );
          cb_flags.push("EXTREME_TARGET");
        }
      }

      // 2. All required fields present
      const requiredFields = ["base", "low", "high", "current_price", "ttm_revenue", "shares_diluted"];
      for (const f of requiredFields) {
        const val = target[f];
        if (val === null || val === undefined || (typeof val === "number" && isNaN(val))) {
          cb_warnings.push(`MISSING_FIELD: target.${f} is ${val}`);
          cb_flags.push("MISSING_FIELD");
        }
      }

      // 3. Scenario ordering sanity (low < base < high)
      if (target.low && target.base && target.high) {
        if (target.low > target.base || target.base > target.high) {
          cb_warnings.push(
            `SCENARIO_INVERSION: low=$${Math.round(target.low)} base=$${Math.round(target.base)} high=$${Math.round(target.high)}`
          );
          cb_flags.push("SCENARIO_INVERSION");
        }
      }
    }

    // Attach quality metadata to payload
    payload._data_quality = {
      confidence: cb_flags.includes("EXTREME_TARGET") || cb_flags.includes("MISSING_FIELD")
        ? "low"
        : cb_flags.length > 0
          ? "medium"
          : "high",
      warnings: cb_warnings,
      flags: cb_flags,
    };

    return NextResponse.json(payload);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { error: `target_api.py failed: ${msg}`, ticker },
      { status: 500 }
    );
  }
}
