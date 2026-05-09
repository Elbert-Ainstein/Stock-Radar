/**
 * GET /api/convergence
 *
 * Returns top-N convergence candidates from discovery_universe with class-aware
 * scoring. Mirrors the logic of `scripts/convergence_detector.py` so the
 * dashboard can render Module 11a output without shelling to Python.
 *
 * Query params:
 *   ?status=exploring,promising,qualified  (default: exploring,promising,qualified)
 *   ?top=25                                  (default: 25, max 100)
 *
 * Two intended consumers:
 *   - Tier1Panel (status=exploring,promising,qualified) — discovery surface
 *   - WatchlistConvergencePanel (status=watchlisted)    — watchlist refresh surface
 *
 * Class taxonomy must stay in sync with scripts/convergence_detector.py
 * SOURCE_CLASS_MAP. Update both together if you add a new class prefix.
 */
import { NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

const SOURCE_CLASS_MAP: ReadonlyArray<readonly [string, string]> = [
  ["13f_", "smart_money"],
  ["insider_", "insider"],
  ["news_", "news"],
  ["theme_", "theme"],
  ["yahoo_", "momentum"],
  ["watchlist_seed", "manual"],
] as const;

function tagToClass(tag: string): string {
  const t = tag.trim().toLowerCase();
  for (const [prefix, cls] of SOURCE_CLASS_MAP) {
    if (t.startsWith(prefix)) return cls;
  }
  return `other:${t.slice(0, 20)}`;
}

function splitSourceTags(source: string | null | undefined): string[] {
  if (!source) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of source.split(",")) {
    const tag = raw.trim();
    if (tag && !seen.has(tag)) {
      seen.add(tag);
      out.push(tag);
    }
  }
  return out;
}

function classifyTier(classCount: number): "STRONG" | "MEDIUM" | "SINGLE" | "EMPTY" {
  if (classCount >= 3) return "STRONG";
  if (classCount === 2) return "MEDIUM";
  if (classCount === 1) return "SINGLE";
  return "EMPTY";
}

export interface ConvergenceRow {
  ticker: string;
  tier: "STRONG" | "MEDIUM" | "SINGLE" | "EMPTY";
  class_count: number;
  source_count: number;
  classes: string[];
  sources: string[];
  cheap_score: number | null;
  status: string | null;
  market: string | null;
  sector: string | null;
  first_seen: string | null;
  last_scanned: string | null;
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const statusParam = url.searchParams.get("status") || "exploring,promising,qualified";
  const topRaw = parseInt(url.searchParams.get("top") || "25", 10);
  const top = Number.isFinite(topRaw) ? Math.min(Math.max(topRaw, 1), 100) : 25;

  const statuses = statusParam.split(",").map(s => s.trim()).filter(Boolean);
  if (statuses.length === 0) {
    return NextResponse.json({ error: "no statuses provided" }, { status: 400 });
  }

  let rows: any[] = [];
  try {
    const sb = getSupabase();
    const { data, error } = await sb
      .from("discovery_universe")
      .select("ticker,source,status,cheap_score,first_seen,last_scanned,market,sector")
      .in("status", statuses);
    if (error) {
      return NextResponse.json(
        { error: `[SR-CONVERGE-API-001] supabase query failed: ${error.message}` },
        { status: 500 }
      );
    }
    rows = data || [];
  } catch (e: any) {
    return NextResponse.json(
      { error: `[SR-CONVERGE-API-002] supabase client init failed: ${e.message}` },
      { status: 500 }
    );
  }

  const scored: ConvergenceRow[] = [];
  for (const r of rows) {
    const tags = splitSourceTags(r.source);
    if (tags.length === 0) continue;
    const classSet = new Set<string>();
    for (const t of tags) classSet.add(tagToClass(t));
    const classes = Array.from(classSet).sort();
    scored.push({
      ticker: r.ticker,
      tier: classifyTier(classes.length),
      class_count: classes.length,
      source_count: tags.length,
      classes,
      sources: tags,
      cheap_score: r.cheap_score,
      status: r.status,
      market: r.market,
      sector: r.sector,
      first_seen: r.first_seen,
      last_scanned: r.last_scanned,
    });
  }

  // Sort: class_count desc → cheap_score desc (null sinks) → source_count desc → ticker asc.
  // cheap_score is the primary differentiator within tier so AXON (cheap 8.0)
  // ranks above ENTG (cheap 5.0) even though ENTG has more 13F manager tags.
  scored.sort((a, b) => {
    if (b.class_count !== a.class_count) return b.class_count - a.class_count;
    const csA = a.cheap_score ?? -1;
    const csB = b.cheap_score ?? -1;
    if (csB !== csA) return csB - csA;
    if (b.source_count !== a.source_count) return b.source_count - a.source_count;
    return a.ticker.localeCompare(b.ticker);
  });

  const limited = scored.slice(0, top);

  const tierCounts = {
    STRONG: limited.filter(r => r.tier === "STRONG").length,
    MEDIUM: limited.filter(r => r.tier === "MEDIUM").length,
    SINGLE: limited.filter(r => r.tier === "SINGLE").length,
  };

  return NextResponse.json({
    run_at: new Date().toISOString(),
    statuses_queried: statuses,
    row_count: limited.length,
    total_matched: scored.length,
    tier_counts: tierCounts,
    rows: limited,
  });
}
