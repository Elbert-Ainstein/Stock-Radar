import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

// GET /api/feedback — returns scout accuracy data + recent outcomes
export async function GET() {
  try {
    // Scout accuracy (aggregated stats per scout per window)
    const { data: accuracy, error: accErr } = await supabase
      .from("scout_accuracy")
      .select("*")
      .order("accuracy_pct", { ascending: false });

    if (accErr) {
      console.error("[feedback] Failed to load accuracy:", accErr.message);
    }

    // Recent outcomes (last 50 for display)
    const { data: outcomes, error: outErr } = await supabase
      .from("signal_outcomes")
      .select("*")
      .order("evaluated_at", { ascending: false })
      .limit(50);

    if (outErr) {
      console.error("[feedback] Failed to load outcomes:", outErr.message);
    }

    // Total outcome counts for summary
    const { count: totalOutcomes } = await supabase
      .from("signal_outcomes")
      .select("*", { count: "exact", head: true });

    return NextResponse.json({
      accuracy: accuracy || [],
      recentOutcomes: outcomes || [],
      totalOutcomes: totalOutcomes || 0,
    });
  } catch (e: any) {
    return NextResponse.json(
      { error: e.message || "Failed to load feedback data" },
      { status: 500 }
    );
  }
}
