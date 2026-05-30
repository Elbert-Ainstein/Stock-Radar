/**
 * /api/scenarios/[ticker]
 *
 * CRUD for the Phase 1 what-if scenario sandbox.
 * Backed by Supabase scenario_scratch table (see supabase/2026-05-09_scenario_scratch.sql,
 * with post-review fixes in supabase/2026-05-09b_scenario_scratch_fixes.sql).
 *
 * GET  → list active scenarios for ticker (most-recent first)
 * POST → create or update a scenario (idempotent on ticker+scenario_name).
 *        body: { scenario_name, drivers, computed_price, upside_vs_current?,
 *                delta_vs_model?, spot_at_save?, notes?, valuation_method? }
 * DELETE → soft-delete (sets active=false). body: { scenario_name } OR ?name=
 *
 * Why upsert in POST: WhatIfTab will save-as-you-tweak with debounce. Hard insert
 * would fail the unique constraint on every save after the first. PostgREST
 * upsert by composite key handles it.
 */
import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

const TICKER_RE = /^[A-Z0-9]{1,6}(\.[A-Z]{1,3})?$/;
function isValidTicker(t: string): boolean {
  return TICKER_RE.test(t);
}

interface DriversShape {
  rev_growth_y1: number;
  rev_growth_terminal: number;
  ebitda_margin: number;
  fcf_sbc_margin: number;
  ev_ebitda_multiple: number;
  ev_fcf_multiple: number;
  wacc: number;
  blend: number;
  term_ps?: number | null;
}

function isValidDrivers(d: unknown): d is DriversShape {
  if (!d || typeof d !== "object") return false;
  const o = d as Record<string, unknown>;
  const numKeys = [
    "rev_growth_y1", "rev_growth_terminal", "ebitda_margin",
    "fcf_sbc_margin", "ev_ebitda_multiple", "ev_fcf_multiple",
    "wacc", "blend",
  ];
  for (const k of numKeys) {
    if (typeof o[k] !== "number" || !Number.isFinite(o[k] as number)) return false;
  }
  return true;
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!isValidTicker(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }
  try {
    const sb = getSupabase();
    const { data, error } = await sb
      .from("scenario_scratch")
      .select("id,ticker,scenario_name,created_at,updated_at,drivers,computed_price,upside_vs_current,delta_vs_model,spot_at_save,notes,valuation_method")
      .eq("ticker", ticker)
      .eq("active", true)
      .order("created_at", { ascending: false });
    if (error) {
      return NextResponse.json(
        { error: `[SR-SCENARIO-API-001] supabase query failed: ${error.message}` },
        { status: 500 }
      );
    }
    return NextResponse.json({ ticker, scenarios: data || [] });
  } catch (e: any) {
    return NextResponse.json(
      { error: `[SR-SCENARIO-API-002] supabase init failed: ${e.message}` },
      { status: 500 }
    );
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!isValidTicker(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }
  let body: any;
  try { body = await req.json(); } catch { body = null; }
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }
  const scenarioName = String(body.scenario_name || "").trim();
  if (!scenarioName || scenarioName.length > 80) {
    return NextResponse.json({ error: "scenario_name required, ≤80 chars" }, { status: 400 });
  }
  if (!isValidDrivers(body.drivers)) {
    return NextResponse.json({ error: "invalid drivers shape" }, { status: 400 });
  }
  if (typeof body.computed_price !== "number" || !Number.isFinite(body.computed_price)) {
    return NextResponse.json({ error: "computed_price required" }, { status: 400 });
  }

  // valuation_method is persisted (post-2026-05-09b migration) so the
  // ScenarioCompare UI can warn when a saved scenario from a different
  // valuation mode is loaded. Pre-migration rows have NULL — treated as
  // "unknown mode" by the client.
  const valuationMethod = typeof body.valuation_method === "string"
    && (body.valuation_method === "revenue_multiple" || body.valuation_method === "ev_ebitda")
      ? body.valuation_method
      : null;

  const row = {
    ticker,
    scenario_name: scenarioName,
    drivers: body.drivers,
    computed_price: body.computed_price,
    upside_vs_current: typeof body.upside_vs_current === "number" ? body.upside_vs_current : null,
    delta_vs_model: typeof body.delta_vs_model === "number" ? body.delta_vs_model : null,
    spot_at_save: typeof body.spot_at_save === "number" ? body.spot_at_save : null,
    notes: typeof body.notes === "string" ? body.notes.slice(0, 2000) : null,
    valuation_method: valuationMethod,
    active: true,
  };

  try {
    const sb = getSupabase();
    // Upsert on (ticker, scenario_name) with active=true. The 2026-05-09b
    // migration replaced the (ticker, scenario_name, active) UNIQUE
    // constraint with a partial unique index on active rows only — so
    // PostgREST onConflict needs to target the index columns, not the
    // dropped constraint name. PostgREST resolves this by matching the
    // column list to any unique index, partial or full.
    const { data, error } = await sb
      .from("scenario_scratch")
      .upsert(row, { onConflict: "ticker,scenario_name" })
      .select()
      .maybeSingle();
    if (error) {
      return NextResponse.json(
        { error: `[SR-SCENARIO-API-003] upsert failed: ${error.message}` },
        { status: 500 }
      );
    }
    return NextResponse.json({ success: true, scenario: data });
  } catch (e: any) {
    return NextResponse.json(
      { error: `[SR-SCENARIO-API-004] supabase init failed: ${e.message}` },
      { status: 500 }
    );
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase().replace(/[^A-Z0-9.]/g, "");
  if (!isValidTicker(ticker)) {
    return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  }
  let scenarioName = new URL(req.url).searchParams.get("name") || "";
  if (!scenarioName) {
    try {
      const body = await req.json();
      scenarioName = String(body?.scenario_name || "");
    } catch { /* no body */ }
  }
  scenarioName = scenarioName.trim();
  if (!scenarioName) {
    return NextResponse.json({ error: "scenario_name required" }, { status: 400 });
  }
  try {
    const sb = getSupabase();
    const { error } = await sb
      .from("scenario_scratch")
      .update({ active: false })
      .eq("ticker", ticker)
      .eq("scenario_name", scenarioName)
      .eq("active", true);
    if (error) {
      return NextResponse.json(
        { error: `[SR-SCENARIO-API-005] delete failed: ${error.message}` },
        { status: 500 }
      );
    }
    return NextResponse.json({ success: true, ticker, scenario_name: scenarioName });
  } catch (e: any) {
    return NextResponse.json(
      { error: `[SR-SCENARIO-API-006] supabase init failed: ${e.message}` },
      { status: 500 }
    );
  }
}
