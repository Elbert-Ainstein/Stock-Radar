import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

// Allow letters AND digits for HK tickers like 6082.HK
const TICKER_RE = /^[A-Z0-9]{1,6}(\.[A-Z]{1,3})?$/;

function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

/**
 * GET /api/thesis/[ticker]
 *
 * Returns the LATEST thesis row for a ticker from the `theses` table —
 * the v2 dashboard headline source produced by scripts/run_thesis.py.
 *
 * Response shape:
 *   {
 *     ticker, run_at, prompt_version,
 *     thesis_target, breakout_price, risk_adj_target,
 *     conviction, position_size_pct, buy_below, trim_above,
 *     filters, top_risks, top_catalysts, kill_triggers,
 *     spot_at_run, trigger_reason, markdown_path,
 *     coverage_quality, cited_domains,
 *     input_tokens, output_tokens, web_search_count
 *   }
 *
 * If no thesis exists for the ticker, returns 404 with { exists: false }
 * — UI should render a "Run thesis" button in that state.
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

  try {
    const { data, error } = await supabase
      .from("theses")
      .select("*")
      .eq("ticker", ticker)
      .order("run_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      console.error(`[thesis GET ${ticker}] supabase error:`, error.message);
      return NextResponse.json(
        { error: "supabase query failed", detail: error.message },
        { status: 500 }
      );
    }

    if (!data) {
      return NextResponse.json(
        { exists: false, ticker, message: "no thesis on file — trigger a run via POST /rerun" },
        { status: 404 }
      );
    }

    // Strip the heaviest debug field unless explicitly requested via ?include_raw=1
    const url = new URL(_req.url);
    const includeRaw = url.searchParams.get("include_raw") === "1";
    if (!includeRaw && data.raw_response_blocks) {
      delete (data as Record<string, unknown>).raw_response_blocks;
    }

    return NextResponse.json({ exists: true, ...data });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error(`[thesis GET ${ticker}] unhandled:`, msg);
    return NextResponse.json({ error: "unhandled", detail: msg }, { status: 500 });
  }
}
