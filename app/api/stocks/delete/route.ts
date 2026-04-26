import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import fs from "fs";
import path from "path";

const DATA_DIR = path.join(process.cwd(), "data");

export async function POST(request: Request) {
  try {
    const body = await request.json();

    // Support both single ticker and bulk tickers
    const tickers: string[] = body.tickers
      ? body.tickers
      : body.ticker
      ? [body.ticker]
      : [];

    if (tickers.length === 0) {
      return NextResponse.json({ error: "ticker or tickers[] required" }, { status: 400 });
    }

    // Soft-delete: set active = false
    const { data, error } = await supabase
      .from("stocks")
      .update({ active: false })
      .in("ticker", tickers)
      .select("ticker");

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    // Signal any running mini-pipelines to stop
    try {
      fs.mkdirSync(DATA_DIR, { recursive: true });
      for (const t of tickers) {
        const cancelFile = path.join(DATA_DIR, `.pipeline-cancel-${t}`);
        fs.writeFileSync(cancelFile, new Date().toISOString(), "utf-8");
      }
    } catch {
      // Non-fatal
    }

    const deleted = data?.map(d => d.ticker) || [];
    return NextResponse.json({
      success: true,
      tickers: deleted,
      message: `${deleted.length} stock(s) removed from watchlist.`,
    });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
