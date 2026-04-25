import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

/**
 * GET /api/logs — Activity log endpoint for the /logs dashboard page.
 *
 * Query params:
 *   category  — filter by category (pipeline, scout, analyst, etc.)
 *   level     — filter by level (info, warn, error)
 *   ticker    — filter by ticker symbol
 *   run_id    — filter by pipeline run ID
 *   limit     — max rows (default 100, max 500)
 *   offset    — pagination offset (default 0)
 *   since     — ISO timestamp, only return logs after this time
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const category = url.searchParams.get("category");
  const level = url.searchParams.get("level");
  const ticker = url.searchParams.get("ticker");
  const runId = url.searchParams.get("run_id");
  const since = url.searchParams.get("since");
  const limitRaw = parseInt(url.searchParams.get("limit") || "100", 10);
  const offset = parseInt(url.searchParams.get("offset") || "0", 10);
  const limit = Math.min(Math.max(1, limitRaw), 500);

  let query = supabase
    .from("activity_log")
    .select("*", { count: "exact" })
    .order("created_at", { ascending: false })
    .range(offset, offset + limit - 1);

  if (category) query = query.eq("category", category);
  if (level) query = query.eq("level", level);
  if (ticker) query = query.eq("ticker", ticker);
  if (runId) query = query.eq("run_id", runId);
  if (since) query = query.gte("created_at", since);

  const { data, error, count } = await query;

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // Group by run_id for timeline view
  const runs: Record<string, any[]> = {};
  const noRun: any[] = [];

  for (const row of data || []) {
    if (row.run_id) {
      if (!runs[row.run_id]) runs[row.run_id] = [];
      runs[row.run_id].push(row);
    } else {
      noRun.push(row);
    }
  }

  return NextResponse.json({
    logs: data || [],
    total: count || 0,
    limit,
    offset,
    grouped: {
      by_run: runs,
      ungrouped: noRun,
    },
  });
}
