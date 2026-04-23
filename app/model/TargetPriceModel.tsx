"use client";

import { useState, useEffect, useMemo } from "react";

import type { Props, StockTarget } from "./types";
import {
  cn,
  detectValuationMethod,
  cyclicalMethodInfo,
  computeTargetPrice,
  computeTargetPricePS,
  computeTargetPriceCyclical,
  buildSensitivityMatrix,
  buildTimePath,
} from "./helpers";
import { useEnginePayload } from "./hooks/useEnginePayload";
import { usePipeline } from "./hooks/usePipeline";

import SliderRow from "./components/SliderRow";
import DeductionChain from "./components/DeductionChain";
import SensitivityTable from "./components/SensitivityTable";
import TimePathChart from "./components/TimePathChart";
import ScenarioSection from "./components/ScenarioSection";
import GordonModel from "./components/GordonModel";
import CriteriaChecklist from "./components/CriteriaChecklist";
import ConfidenceMeter from "./components/ConfidenceMeter";
import EventImpactsPanel from "./components/EventImpactsPanel";

// ─── Implied Target Box (kept in orchestrator — small, tightly coupled to state) ───
function ImpliedTargetBox({
  impliedPrice,
  thesisTarget,
  currentPrice,
  loading = false,
}: {
  impliedPrice: number;
  thesisTarget: number;
  currentPrice: number;
  loading?: boolean;
}) {
  const meetsTarget = impliedPrice >= thesisTarget * 0.98;
  const borderColor = loading
    ? "border-[var(--border)]"
    : meetsTarget
      ? "border-emerald-500/50"
      : "border-amber-500/30";
  const statusText = meetsTarget
    ? `$${thesisTarget.toLocaleString()} target met or exceeded`
    : `Below $${thesisTarget.toLocaleString()} target`;
  const statusColor = meetsTarget ? "text-emerald-500" : "text-amber-500";

  if (loading) {
    return (
      <div
        className={cn(
          "rounded-xl border-2 p-8 text-center transition-colors",
          borderColor,
          "bg-[var(--bg)]"
        )}
        aria-busy="true"
        aria-live="polite"
      >
        <div className="text-sm text-[var(--secondary)] mb-2">Implied target price</div>
        <div className="flex items-center justify-center gap-3 mb-3 h-[60px]">
          <span className="w-5 h-5 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
          <div className="h-8 w-40 rounded-md bg-[var(--card)] animate-pulse" />
        </div>
        <div className="text-xs text-[var(--muted)]">
          Recomputing target at new horizon...
        </div>
      </div>
    );
  }

  return (
    <div className={cn("rounded-xl border-2 p-8 text-center transition-colors", borderColor, "bg-[var(--bg)]")}>
      <div className="text-sm text-[var(--secondary)] mb-2">Implied target price</div>
      <div className={cn(
        "text-5xl font-mono font-bold mb-3",
        meetsTarget ? "text-emerald-400" : "text-amber-400"
      )}>
        ${impliedPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </div>
      <div className="text-sm text-[var(--secondary)] mb-2">
        vs ${thesisTarget.toLocaleString()} target \u00B7 current ~${currentPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </div>
      <div className={cn("text-sm", statusColor)}>
        {statusText}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════
export default function TargetPriceModel({ stocks: initialStocks, meta, initialTicker }: Props) {
  const stocks = initialStocks;
  const [selectedTicker, setSelectedTicker] = useState(
    initialTicker && initialStocks.find(s => s.ticker === initialTicker)
      ? initialTicker
      : stocks[0]?.ticker || ""
  );
  const stock = stocks.find(s => s.ticker === selectedTicker) || stocks[0];

  // Criteria state: track which criteria are toggled met
  const [criteriaState, setCriteriaState] = useState<Record<string, Set<string>>>({});

  const toggleCriterion = (stockTicker: string, criterionId: string) => {
    setCriteriaState(prev => {
      const next = { ...prev };
      const set = new Set(prev[stockTicker] || []);
      if (set.has(criterionId)) set.delete(criterionId);
      else set.add(criterionId);
      next[stockTicker] = set;
      return next;
    });
  };

  // Price-target horizon (12/24/36 months forward)
  const [priceHorizonMonths, setPriceHorizonMonths] = useState<12 | 24 | 36>(12);

  // Pipeline
  const { pipelineRunning, pipelineMsg, runPipeline } = usePipeline();

  // Check if this specific stock has quant data AND meaningful analysis
  // NOTE: stock can be undefined if all stocks are deleted — guard downstream,
  // but do NOT early-return here (all hooks must be called unconditionally).
  const hasQuant = stock ? (stock.currentPrice > 0 || stock.marketCapB > 0) : false;
  const hasAnalysis = stock ? !!(stock.sector && stock.sector !== "Unknown" && stock.thesis && !stock.thesis.includes("pipeline will generate")) : false;
  const stockHasData = hasQuant && hasAnalysis;

  // Detect valuation method — initial guess from stock data (may be overridden by engine)
  const baseValMethodInfo = useMemo(() => {
    if (!stock) return { method: "pe" as const, label: "", multipleLabel: "", justification: "", reasons: [] };
    // If stock has cyclical archetype, start with cyclical assumption
    if (stock.archetype?.primary === "cyclical") return cyclicalMethodInfo(stock.ticker);
    return detectValuationMethod(stock);
  }, [stock]);

  // Derive initial values
  const target = stock?.target || {} as StockTarget;
  const defaults = target.model_defaults;

  const currentRevB = stock?.psRatio && stock.psRatio > 0
    ? stock.marketCapB / stock.psRatio
    : (stock?.marketCapB && stock.marketCapB > 0 ? stock.marketCapB / 5 : 1);
  const initialSharesM = stock?.marketCapB && stock.marketCapB > 0 && stock.currentPrice > 0
    ? (stock.marketCapB * 1000) / stock.currentPrice
    : 200;

  const defaultRevenue = defaults?.revenue_b
    || (currentRevB > 0 ? Math.round(currentRevB * 10) / 10 : 1);
  const defaultOpMargin = defaults?.op_margin
    ?? (stock?.operatingMarginPct !== 0 ? (stock?.operatingMarginPct || 0) / 100 : 0.15);
  const defaultTaxRate = defaults?.tax_rate ?? 0.17;
  const defaultSharesM = defaults?.shares_m || Math.round(initialSharesM);

  const defaultMultiple = baseValMethodInfo.method === "cyclical"
    ? 12 // default through-cycle EV/EBIT — will be overridden by engine
    : baseValMethodInfo.method === "ps"
    ? (defaults?.ps_multiple || (stock?.psRatio && stock.psRatio > 0 ? Math.round(stock.psRatio) : 10))
    : (defaults?.pe_multiple || target.target_multiple || (stock?.forwardPe && stock.forwardPe > 0 ? Math.round(stock.forwardPe) : 20));

  // State: Model Variables
  const [revenue, setRevenue] = useState(defaultRevenue);
  const [opMargin, setOpMargin] = useState(defaultOpMargin);
  const [taxRate, setTaxRate] = useState(defaultTaxRate);
  const [sharesM, setSharesM] = useState(defaultSharesM);
  const [multiple, setMultiple] = useState(defaultMultiple);

  // Gordon Model (only relevant for P/E)
  const [reqReturn, setReqReturn] = useState(0.10);
  const [termGrowth, setTermGrowth] = useState(0.05);

  // Time path
  const currentMultiple = baseValMethodInfo.method === "cyclical"
    ? defaultMultiple // cyclical: start at the through-cycle multiple
    : baseValMethodInfo.method === "ps"
    ? (stock?.psRatio && stock.psRatio > 0 ? Math.round(stock.psRatio) : defaultMultiple)
    : (stock?.forwardPe && stock.forwardPe > 0 ? Math.round(stock.forwardPe) : Math.round(defaultMultiple * 1.5));
  const [startMultiple, setStartMultiple] = useState(currentMultiple);
  const [endMultiple, setEndMultiple] = useState(defaultMultiple);

  // Scenarios
  const stockScenarios = target.scenarios;
  const [bearProb] = useState(stockScenarios?.bear?.probability ?? 0.2);
  const [baseProb] = useState(stockScenarios?.base?.probability ?? 0.5);
  const [bullProb] = useState(stockScenarios?.bull?.probability ?? 0.25);

  // Engine payload hook
  const { enginePayload, engineLoading, engineError } = useEnginePayload(
    selectedTicker,
    priceHorizonMonths,
    baseValMethodInfo,
    defaultOpMargin,
    defaultTaxRate,
    defaultMultiple,
    setRevenue,
    setOpMargin,
    setSharesM,
    setMultiple,
  );

  // Final valuation method: engine may confirm/override cyclical mode
  const valMethodInfo = useMemo(() => {
    if (enginePayload?.target?.valuation_method === "cyclical_normalized" && stock) {
      return cyclicalMethodInfo(stock.ticker);
    }
    return baseValMethodInfo;
  }, [enginePayload, baseValMethodInfo, stock]);

  // Net debt for cyclical EV-to-equity bridge
  const netDebtB = useMemo(() => {
    if (enginePayload?.capitalization?.net_debt) return enginePayload.capitalization.net_debt / 1e9;
    if (enginePayload?.target?.net_debt) return enginePayload.target.net_debt / 1e9;
    return 0;
  }, [enginePayload]);

  // Cycle position (for display)
  const cyclePosition = useMemo(() => {
    return enginePayload?.target?.drivers?.cycle_position ?? 0.5;
  }, [enginePayload]);

  // Derived
  const targetPrice = useMemo(
    () => {
      if (valMethodInfo.method === "cyclical") {
        return computeTargetPriceCyclical(revenue, opMargin, multiple, sharesM, netDebtB);
      }
      if (valMethodInfo.method === "ps") {
        return computeTargetPricePS(revenue, sharesM, multiple);
      }
      return computeTargetPrice(revenue, opMargin, taxRate, sharesM, multiple);
    },
    [revenue, opMargin, taxRate, sharesM, multiple, valMethodInfo.method, netDebtB]
  );

  // Scenario prices
  const engineBase = enginePayload?.target.base;
  const engineLow = enginePayload?.target.low;
  const engineHigh = enginePayload?.target.high;
  const configTargetPrice = engineBase && engineBase > 0 ? engineBase : (target.price || 0);

  const bearPrice = useMemo(() => {
    if (engineLow && engineLow > 0) return Math.round(engineLow);
    const storedBear = stockScenarios?.bear?.price || 0;
    if (storedBear > 0 && configTargetPrice > 0) {
      const ratio = storedBear / configTargetPrice;
      return Math.round(targetPrice * ratio);
    }
    return Math.round(targetPrice * 0.4);
  }, [engineLow, stockScenarios, configTargetPrice, targetPrice]);

  const bullPrice = useMemo(() => {
    if (engineHigh && engineHigh > 0) return Math.round(engineHigh);
    const storedBull = stockScenarios?.bull?.price || 0;
    if (storedBull > 0 && configTargetPrice > 0) {
      const ratio = storedBull / configTargetPrice;
      const safeRatio = Math.max(ratio, 1.1);
      return Math.round(targetPrice * safeRatio);
    }
    return Math.round(targetPrice * 1.5);
  }, [engineHigh, stockScenarios, configTargetPrice, targetPrice]);

  const timeline = target.timeline_years || 3;
  const growthRate = (stock?.revenueGrowthPct || 0) / 100 || 0.20;

  // Criteria with met state
  const enrichedCriteria = useMemo(() => {
    const metSet = criteriaState[stock?.ticker || ""] || new Set();
    return (stock?.criteria || []).map(c => {
      const manuallyMet = metSet.has(c.id);
      const autoMet = c.evaluation_note ? c.status === "met" : false;
      return { ...c, met: manuallyMet || autoMet };
    });
  }, [stock?.criteria, stock?.ticker, criteriaState]);

  // Sensitivity
  const sens = useMemo(
    () => buildSensitivityMatrix(revenue, opMargin, taxRate, sharesM, multiple, valMethodInfo.method, netDebtB),
    [revenue, opMargin, taxRate, sharesM, multiple, valMethodInfo.method, netDebtB]
  );

  // Time path
  const timePath = useMemo(
    () => buildTimePath(revenue, growthRate, opMargin, taxRate, sharesM, startMultiple, endMultiple, timeline, valMethodInfo.method),
    [revenue, growthRate, opMargin, taxRate, sharesM, startMultiple, endMultiple, timeline, valMethodInfo.method]
  );

  // Stock change handler
  const handleStockChange = (ticker: string) => {
    setSelectedTicker(ticker);
    const s = stocks.find(st => st.ticker === ticker);
    if (s) {
      const st = s.target || {} as StockTarget;
      const d = st.model_defaults;
      const vm = s.archetype?.primary === "cyclical" ? cyclicalMethodInfo(s.ticker) : detectValuationMethod(s);

      const revB = d?.revenue_b || (s.psRatio > 0 ? s.marketCapB / s.psRatio : s.marketCapB / 10);
      setRevenue(revB > 0 ? Math.round(revB * 10) / 10 : 1);

      const shM = d?.shares_m || (s.marketCapB > 0 && s.currentPrice > 0 ? (s.marketCapB * 1000) / s.currentPrice : 200);
      setSharesM(Math.round(shM));

      setOpMargin(d?.op_margin ?? (s.operatingMarginPct !== 0 ? s.operatingMarginPct / 100 : 0.15));
      setTaxRate(d?.tax_rate ?? 0.17);

      const defaultM = vm.method === "cyclical"
        ? 12
        : vm.method === "ps"
        ? (d?.ps_multiple || (s.psRatio > 0 ? Math.round(s.psRatio) : 10))
        : (d?.pe_multiple || st.target_multiple || (s.forwardPe > 0 ? Math.round(s.forwardPe) : 20));
      setMultiple(defaultM);

      const curM = vm.method === "cyclical"
        ? defaultM
        : vm.method === "ps"
        ? (s.psRatio > 0 ? Math.round(s.psRatio) : defaultM)
        : (s.forwardPe > 0 ? Math.round(s.forwardPe) : Math.round(defaultM * 1.5));
      setStartMultiple(curM);
      setEndMultiple(defaultM);
    }
  };

  // Theme toggle
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    const saved = localStorage.getItem("sr-theme");
    if (saved === "light") {
      setTheme("light");
      document.documentElement.setAttribute("data-theme", "light");
    }
  }, []);
  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next === "dark" ? "" : "light");
    window.localStorage.setItem("sr-theme", next);
  };

  // ── Early return for empty state (AFTER all hooks to satisfy Rules of Hooks) ──
  if (!stock) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        <div className="text-center">
          <div className="text-4xl mb-4">📐</div>
          <div className="text-lg mb-2">No stock data available</div>
          <div className="text-sm mb-4">Run the pipeline first to generate data.</div>
          <button
            onClick={() => runPipeline(false)}
            disabled={pipelineRunning}
            className="px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-sm hover:bg-white/20 transition-all disabled:opacity-50"
          >
            {pipelineRunning ? "Running..." : "Run Pipeline"}
          </button>
          {pipelineMsg && <div className="mt-3 text-xs text-gray-400">{pipelineMsg}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      {/* Header */}
      <header className="border-b border-[var(--border)] bg-[var(--bg-elevated)]">
        <div className="max-w-[1000px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <a href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
              <div className="w-7 h-7 rounded-md bg-[var(--text)] flex items-center justify-center text-[11px] font-bold text-[var(--bg)]">SR</div>
              <div>
                <h1 className="text-[15px] font-semibold text-[var(--text)]">Target Price Model</h1>
                <p className="text-[10px] text-[var(--muted)]">Reverse-Valuation Framework</p>
              </div>
            </a>
            <nav className="flex gap-4 text-xs">
              <a href="/" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Watchlist</a>
              <a href="/discovery" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Discovery</a>
              <span className="text-amber-500 font-medium">Models</span>
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={toggleTheme}
              className="text-[var(--muted)] hover:text-[var(--text)] transition-colors p-1.5 rounded-md hover:bg-[var(--hover)]"
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            >
              {theme === "dark" ? (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.5"/><path d="M8 1.5v1M8 13.5v1M1.5 8h1M13.5 8h1M3.4 3.4l.7.7M11.9 11.9l.7.7M3.4 12.6l.7-.7M11.9 4.1l.7-.7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M13.5 9.2A5.5 5.5 0 016.8 2.5a6 6 0 106.7 6.7z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              )}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1000px] mx-auto px-6 py-8">
        {/* Stock selector */}
        <div className="flex items-center gap-1.5 mb-6 flex-wrap">
          {stocks.map(s => (
            <button
              key={s.ticker}
              onClick={() => handleStockChange(s.ticker)}
              className={cn(
                "px-3.5 py-1.5 rounded-md border text-[13px] font-mono font-medium transition-all",
                selectedTicker === s.ticker
                  ? "bg-[var(--text)] border-[var(--text)] text-[var(--bg)]"
                  : "bg-[var(--card)] border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)] hover:border-[var(--border-hover)]"
              )}
            >
              {s.ticker}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2 text-xs text-[var(--muted)]">
            {stock.name} &middot; {stock.sector}
            {/* Archetype badge — from Supabase (set by generate_model.py) or engine payload */}
            {(stock.archetype?.primary || enginePayload?.archetype?.primary) && (() => {
              const arch = stock.archetype?.primary || enginePayload?.archetype?.primary || "";
              const labels: Record<string, string> = {
                garp: "GARP",
                cyclical: "Cyclical",
                transformational: "Transformational",
                compounder: "Compounder",
                special_situation: "Special Sit.",
              };
              const colors: Record<string, string> = {
                garp: "bg-blue-500/20 text-blue-300 border-blue-500/30",
                cyclical: "bg-amber-500/20 text-amber-300 border-amber-500/30",
                transformational: "bg-violet-500/20 text-violet-300 border-violet-500/30",
                compounder: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
                special_situation: "bg-rose-500/20 text-rose-300 border-rose-500/30",
              };
              return (
                <span className={cn("px-2 py-0.5 rounded-full border text-[10px] font-medium", colors[arch] || "bg-gray-500/20 text-gray-300 border-gray-500/30")}>
                  {labels[arch] || arch}
                </span>
              );
            })()}
            {/* Valuation method badge from engine */}
            {enginePayload?.target?.valuation_method && enginePayload.target.valuation_method !== "ev_ebitda" && (
              <span className="px-2 py-0.5 rounded-full border text-[10px] font-medium bg-cyan-500/20 text-cyan-300 border-cyan-500/30">
                {enginePayload.target.valuation_method === "cyclical_normalized" ? "Cyclical Engine"
                  : enginePayload.target.valuation_method === "revenue_multiple" ? "P/S Mode"
                  : enginePayload.target.valuation_method}
              </span>
            )}
          </div>
        </div>

        {/* Thesis */}
        {stock.thesis && (
          <div className="mb-8 text-[13px] text-[var(--secondary)] leading-relaxed">
            <span className="text-[var(--text)] font-medium">Thesis: </span>
            {stock.thesis}
          </div>
        )}

        {/* MODEL SOURCES */}
        {stock.researchCache?.generated_at && (
          <div className="mb-6 flex items-center gap-3 text-[11px] text-[var(--muted)] bg-[var(--card)] border border-[var(--border)] rounded-lg px-4 py-2.5">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="flex-shrink-0 opacity-60">
              <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M8 4.5v4M8 10.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <span>
              Model generated{" "}
              <span className="text-[var(--secondary)] font-medium">
                {new Date(stock.researchCache.generated_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
              {stock.researchCache.sources && stock.researchCache.sources.length > 0 && (
                <>
                  {" "}using{" "}
                  <span className="text-[var(--secondary)]">
                    {stock.researchCache.sources.join(", ")}
                  </span>
                </>
              )}
              {stock.researchCache.quant_snapshot?.price && (
                <>
                  {" "}\u00B7 Quant price at generation:{" "}
                  <span className="font-mono text-[var(--secondary)]">
                    ${stock.researchCache.quant_snapshot.price.toFixed(2)}
                  </span>
                </>
              )}
            </span>
          </div>
        )}

        {/* NO DATA STATE */}
        {!stockHasData && (
          <div className="rounded-xl border-2 border-dashed border-[var(--border)] p-12 mb-8 text-center">
            <div className="text-4xl mb-4">📐</div>
            <div className="text-lg font-medium text-[var(--text)] mb-2">
              No analysis data for {stock.ticker}
            </div>
            <div className="text-sm text-[var(--muted)] mb-6 max-w-md mx-auto">
              {hasQuant && !hasAnalysis
                ? `${stock.ticker} has market data but no analysis yet. Run the pipeline or rebuild analysis to generate thesis, valuation, and target price model.`
                : "The pipeline hasn\u2019t been run for this stock yet. Run the pipeline to fetch quant data, news, and generate the full target price model."
              }
            </div>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => runPipeline(false)}
                disabled={pipelineRunning}
                className={cn(
                  "px-5 py-2.5 rounded-lg text-sm font-medium transition-all",
                  pipelineRunning
                    ? "bg-[var(--hover)] border border-[var(--border)] text-[var(--muted)]"
                    : "bg-[var(--text)] text-[var(--bg)] hover:opacity-90"
                )}
              >
                {pipelineRunning ? (
                  <span className="flex items-center gap-2">
                    <span className="w-3 h-3 border-[1.5px] border-[var(--bg)] border-t-transparent rounded-full animate-spin" />
                    Running...
                  </span>
                ) : "Run Full Pipeline"}
              </button>
              <button
                onClick={() => runPipeline(true)}
                disabled={pipelineRunning}
                className="px-4 py-2.5 rounded-lg border border-[var(--border)] text-sm text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--hover)] transition-all disabled:opacity-40"
              >
                Free scouts only
              </button>
            </div>
            {pipelineMsg && (
              <div className="mt-4 text-xs text-[var(--secondary)]">
                {pipelineRunning && (
                  <span className="inline-block w-3 h-3 border-[1.5px] border-[var(--text)] border-t-transparent rounded-full animate-spin mr-2 align-middle" />
                )}
                {pipelineMsg}
              </div>
            )}
          </div>
        )}

        {/* FULL MODEL (only when data is available) */}
        {stockHasData && (<>

        {/* VALUATION METHOD JUSTIFICATION */}
        <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-5 mb-6">
          <div className="flex items-center gap-3 mb-3 flex-wrap">
            <span className={cn(
              "px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold",
              valMethodInfo.method === "pe"
                ? "bg-emerald-400/10 text-emerald-400 border border-emerald-400/20"
                : "bg-[#60a5fa]/10 text-[#60a5fa] border border-[#60a5fa]/20"
            )}>
              {valMethodInfo.label}
            </span>
            <span className="text-[11px] text-[var(--muted)]">Auto-selected for {stock.ticker}</span>
            {engineLoading && (
              <span className="text-[10px] text-[var(--faint)] flex items-center gap-1.5">
                <span className="w-2 h-2 border border-[var(--faint)] border-t-transparent rounded-full animate-spin" />
                Loading engine target...
              </span>
            )}
            {engineError && !enginePayload && (
              <span className="text-[10px] text-amber-500">
                Engine unavailable \u2014 showing pipeline-derived defaults
              </span>
            )}
            {/* Detailed-view link */}
            <a
              href={`/model/${selectedTicker}/detailed`}
              className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-400/10 border border-emerald-400/30 text-emerald-400 hover:bg-emerald-400/20 hover:border-emerald-400/50 transition-all text-[11px] font-semibold"
              title="Open the full workbook (P&L, Income Statement, Cash Flow, Valuation, Capitalization)"
            >
              <span>📊</span>
              <span>Detailed Model</span>
              {enginePayload && (
                <span className="font-mono opacity-70">\u00B7 base ${Math.round(enginePayload.target.base)}</span>
              )}
              <span>\u2192</span>
            </a>
          </div>
          <p className="text-[13px] text-[var(--secondary)] leading-relaxed mb-3">{valMethodInfo.justification}</p>
          <div className="space-y-1.5">
            {valMethodInfo.reasons.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-[11px] text-[var(--muted)]">
                <span className="mt-0.5 w-1 h-1 rounded-full bg-[var(--muted)] flex-shrink-0" />
                {r}
              </div>
            ))}
          </div>
          {valMethodInfo.method === "cyclical" && (
            <div className="mt-3 text-[10px] text-[var(--faint)] border-t border-[var(--border)] pt-3">
              Equation: EV = Revenue \u00D7 Normalized EBIT Margin \u00D7 EV/EBIT \u2192 Equity = EV \u2212 Net Debt \u2192 Price = Equity / Shares
            </div>
          )}
          {valMethodInfo.method === "ps" && (
            <div className="mt-3 text-[10px] text-[var(--faint)] border-t border-[var(--border)] pt-3">
              Equation: Target Price = (Revenue / Diluted Shares) \u00D7 P/S Multiple
            </div>
          )}
          {valMethodInfo.method === "pe" && (
            <div className="mt-3 text-[10px] text-[var(--faint)] border-t border-[var(--border)] pt-3">
              Equation: Target Price = (Revenue \u00D7 Op Margin \u00D7 (1 \u2212 Tax Rate)) / Diluted Shares \u00D7 P/E Multiple
            </div>
          )}
        </div>

        {/* HORIZON SELECTOR */}
        <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] px-6 py-4 mb-4">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-[var(--faint)] mb-1">
                Price target horizon
              </div>
              <div className="text-[15px] font-semibold text-[var(--text)]">
                {priceHorizonMonths} months forward
                {enginePayload?.target.price_target_date && (
                  <span className="text-[13px] font-normal text-[var(--muted)] ml-2">
                    (\u2248 {enginePayload.target.price_target_date})
                  </span>
                )}
              </div>
              <div className="text-[11px] text-[var(--muted)] mt-0.5">
                Exit fundamentals anchored at Y3
                {enginePayload?.target.exit_fiscal_year &&
                  ` (${enginePayload.target.exit_fiscal_year})`}
                {" "}\u2014 only the discount back to today changes with horizon.
              </div>
            </div>
            <div className="inline-flex rounded-md border border-[var(--border)] overflow-hidden">
              {([12, 24, 36] as const).map((h) => (
                <button
                  key={h}
                  onClick={() => setPriceHorizonMonths(h)}
                  className={cn(
                    "px-4 py-2 text-[12px] font-medium transition-colors",
                    priceHorizonMonths === h
                      ? "bg-emerald-500 text-white"
                      : "bg-[var(--card)] text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--card-hover,#1f1f24)]"
                  )}
                >
                  {h}mo
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* SLIDERS */}
        <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] px-6 py-4 mb-8">
          <div className="text-[13px] text-[var(--muted)] mb-2">
            {valMethodInfo.method === "cyclical"
              ? "Normalized mid-cycle fundamentals (Damodaran approach) \u2014 adjust sliders or click values to type"
              : `Y3 exit fundamentals (FY${2026 + timeline}) \u2014 adjust sliders or click values to type`}
          </div>
          {valMethodInfo.method === "cyclical" ? (
            <>
              <SliderRow label="Annual revenue" value={revenue} onChange={setRevenue}
                min={Math.max(0.5, Math.round(currentRevB * 0.3 * 10) / 10)}
                max={Math.max(Math.round(currentRevB * 5), 10)} step={0.1}
                format={v => `$${v.toFixed(1)}B`} />
              <SliderRow label="Normalized EBIT margin (mid-cycle avg)" value={opMargin} onChange={setOpMargin}
                min={-0.10} max={0.60} step={0.01}
                format={v => `${(v * 100).toFixed(1)}%`} />
              <SliderRow
                label="Through-cycle EV/EBIT"
                value={multiple}
                onChange={setMultiple}
                min={4}
                max={40}
                step={1}
                format={v => `${v}\u00D7`}
              />
              <SliderRow label="Diluted shares" value={sharesM} onChange={setSharesM}
                min={Math.round(initialSharesM * 0.7)} max={Math.round(initialSharesM * 1.5)} step={1}
                format={v => `${v.toFixed(0)}M`} />
              {/* Cycle position indicator (read-only display from engine) */}
              <div className="flex items-center justify-between py-2 text-[12px]">
                <span className="text-[var(--muted)]">Cycle position</span>
                <div className="flex items-center gap-2">
                  <div className="w-32 h-2 rounded-full bg-[var(--bg)] overflow-hidden relative">
                    <div
                      className="absolute top-0 left-0 h-full rounded-full transition-all"
                      style={{
                        width: `${cyclePosition * 100}%`,
                        background: cyclePosition > 0.7 ? '#f59e0b' : cyclePosition < 0.3 ? '#3b82f6' : '#10b981',
                      }}
                    />
                  </div>
                  <span className="font-mono text-[var(--secondary)]">
                    {cyclePosition < 0.3 ? 'Trough' : cyclePosition > 0.7 ? 'Peak' : 'Mid-cycle'}
                    {' '}({(cyclePosition * 100).toFixed(0)}%)
                  </span>
                </div>
              </div>
              {netDebtB !== 0 && (
                <div className="flex items-center justify-between py-2 text-[12px]">
                  <span className="text-[var(--muted)]">Net debt</span>
                  <span className="font-mono text-[var(--secondary)]">
                    ${netDebtB.toFixed(1)}B
                  </span>
                </div>
              )}
            </>
          ) : (
            <>
              <SliderRow label="Annual revenue" value={revenue} onChange={setRevenue}
                min={Math.max(0.5, Math.round(currentRevB * 0.3 * 10) / 10)}
                max={Math.max(Math.round(currentRevB * 5), 10)} step={0.1}
                format={v => `$${v.toFixed(1)}B`} />
              {valMethodInfo.method === "pe" && (
                <>
                  <SliderRow label="Operating margin" value={opMargin} onChange={setOpMargin}
                    min={-0.10} max={0.60} step={0.01}
                    format={v => `${(v * 100).toFixed(0)}%`} />
                  <SliderRow label="Tax rate" value={taxRate} onChange={setTaxRate}
                    min={0} max={0.40} step={0.01}
                    format={v => `${(v * 100).toFixed(0)}%`} />
                </>
              )}
              <SliderRow label="Diluted shares" value={sharesM} onChange={setSharesM}
                min={Math.round(initialSharesM * 0.7)} max={Math.round(initialSharesM * 1.5)} step={1}
                format={v => `${v.toFixed(1)}M`} />
              <SliderRow
                label={valMethodInfo.multipleLabel}
                value={multiple}
                onChange={setMultiple}
                min={valMethodInfo.method === "ps" ? 1 : 5}
                max={valMethodInfo.method === "ps" ? 50 : 100}
                step={1}
                format={v => `${v}\u00D7`}
              />
            </>
          )}
        </div>

        {/* IMPLIED TARGET PRICE */}
        <div className="mb-8">
          <ImpliedTargetBox
            impliedPrice={targetPrice}
            thesisTarget={configTargetPrice}
            currentPrice={stock.currentPrice}
            loading={engineLoading}
          />
        </div>

        {/* DEDUCTION CHAIN */}
        <div className="mb-8">
          <div className="text-sm text-[var(--secondary)] mb-3">
            The deduction chain {valMethodInfo.method === "cyclical" ? "(normalized EV/EBIT)" : valMethodInfo.method === "ps" ? "(revenue-based)" : "(earnings-based)"}
          </div>
          <DeductionChain
            revenueB={revenue}
            opMargin={opMargin}
            taxRate={taxRate}
            sharesM={sharesM}
            multiple={multiple}
            targetPrice={targetPrice}
            method={valMethodInfo.method}
            netDebtB={netDebtB}
          />
        </div>

        {/* SENSITIVITY TABLE */}
        <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-6 mb-8">
          <SensitivityTable
            revenues={sens.revenues}
            multiples={sens.multiples}
            matrix={sens.matrix}
            targetPrice={configTargetPrice || targetPrice}
            currentPrice={stock.currentPrice}
            baseRevIdx={sens.baseRevIdx}
            baseMIdx={sens.baseMIdx}
            opMargin={opMargin}
            taxRate={taxRate}
            sharesM={sharesM}
            method={valMethodInfo.method}
            multipleLabel={valMethodInfo.multipleLabel}
          />
        </div>

        {/* GORDON GROWTH MODEL (P/E only) */}
        {valMethodInfo.method === "pe" && (
          <div className="mb-8">
            <div className="text-[13px] text-[var(--muted)] mb-3">P/E multiple derivation</div>
            <GordonModel
              reqReturn={reqReturn}
              termGrowth={termGrowth}
              onChangeR={setReqReturn}
              onChangeG={setTermGrowth}
              onApply={setMultiple}
            />
          </div>
        )}

        {/* TIME PATH */}
        <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-6 mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="text-[13px] text-[var(--muted)]">
              Price path \u2014 {timeline}yr projection with {valMethodInfo.multipleLabel} {startMultiple > endMultiple ? "compression" : "expansion"}
            </div>
            <div className="flex items-center gap-4 text-xs text-[var(--muted)]">
              <div className="flex items-center gap-2">
                <span>Start {valMethodInfo.multipleLabel.split(" ").pop()}:</span>
                <input type="number" value={startMultiple} onChange={e => setStartMultiple(Number(e.target.value))}
                  className="w-14 px-2 py-1 bg-[var(--bg)] border border-[var(--border)] rounded text-[var(--text)] font-mono text-xs text-center" />
              </div>
              <div className="flex items-center gap-2">
                <span>End {valMethodInfo.multipleLabel.split(" ").pop()}:</span>
                <input type="number" value={endMultiple} onChange={e => setEndMultiple(Number(e.target.value))}
                  className="w-14 px-2 py-1 bg-[var(--bg)] border border-[var(--border)] rounded text-[var(--text)] font-mono text-xs text-center" />
              </div>
            </div>
          </div>
          <TimePathChart path={timePath} currentPrice={stock.currentPrice} targetPrice={configTargetPrice || targetPrice} multipleLabel={valMethodInfo.multipleLabel} />
          <div className="mt-3 text-[10px] text-[var(--muted)]">
            Revenue compounds at {(growthRate * 100).toFixed(0)}% CAGR. {valMethodInfo.multipleLabel} {startMultiple > endMultiple ? "compresses" : "expands"} {startMultiple}\u00D7 \u2192 {endMultiple}\u00D7 over {timeline}yr.
          </div>
        </div>

        {/* SCENARIOS */}
        <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-6 mb-8">
          <div className="text-[13px] text-[var(--muted)] mb-4">Scenario analysis</div>
          <ScenarioSection
            targetPrice={targetPrice}
            currentPrice={stock.currentPrice}
            bearProb={bearProb}
            baseProb={baseProb}
            bullProb={bullProb}
            bearPrice={bearPrice}
            bullPrice={bullPrice}
          />
        </div>

        {/* ENGINE WARNINGS */}
        {enginePayload?.warnings && enginePayload.warnings.length > 0 && (
          <div className="rounded-xl bg-yellow-500/10 border border-yellow-500/30 p-4 mb-8">
            <div className="flex items-start gap-2">
              <span className="text-yellow-400 text-sm mt-0.5">\u26A0</span>
              <div>
                <div className="text-[13px] text-yellow-300 font-medium mb-1">Engine warnings</div>
                {enginePayload.warnings.map((w, i) => (
                  <div key={i} className="text-[11px] text-yellow-200/80 leading-relaxed">{w}</div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* CRITERIA CHECKLIST + CONFIDENCE */}
        {enrichedCriteria.length > 0 && (
          <div className="mb-8">
            <div className="mb-4">
              <div className="text-[13px] text-[var(--muted)]">Criteria checklist</div>
              <div className="text-[10px] text-[var(--faint)] mt-1">
                Click checkboxes to toggle. Expand rows for progress and news.
              </div>
            </div>
            <div className="grid grid-cols-12 gap-6">
              <div className="col-span-7">
                <CriteriaChecklist
                  criteria={enrichedCriteria}
                  onToggle={(id) => toggleCriterion(stock.ticker, id)}
                  targetPrice={targetPrice}
                />
              </div>
              <div className="col-span-5">
                <ConfidenceMeter criteria={enrichedCriteria} targetPrice={targetPrice} />
              </div>
            </div>
          </div>
        )}

        {/* EVENT IMPACTS (Phase 1 audit-only) */}
        {stock.eventImpacts && (() => {
          let critAdjPct = 0;
          for (const c of enrichedCriteria) {
            const pct = c.price_impact_pct || 0;
            if (c.price_impact_direction === "down_if_failed") {
              if (c.status === "failed" && !c.met) critAdjPct -= Math.abs(pct);
            } else if (c.met) {
              critAdjPct += pct;
            }
          }
          const baseForEvents = configTargetPrice || targetPrice;
          const criteriaAdjustedTarget = Math.round(baseForEvents * (1 + critAdjPct / 100));
          return (
            <div className="mb-8">
              <EventImpactsPanel
                impacts={stock.eventImpacts}
                criteriaAdjustedTarget={criteriaAdjustedTarget}
                ticker={stock.ticker}
              />
            </div>
          );
        })()}

        {/* AUTO TIERS */}
        {stock.autoTiers && stock.autoTiers.length > 0 && (
          <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-6 mb-8">
            <div className="text-[13px] text-[var(--muted)] mb-4">Return multiples</div>
            <div className="grid grid-cols-3 gap-3">
              {stock.autoTiers.map((tier: any) => (
                <div key={tier.tier} className="p-4 rounded-lg bg-[var(--bg)] border border-[var(--border)]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-lg font-mono font-bold text-[var(--text)]">{tier.tier}</span>
                    <span className="text-[10px] text-[var(--muted)] font-mono">{tier.feasibility}</span>
                  </div>
                  <div className="text-base font-mono text-[var(--secondary)]">${tier.target_price?.toLocaleString()}</div>
                  <div className="text-[10px] text-[var(--muted)] mt-1">
                    {tier.required_cagr_pct}% CAGR
                    {tier.required_revenue_b && ` \u2192 $${tier.required_revenue_b}B`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Kill condition */}
        {stock.killCondition && (() => {
          const kEval = stock.killConditionEval;
          const kStatus = kEval?.status || "unchecked";
          const statusBadge = kStatus === "triggered"
            ? { label: "THESIS BREAK", cls: "bg-red-500/20 text-red-400 border-red-500/40" }
            : kStatus === "warning"
            ? { label: "WATCH", cls: "bg-yellow-500/20 text-yellow-400 border-yellow-500/40" }
            : kStatus === "safe"
            ? { label: "SAFE", cls: "bg-green-500/15 text-green-400 border-green-500/30" }
            : null;
          return (
            <div className={cn("rounded-lg border p-4 mb-8",
              kStatus === "triggered" ? "bg-red-500/10 border-red-500/30" :
              kStatus === "warning" ? "bg-yellow-500/10 border-yellow-500/30" :
              "bg-[var(--danger-bg)] border-[var(--danger)]/15"
            )}>
              <div className="flex items-center justify-between mb-1">
                <div className="text-xs text-[var(--danger)] font-medium">Kill condition</div>
                {statusBadge && (
                  <span className={cn("text-[9px] px-1.5 py-0.5 rounded border font-mono", statusBadge.cls)}>
                    {statusBadge.label}
                  </span>
                )}
              </div>
              <div className="text-[13px] text-[var(--secondary)]">{stock.killCondition}</div>
              {kEval?.reasoning && kStatus !== "safe" && (
                <div className="text-[11px] text-[var(--muted)] mt-2 italic">{kEval.reasoning}</div>
              )}
              {kEval?.evidence && kEval.evidence.length > 0 && kStatus !== "safe" && (
                <div className="mt-2 space-y-0.5">
                  {kEval.evidence.map((e, i) => (
                    <div key={i} className="text-[10px] text-[var(--faint)] pl-2 border-l-2 border-[var(--border)]">{e}</div>
                  ))}
                </div>
              )}
              {kEval?.checked_at && (
                <div className="text-[9px] text-[var(--faint)] mt-2 font-mono">
                  Last checked: {new Date(kEval.checked_at).toLocaleDateString()}
                </div>
              )}
            </div>
          );
        })()}

        </>)}
        {/* END FULL MODEL CONDITIONAL */}

        {/* Footer */}
        <footer className="pt-6 border-t border-[var(--border)] text-center text-[10px] text-[var(--muted)]">
          All numbers are model outputs, not predictions \u2014 Not financial advice
        </footer>
      </main>
    </div>
  );
}
