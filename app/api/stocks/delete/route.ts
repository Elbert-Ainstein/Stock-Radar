import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import fs from "fs";
import path from "path";

const DATA_DIR = path.join(process.cwd(), "data");

export async function POST(request: Request) {
  try {
    const { ticker } = await request.json();

    if (!ticker) {
      return NextResponse.json({ error: "ticker required" }, { status: 400 });
    }

    // Soft-delete: set active = false
    const { data, error } = await supabase
      .from("stocks")
      .update({ active: false })
      .eq("ticker", ticker)
      .select("ticker");

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    if (!data || data.length === 0) {
      return NextResponse.json({ error: "Stock not found" }, { status: 404 });
    }

    // Signal any running mini-pipeline for this ticker to stop.
    // The pipeline checks for this file between stages and halts early.
    try {
      fs.mkdirSync(DATA_DIR, { recursive: true });
      const cancelFile = path.join(DATA_DIR, `.pipeline-cancel-${ticker}`);
      fs.writeFileSync(cancelFile, new Date().toISOString(), "utf-8");
    } catch {
      // Non-fatal — pipeline will just finish normally
    }

    return NextResponse.json({
      success: true,
      ticker,
      message: `${ticker} removed from watchlist.`,
    });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
