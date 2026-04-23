import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

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

    return NextResponse.json({
      success: true,
      ticker,
      message: `${ticker} removed from watchlist.`,
    });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
