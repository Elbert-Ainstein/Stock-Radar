import { supabase } from "./supabase";
import { SCOUT_REGISTRY } from "./registries";

// ─── Currency inference from ticker suffix ───
const EXCHANGE_CURRENCY: Record<string, string> = {
  HK: "HKD", T: "JPY", TW: "TWD", L: "GBP", PA: "EUR", DE: "EUR",
  AS: "EUR", MI: "EUR", MC: "EUR", SW: "CHF", ST: "SEK", OL: "NOK",
  CO: "DKK", TO: "CAD", AX: "AUD", SI: "SGD", KS: "KRW", SA: "BRL",
  TA: "ILS",
};

export function inferCurrency(ticker: string): string {
  const dot = ticker.indexOf(".");
  if (dot < 0) return "USD"; // bare ticker = US-listed
  const suffix = ticker.slice(dot + 1);
  return EXCHANGE_CURRENCY[suffix] || "USD";
}

// ─── Interfaces ───
export interface ScoutSignal {
  scout: string;
  ai: string;
  signal: "bullish" | "bearish" | "neutral";
  summary: string;
  timestamp: string;
}

export interface DataQuality {
  confidence: "high" | "medium" | "low";
  confidence_score: number;
  scouts_scored: number;
  scouts_total: number;
  scout_names: string[];
  warnings: string[];
}

export interface ThesisFilter {
  pass: boolean;
  evidence: string;
}

export interface ThesisRisk {
  name: string;
  probability: number | null | undefined;
  price_impact: number | null | undefined;
  early_signal: string;
}

export interface ThesisCatalyst {
  name: string;
  probability: number | null | undefined;
  price_impact: number | null | undefined;
  confirming_signal: string;
}

export interface ThesisRun {
  ticker: string;
  run_at: string;
  prompt_version: string;
  thesis_target: number | null;
  breakout_price: number | null;
  risk_adj_target: number | null;
  conviction: "HIGH" | "MEDIUM" | "LOW" | "BROKEN" | string | null;
  position_size_pct: number | null;
  buy_below: number | null;
  trim_above: number | null;
  filters: Record<string, ThesisFilter>;
  top_risks: ThesisRisk[];
  top_catalysts: ThesisCatalyst[];
  kill_triggers: string[];
  spot_at_run: number | null;
  trigger_reason: string | null;
  markdown_path: string | null;
  coverage_quality: "HIGH" | "MEDIUM" | "LOW" | string | null;
  cited_domains: string[];
}

// ─── Discovery universe (self-evolving multi-market candidate registry) ───
// Mirrors supabase/2026-05-04_discovery_universe.sql.
// Distinct from the legacy `discovery_candidates` table (per-run scout outputs):
// `discovery_universe` is the persistent upstream pool that scouts read from.
export type DiscoveryMarket = "US" | "HK" | "TW" | "JP" | "KR";
export type DiscoveryStatus =
  | "exploring"
  | "promising"
  | "promoted"
  | "dropped"
  | "watchlisted";

export interface DiscoveryScanEntry {
  ts: string;
  score: number | null;
  verdict: string | null;
  model: string | null;
  version: string | null;
}

export interface DiscoveryUniverseRow {
  ticker: string;
  market: DiscoveryMarket | string;
  company_name: string | null;
  sector: string | null;
  first_seen: string;
  last_scanned: string | null;
  source: string;
  cheap_score: number | null;
  cheap_verdict: string | null;
  full_score: number | null;
  status: DiscoveryStatus | string;
  scan_history: DiscoveryScanEntry[];
  market_cap_usd: number | null;
  currency: string | null;
}

export interface Stock {
  ticker: string;
  name: string;
  sector: string;
  currency: string;  // "USD", "EUR", "HKD", etc. — inferred from ticker suffix
  price: number;
  change: number;
  changePct: number;
  marketCap: string;
  score: number;
  scoreDelta: number;
  watchlistThesis: string;
  killCondition: string;
  killConditionEval?: {
    status: "safe" | "warning" | "triggered";
    confidence: number;
    reasoning: string;
    evidence: string[];
    checked_at: string;
  } | null;
  signals: ScoutSignal[];
  scoreHistory: number[];
  catalysts: string[];
  tags: string[];
  overallSignal: string;
  convergence: { bullish: number; bearish: number; neutral: number; total: number };
  thesisRun?: ThesisRun | null;
  dataQuality?: DataQuality | null;
}

export interface MacroContext {
  sp500: number;
  sp500Change: number;
  nasdaq: number;
  nasdaqChange: number;
  vix: number;
  vixChange: number;
  tenYear: number;
  tenYearChange: number;
  fedNext: string;
  sectorRotation: string;
}

// ─── Format market cap ───
function formatMarketCap(billions: number | undefined): string {
  if (!billions) return "N/A";
  if (billions >= 1000) return `$${(billions / 1000).toFixed(1)}T`;
  if (billions >= 1) return `$${billions.toFixed(1)}B`;
  return `$${(billions * 1000).toFixed(0)}M`;
}

// ─── Main data loader (Supabase) ───
export async function loadStocks(): Promise<Stock[]> {
  // PRIMARY SOURCE: stocks table (always has all active stocks)
  const { data: stockRows, error: sErr } = await supabase
    .from("stocks")
    .select("*")
    .eq("active", true);

  if (sErr || !stockRows) {
    console.error("[data] Failed to load stocks:", sErr?.message);
    return [];
  }

  // ENRICH: latest analysis per stock (may be empty if pipeline hasn't run)
  const { data: analysisRows } = await supabase
    .from("latest_analysis")
    .select("*");

  const analysisMap: Record<string, any> = {};
  for (const a of analysisRows || []) {
    analysisMap[a.ticker] = a;
  }

  // ENRICH: latest thesis row per stock from `theses` table (v2 dashboard headline source).
  // The table has multiple rows per ticker (one per run); we want the most recent.
  // Explicit columns (skip raw_response_blocks ~50-100KB/row).
  // LIMIT 200 bounds payload as event-triggered runs accumulate (session 5+).
  const THESIS_FIELDS = [
    "ticker","run_at","prompt_version",
    "thesis_target","breakout_price","risk_adj_target",
    "conviction","position_size_pct","buy_below","trim_above",
    "filters","top_risks","top_catalysts","kill_triggers",
    "spot_at_run","trigger_reason","markdown_path",
    "coverage_quality","cited_domains",
  ].join(",");
  const { data: thesesRows } = await supabase
    .from("theses")
    .select(THESIS_FIELDS)
    .order("run_at", { ascending: false })
    // LIMIT 1000 gives ~14 years of runway at monthly cadence on 6 tickers.
    // BEFORE session 5 (event-triggered runs) deploys, replace this with a
    // Postgres view `latest_thesis_per_ticker` to guarantee per-ticker
    // coverage regardless of run distribution.
    .limit(1000);

  const thesesMap: Record<string, ThesisRun> = {};
  for (const t of thesesRows || []) {
    if (!thesesMap[t.ticker]) {
      // First (most recent) row per ticker, since query is ordered DESC
      thesesMap[t.ticker] = t as ThesisRun;
    }
  }

  // ENRICH: latest signals per stock per scout
  const { data: signalRows } = await supabase
    .from("latest_signals")
    .select("*");

  const signalsByTicker: Record<string, ScoutSignal[]> = {};
  for (const sig of signalRows || []) {
    if (!signalsByTicker[sig.ticker]) signalsByTicker[sig.ticker] = [];
    signalsByTicker[sig.ticker].push({
      scout: sig.scout,
      ai: sig.ai || "",
      signal: sig.signal as "bullish" | "bearish" | "neutral",
      summary: sig.summary || "",
      timestamp: sig.created_at || "",
    });
  }

  const stocks: Stock[] = stockRows.map((row: any) => {
    const ticker = row.ticker;
    const analysis = analysisMap[ticker];
    const signals = signalsByTicker[ticker] || [];

    // Price data: prefer analysis.price_data, fall back to signal quant data
    const pd = analysis?.price_data || {};
    const quantSignal = signals.find(s => s.scout.toLowerCase() === "quant");
    let price = pd.price || 0;
    let change = pd.change || 0;
    let changePct = pd.change_pct || 0;
    let marketCapB = pd.market_cap_b;

    // If no analysis price data, try to extract from quant signal's raw data in signals table
    if (price === 0 && !analysis) {
      // Read raw quant signal data from latest_signals
      const rawQuant = (signalRows || []).find(
        (s: any) => s.ticker === ticker && s.scout.toLowerCase() === "quant"
      );
      if (rawQuant?.data) {
        price = rawQuant.data.price || 0;
        change = rawQuant.data.change || 0;
        changePct = rawQuant.data.change_pct || 0;
        marketCapB = rawQuant.data.market_cap_b;
      }
    }

    const score = analysis?.composite_score || 0;
    const convergence = analysis?.convergence || { bullish: 0, bearish: 0, neutral: 0, total: 0 };

    // Data quality from analyst circuit breaker (if available).
    // Fallback: count distinct scouts from signals array.
    const analystDQ = analysis?.data_quality;
    const distinctScouts = new Set(signals.map(s => s.scout.toLowerCase()));
    const fallbackConfidence = distinctScouts.size >= 6 ? "high" : distinctScouts.size >= 4 ? "medium" : "low";
    const fallbackScore = distinctScouts.size >= 6 ? 0.80 : distinctScouts.size >= 4 ? 0.55 : 0.35;
    const dataQuality: DataQuality = analystDQ || {
      confidence: fallbackConfidence,
      confidence_score: fallbackScore,
      scouts_scored: distinctScouts.size,
      scouts_total: 9,
      scout_names: Array.from(distinctScouts),
      warnings: distinctScouts.size < 4
        ? [`Only ${distinctScouts.size}/9 scouts contributed signals`]
        : [],
    };

    return {
      ticker,
      name: row.name || ticker,
      sector: row.sector || "",
      currency: inferCurrency(ticker),
      price,
      change,
      changePct,
      marketCap: formatMarketCap(marketCapB),
      score,
      scoreDelta: 0,
      watchlistThesis: row.thesis || "",
      killCondition: row.kill_condition || "",
      signals,
      scoreHistory: score > 0 ? [score, score] : [0],
      catalysts: [],
      tags: row.tags || [],
      overallSignal: analysis?.overall_signal || "neutral",
      convergence,
      thesisRun: thesesMap[ticker] || null,
      dataQuality,
    };
  });

  // Sort by score descending (stocks without scores go to end)
  stocks.sort((a, b) => b.score - a.score);
  return stocks;
}

// ─── Load macro context ───
export async function loadMacro(): Promise<MacroContext> {
  return {
    sp500: 0,
    sp500Change: 0,
    nasdaq: 0,
    nasdaqChange: 0,
    vix: 0,
    vixChange: 0,
    tenYear: 0,
    tenYearChange: 0,
    fedNext: "—",
    sectorRotation: "—",
  };
}

// ─── Scout metadata ───
export interface ScoutInfo {
  name: string;
  signalCount: number;
  generatedAt: string;
  requiresKey: boolean;
}

// SCOUT_REGISTRY imported from lib/registries.ts (single source of truth)

// ─── Load metadata ───
export async function loadMeta(): Promise<{ generatedAt: string; scoutsActive: string[]; scoutDetails: ScoutInfo[] }> {
  // Get the latest pipeline run (if any)
  const { data: run } = await supabase
    .from("pipeline_runs")
    .select("*")
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  // Also count actual signals per scout from latest_signals (ground truth)
  const { data: latestSignals } = await supabase
    .from("latest_signals")
    .select("scout, created_at");

  const signalCountByScout: Record<string, { count: number; latestAt: string }> = {};
  for (const sig of latestSignals || []) {
    const scout = (sig.scout || "").toLowerCase();
    if (!signalCountByScout[scout]) {
      signalCountByScout[scout] = { count: 0, latestAt: sig.created_at || "" };
    }
    signalCountByScout[scout].count++;
    if (sig.created_at > signalCountByScout[scout].latestAt) {
      signalCountByScout[scout].latestAt = sig.created_at;
    }
  }

  const scoutDetailsFromRun = run?.scout_details || {};
  const scoutsActive = run?.scouts_active || Object.keys(signalCountByScout);

  const allScoutNames = Object.keys(SCOUT_REGISTRY);
  const scoutDetails: ScoutInfo[] = allScoutNames.map(name => {
    const reg = SCOUT_REGISTRY[name];
    const fromRun = scoutDetailsFromRun[name];
    const fromSignals = signalCountByScout[name];
    // Use whichever source has data
    const signalCount = fromSignals?.count || fromRun?.signal_count || 0;
    const generatedAt = fromSignals?.latestAt || fromRun?.generated_at || "";
    return {
      name: reg.label,
      signalCount,
      generatedAt,
      requiresKey: reg.requiresKey,
    };
  });

  // Find most recent timestamp from any source
  const latestSignalTime = Object.values(signalCountByScout)
    .map(s => s.latestAt)
    .sort()
    .pop() || "";
  const generatedAt = run?.completed_at || run?.started_at || latestSignalTime;

  return {
    generatedAt,
    scoutsActive,
    scoutDetails,
  };
}

// ─── Load stocks for model page (full enriched data) ───
export async function loadStocksForModel(): Promise<any[]> {
  // Load all active stocks from stocks table
  const { data: stockRows, error: sErr } = await supabase
    .from("stocks")
    .select("*")
    .eq("active", true);

  if (sErr || !stockRows) {
    console.error("[data] Failed to load stocks:", sErr?.message);
    return [];
  }

  // Enrich with latest thesis row per ticker (v2: anchor for the model page)
  const THESIS_FIELDS_M = [
    "ticker","run_at","prompt_version",
    "thesis_target","breakout_price","risk_adj_target",
    "conviction","position_size_pct","buy_below","trim_above",
  ].join(",");
  const { data: thesesRowsM } = await supabase
    .from("theses")
    .select(THESIS_FIELDS_M)
    .order("run_at", { ascending: false })
    .limit(1000);
  const thesesMapM: Record<string, ThesisRun> = {};
  for (const t of thesesRowsM || []) {
    if (!thesesMapM[t.ticker]) thesesMapM[t.ticker] = t as ThesisRun;
  }


  // Load latest analysis
  const { data: analysisRows } = await supabase
    .from("latest_analysis")
    .select("*");

  const analysisMap: Record<string, any> = {};
  for (const a of analysisRows || []) {
    analysisMap[a.ticker] = a;
  }

  // Load latest signals (for quant data)
  const { data: signalRows } = await supabase
    .from("latest_signals")
    .select("*");

  const signalMap: Record<string, Record<string, any>> = {};
  for (const sig of signalRows || []) {
    if (!signalMap[sig.ticker]) signalMap[sig.ticker] = {};
    signalMap[sig.ticker][sig.scout] = sig;
  }

  return stockRows.map((w: any) => {
    const a = analysisMap[w.ticker] || {};
    const quantSig = signalMap[w.ticker]?.["quant"];
    const quant = quantSig?.data || {};

    // Merge analyst criteria with stock criteria
    const evalCriteria = a.criteria_eval?.criteria || [];
    const baseCriteria = w.criteria || [];
    const mergedCriteria = baseCriteria.map((wc: any) => {
      const ec = evalCriteria.find((e: any) => e.id === wc.id);
      return ec ? { ...wc, ...ec } : wc;
    });

    // Build target object from stock columns
    // model.tsx expects: target.price, target.model_defaults, target.scenarios
    const target = {
      price: w.target_price || 0,
      timeline_years: w.timeline_years || 3,
      valuation_method: w.valuation_method || "pe",
      target_multiple: w.target_multiple,
      notes: w.target_notes || "",
      model_defaults: w.model_defaults || {},
      scenarios: w.scenarios || {},
    };

    return {
      ticker: w.ticker,
      name: w.name,
      sector: w.sector,
      watchlistThesis: w.thesis,
      thesisRun: thesesMapM[w.ticker] || null,
      killCondition: w.kill_condition,
      archetype: w.archetype || null,
      target,
      criteria: mergedCriteria,
      currentPrice: quant.price || 0,
      marketCapB: quant.market_cap_b || 0,
      psRatio: quant.ps_ratio || 0,
      peRatio: quant.pe_ratio || 0,
      forwardPe: quant.forward_pe || 0,
      revenueGrowthPct: quant.revenue_growth_pct || 0,
      earningsGrowthPct: quant.earnings_growth_pct || 0,
      operatingMarginPct: quant.operating_margin_pct || 0,
      grossMarginPct: quant.gross_margin_pct || 0,
      compositeScore: a.composite_score || 0,
      autoTiers: a.auto_tiers || [],
      // Event impacts — passes through untouched from analyst.
      // Shape: { events: [...], summary: {...}, merge_enabled, proposed_target_with_events, reasoner_available }
      eventImpacts: a.event_impacts || {
        events: [],
        summary: { event_count: 0, event_adjustment_pct: 0, raw_sum_pct: 0, capped: false, up_count: 0, down_count: 0 },
        merge_enabled: false,
        proposed_target_with_events: w.target_price || 0,
        reasoner_available: false,
      },
      researchCache: w.research_cache || null,
      killConditionEval: a.kill_condition_eval || null,
    };
  });
}

// ─── Delete stock ───
export async function deleteStock(ticker: string): Promise<boolean> {
  const { error } = await supabase
    .from("stocks")
    .update({ active: false })
    .eq("ticker", ticker);
  return !error;
}

// ─── Add / update stock ───
export async function upsertStock(stock: any): Promise<boolean> {
  const { error } = await supabase
    .from("stocks")
    .upsert(stock, { onConflict: "ticker" });
  return !error;
}
