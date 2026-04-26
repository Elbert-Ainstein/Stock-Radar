"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { Stock } from "@/lib/data";
import { inferCurrency } from "@/lib/data";
import type { PipelineProgress, ScoutInfo } from "./types";
import { cn, scoreColor, formatTime } from "./helpers";
import PipelineProgressBar from "./PipelineProgressBar";
import StockRow from "./StockRow";
import StockDetail from "./StockDetail";
import TickerSearch from "./TickerSearch";
import ScoutPanel from "./ScoutPanel";
import SummaryCards from "./SummaryCards";
import HealthPanel from "./HealthPanel";

// ─── Main Dashboard ───

export default function Dashboard({ stocks, meta }: { stocks: Stock[]; meta: { generatedAt: string; scoutsActive: string[]; scoutDetails: ScoutInfo[] } }) {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(stocks[0]?.ticker || null);
  const [sortBy, setSortBy] = useState<"score" | "change" | "convergence">("score");
  const [filterSector, setFilterSector] = useState<string>("all");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    const saved = localStorage.getItem("sr-theme");
    if (saved === "light") {
      setTheme("light");
      document.documentElement.setAttribute("data-theme", "light");
    }
  }, []);
  const [localStocks, setLocalStocks] = useState(stocks);

  // Pipeline state
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineProgress, setPipelineProgress] = useState<PipelineProgress | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Rebuild state (analysis-only recompute — no scout re-run)
  const [rebuildRunning, setRebuildRunning] = useState(false);
  const [rebuildProgress, setRebuildProgress] = useState<PipelineProgress | null>(null);
  const rebuildPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Scout panel
  const [showScoutPanel, setShowScoutPanel] = useState(false);
  const activeScoutCount = meta.scoutDetails.filter(s => s.signalCount > 0).length;
  const totalScoutCount = meta.scoutDetails.length;

  // Feedback loop / scout accuracy
  const [scoutAccuracy, setScoutAccuracy] = useState<any[]>([]);
  const [feedbackLoaded, setFeedbackLoaded] = useState(false);

  // Health panel
  const [showHealthPanel, setShowHealthPanel] = useState(false);

  // Bulk select/delete
  const [selectMode, setSelectMode] = useState(false);
  const [selectedTickers, setSelectedTickers] = useState<Set<string>>(new Set());

  const toggleCheck = (ticker: string) => {
    setSelectedTickers(prev => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  };
  const selectAll = () => setSelectedTickers(new Set(sorted.map(s => s.ticker)));
  const selectNone = () => setSelectedTickers(new Set());

  const handleBulkDelete = async () => {
    if (selectedTickers.size === 0) return;
    const names = [...selectedTickers].join(", ");
    if (!confirm(`Remove ${selectedTickers.size} stocks?\n\n${names}`)) return;
    try {
      const res = await fetch("/api/stocks/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tickers: [...selectedTickers] }),
      });
      if (res.ok) {
        setLocalStocks(prev => prev.filter(s => !selectedTickers.has(s.ticker)));
        if (selectedTicker && selectedTickers.has(selectedTicker)) {
          setSelectedTicker(localStocks.find(s => !selectedTickers.has(s.ticker))?.ticker || null);
        }
        setSelectedTickers(new Set());
        setSelectMode(false);
      }
    } catch (err) {
      console.error("Bulk delete failed:", err);
    }
  };

  // ─── Poll pipeline status ───
  const startPolling = useCallback(() => {
    if (pollRef.current) return; // already polling
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch("/api/pipeline");
        const status = await res.json();
        if (status.running) {
          setPipelineRunning(true);
          if (status.progress) setPipelineProgress(status.progress);
        } else {
          // Pipeline finished
          setPipelineRunning(false);
          setPipelineProgress(null);
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          // Reload to get fresh data
          window.location.reload();
        }
      } catch {}
    }, 3000);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // On mount: check if pipeline is already running
  useEffect(() => {
    const checkInitialState = async () => {
      try {
        const res = await fetch("/api/pipeline");
        const status = await res.json();
        if (status.running) {
          setPipelineRunning(true);
          if (status.progress) setPipelineProgress(status.progress);
          startPolling();
        }
      } catch {}
    };
    checkInitialState();
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  // Load feedback/accuracy data when scout panel opens
  useEffect(() => {
    if (showScoutPanel && !feedbackLoaded) {
      fetch("/api/feedback")
        .then(res => res.json())
        .then(data => {
          setScoutAccuracy(data.accuracy || []);
          setFeedbackLoaded(true);
        })
        .catch(() => setFeedbackLoaded(true));
    }
  }, [showScoutPanel, feedbackLoaded]);

  // Track whether any stocks have signal data
  const hasData = stocks.length > 0 && stocks.some(s => s.signals.length > 0);
  // NOTE: Auto-run removed. Previously this would auto-trigger a free pipeline
  // when no signal data existed, but after a DB wipe with 50 stocks this caused
  // a surprise 10-15 minute pipeline run. Users should manually click "Run Pipeline".

  const runPipeline = async (freeOnly = false) => {
    if (pipelineRunning) return; // Guard: prevent double-trigger
    setPipelineRunning(true);
    setPipelineError(null);
    setPipelineProgress({ stage: "init", message: "Starting pipeline...", current: 0, total: 1, percent: 0 });
    try {
      const res = await fetch("/api/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ freeOnly }),
      });
      const data = await res.json();
      if (res.status === 409) {
        // Already running — just start polling to track it
        setPipelineRunning(true);
        if (data.progress) setPipelineProgress(data.progress);
        startPolling();
        return;
      }
      if (!res.ok) {
        setPipelineError(data.message || "Failed to start pipeline");
        setPipelineProgress(null);
        setPipelineRunning(false);
        return;
      }
      // Started successfully — begin polling
      startPolling();
    } catch {
      setPipelineError("Could not reach the server. Is it running?");
      setPipelineProgress(null);
      setPipelineRunning(false);
    }
  };

  const stopPipeline = async () => {
    try {
      const res = await fetch("/api/pipeline", { method: "DELETE" });
      const data = await res.json();
      if (res.ok) {
        setPipelineRunning(false);
        setPipelineProgress(null);
        setPipelineError(null);
      } else {
        setPipelineError(data.message || "Failed to stop pipeline");
      }
    } catch {
      setPipelineError("Could not reach the server.");
    }
  };

  const runRebuild = async (ticker?: string) => {
    if (rebuildRunning || pipelineRunning) return;
    setRebuildRunning(true);
    setRebuildProgress({ stage: "init", message: ticker ? `Rebuilding ${ticker}...` : "Rebuilding all...", current: 0, total: 1, percent: 0 });
    try {
      const res = await fetch("/api/rebuild", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: ticker || null }),
      });
      const data = await res.json();
      if (!res.ok) {
        setRebuildRunning(false);
        setRebuildProgress(null);
        return;
      }
      // Poll until done
      rebuildPollRef.current = setInterval(async () => {
        try {
          const r = await fetch("/api/rebuild");
          const s = await r.json();
          if (s.running) {
            if (s.progress) setRebuildProgress(s.progress);
          } else {
            setRebuildRunning(false);
            setRebuildProgress(null);
            if (rebuildPollRef.current) {
              clearInterval(rebuildPollRef.current);
              rebuildPollRef.current = null;
            }
            window.location.reload();
          }
        } catch {}
      }, 2000);
    } catch {
      setRebuildRunning(false);
      setRebuildProgress(null);
    }
  };

  const handleDeleteStock = async (ticker: string) => {
    if (!confirm(`Remove ${ticker} from watchlist?`)) return;
    try {
      const res = await fetch("/api/stocks/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });
      if (res.ok) {
        setLocalStocks(prev => prev.filter(s => s.ticker !== ticker));
        if (selectedTicker === ticker) {
          setSelectedTicker(localStocks.find(s => s.ticker !== ticker)?.ticker || null);
        }
      }
    } catch (err) {
      console.error("Failed to delete stock:", err);
    }
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next === "dark" ? "" : "light");
    window.localStorage.setItem("sr-theme", next);
  };

  const addingRef = useRef<Set<string>>(new Set());
  const handleAddTicker = async (ticker: string, name: string, sector: string) => {
    // Guard against rapid double-clicks adding same ticker twice
    if (addingRef.current.has(ticker)) return;
    if (localStocks.some(s => s.ticker === ticker)) return;
    addingRef.current.add(ticker);

    // Always allow adding — even while pipeline runs
    const newStock: Stock = {
      ticker,
      name,
      sector,
      currency: inferCurrency(ticker),
      price: 0,
      change: 0,
      changePct: 0,
      marketCap: "N/A",
      score: 0,
      scoreDelta: 0,
      scoreHistory: [0],
      signals: [],
      thesis: pipelineRunning
        ? "Queued — will be analyzed when current pipeline finishes."
        : "Added to watchlist — running pipeline...",
      killCondition: "",
      tags: [sector],
      catalysts: [],
      overallSignal: "neutral",
      convergence: { bullish: 0, bearish: 0, neutral: 0, total: 0 },
    };
    setLocalStocks(prev => [...prev, newStock]);
    try {
      const res = await fetch("/api/stocks/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, name, sector }),
      });
      const data = await res.json();
      if (data.success) {
        console.log(`[Stock Radar] ${ticker}: ${data.message} (status: ${data.pipelineStatus})`);
        // If add triggered its own mini-pipeline and nothing was polling yet, start polling
        if (data.pipelineStatus === "running" && !pipelineRunning) {
          setPipelineRunning(true);
          setPipelineProgress({ stage: "quant", message: `Running pipeline for ${ticker}...`, current: 1, total: 4, percent: 25 });
          startPolling();
        }
      }
    } catch (err) {
      console.error("Failed to add stock:", err);
    } finally {
      addingRef.current.delete(ticker);
    }
  };

  const sectors = ["all", ...Array.from(new Set(localStocks.map(s => s.sector)))];

  const sorted = [...localStocks]
    .filter(s => filterSector === "all" || s.sector === filterSector)
    .sort((a, b) => {
      if (sortBy === "score") return b.score - a.score;
      if (sortBy === "change") return b.changePct - a.changePct;
      const convA = a.signals.length ? a.signals.filter(s => s.signal === "bullish").length / a.signals.length : 0;
      const convB = b.signals.length ? b.signals.filter(s => s.signal === "bullish").length / b.signals.length : 0;
      return convB - convA;
    });

  const selectedStock = localStocks.find(s => s.ticker === selectedTicker);

  const totalBullish = localStocks.reduce((sum, s) => sum + s.signals.filter(sig => sig.signal === "bullish").length, 0);
  const totalSignals = localStocks.reduce((sum, s) => sum + s.signals.length, 0);
  const avgScore = localStocks.length ? localStocks.reduce((sum, s) => sum + s.score, 0) / localStocks.length : 0;

  return (
    <div className="min-h-screen">
      {/* Top bar */}
      <header className="border-b border-[var(--border)] bg-[var(--bg)]">
        <div className="max-w-[1400px] mx-auto px-3 sm:px-6 py-3 sm:py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-0">
          <div className="flex items-center gap-4 sm:gap-6">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-[var(--text)] flex items-center justify-center text-sm font-bold text-[var(--bg)]">SR</div>
              <div>
                <h1 className="text-lg font-bold">Stock Radar</h1>
                <p className="text-[10px] text-[var(--muted)] hidden sm:block">Multi-AI Agent System</p>
              </div>
            </div>
            <nav className="flex gap-3 sm:gap-4 text-xs ml-2 sm:ml-4">
              <span className="text-amber-500 font-medium">Watchlist</span>
              <a href="/discovery" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Discovery</a>
              <a href="/model" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Models</a>
              <a href="/ask" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors hidden sm:inline">Ask AI</a>
              <a href="/logs" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Logs</a>
            </nav>
          </div>
          <div className="flex items-center gap-3 sm:gap-6 text-xs text-[var(--muted)] overflow-x-auto">
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
            {/* Pipeline controls */}
            <div className="flex items-center gap-2">
              {pipelineRunning ? (
                <button
                  onClick={stopPipeline}
                  className="px-3 py-1.5 rounded-md border border-red-500/40 text-[11px] font-medium text-red-400 hover:bg-red-500/10 hover:border-red-500/60 transition-all"
                  title="Force-stop the running pipeline"
                >
                  <span className="flex items-center gap-1.5">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="2.5" y="2.5" width="7" height="7" rx="1" fill="currentColor"/></svg>
                    Stop Pipeline
                  </span>
                </button>
              ) : (
                <button
                  onClick={() => runPipeline(false)}
                  className="px-3 py-1.5 rounded-md border border-[var(--border)] text-[11px] font-medium text-[var(--secondary)] hover:text-[var(--text)] hover:border-[var(--border-hover)] hover:bg-[var(--hover)] transition-all"
                  title="Run all scouts including AI-powered ones (requires API keys)"
                >
                  Run Pipeline
                </button>
              )}
              <button
                onClick={() => runPipeline(true)}
                disabled={pipelineRunning}
                className={cn(
                  "px-2.5 py-1.5 rounded-md border border-[var(--border)] text-[10px] transition-all",
                  pipelineRunning
                    ? "text-[var(--muted)] cursor-not-allowed opacity-50"
                    : "text-[var(--muted)] hover:text-[var(--secondary)] hover:bg-[var(--hover)]"
                )}
                title={pipelineRunning ? "Pipeline is already running" : "Run only free scouts (no API keys needed)"}
              >
                Free only
              </button>
              <button
                onClick={() => runRebuild()}
                disabled={rebuildRunning || pipelineRunning}
                className={cn(
                  "px-2.5 py-1.5 rounded-md border border-[var(--border)] text-[10px] transition-all",
                  (rebuildRunning || pipelineRunning)
                    ? "text-[var(--muted)] cursor-not-allowed opacity-50"
                    : "text-[var(--muted)] hover:text-[var(--secondary)] hover:bg-[var(--hover)]"
                )}
                title={
                  rebuildRunning
                    ? "Rebuild is running"
                    : pipelineRunning
                    ? "Wait for pipeline to finish"
                    : "Recompute analysis from existing signals (no scout re-run)"
                }
              >
                {rebuildRunning ? (
                  <span className="flex items-center gap-1">
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M5 1v1.5M5 7.5V9M1 5h1.5M7.5 5H9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" className="animate-spin origin-center" style={{ transformBox: "fill-box" }}/></svg>
                    Rebuilding...
                  </span>
                ) : "Rebuild"}
              </button>
            </div>
            <span>Last scan: <span className="text-[var(--secondary)] font-mono">{formatTime(meta.generatedAt)}</span></span>
            <button
              onClick={() => setShowScoutPanel(!showScoutPanel)}
              className="flex items-center gap-1.5 hover:text-[var(--text)] transition-colors"
            >
              <span className={cn("w-2 h-2 rounded-full", activeScoutCount > 0 ? "bg-[var(--success)] signal-pulse" : "bg-[var(--muted)]")}></span>
              {activeScoutCount}/{totalScoutCount} scouts active
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" className={cn("transition-transform", showScoutPanel && "rotate-180")}>
                <path d="M2.5 3.75L5 6.25L7.5 3.75" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <button
              onClick={() => setShowHealthPanel(!showHealthPanel)}
              className="flex items-center gap-1.5 hover:text-[var(--text)] transition-colors"
              title="System health: data providers, tests, pipeline status"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1.5v3M7 9.5v3M1.5 7h3M9.5 7h3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                <circle cx="7" cy="7" r="2" stroke="currentColor" strokeWidth="1.2"/>
              </svg>
              Health
            </button>
          </div>
        </div>
      </header>

      {/* Pipeline progress bar (shown when running) */}
      {pipelineRunning && (
        <PipelineProgressBar progress={pipelineProgress} />
      )}

      {/* Rebuild progress bar */}
      {rebuildRunning && rebuildProgress && (
        <div className="mb-4 rounded-lg bg-[var(--card)] border border-[var(--border)] p-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] text-[var(--muted)]">Rebuilding analysis...</span>
            <span className="text-[10px] font-mono text-[var(--secondary)]">{rebuildProgress.percent}%</span>
          </div>
          <div className="w-full h-1.5 bg-[var(--bg)] rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--accent)] rounded-full transition-all duration-500"
              style={{ width: `${rebuildProgress.percent}%` }}
            />
          </div>
          <div className="text-[9px] text-[var(--faint)] mt-1">{rebuildProgress.message}</div>
        </div>
      )}

      {/* Scout status panel */}
      {showScoutPanel && (
        <ScoutPanel
          scoutDetails={meta.scoutDetails}
          scoutAccuracy={scoutAccuracy}
          feedbackLoaded={feedbackLoaded}
          formatTime={formatTime}
        />
      )}

      {/* Health panel */}
      {showHealthPanel && (
        <HealthPanel onClose={() => setShowHealthPanel(false)} />
      )}

      <main className="max-w-[1400px] mx-auto px-3 sm:px-6 py-4 sm:py-6">
        {/* Pipeline error banner */}
        {pipelineError && (
          <div className="mb-4 px-4 py-3 rounded-lg border bg-[var(--danger-bg)] border-[var(--danger)]/20 flex items-center justify-between">
            <span className="text-xs text-[var(--danger)]">{pipelineError}</span>
            <button
              onClick={() => setPipelineError(null)}
              className="text-[var(--muted)] hover:text-[var(--text)] text-xs px-2"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Add stock — always enabled */}
        <div className="mb-6">
          <TickerSearch
            existingTickers={localStocks.map(s => s.ticker)}
            onAddTicker={handleAddTicker}
          />
        </div>

        {/* Summary cards */}
        <SummaryCards
          stockCount={localStocks.length}
          avgScore={avgScore}
          totalBullish={totalBullish}
          totalSignals={totalSignals}
          topPick={sorted[0] ? { ticker: sorted[0].ticker, score: sorted[0].score } : null}
        />

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 sm:gap-4 mb-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--muted)]">Sort:</span>
            {(["score", "change", "convergence"] as const).map(s => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={cn(
                  "text-xs px-3 py-1.5 rounded-lg border transition-all",
                  sortBy === s
                    ? "bg-[var(--hover)] border-[var(--border-hover)] text-[var(--text)]"
                    : "bg-[var(--bg-elevated)] border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)]"
                )}
              >
                {s === "score" ? "Score" : s === "change" ? "% Change" : "Convergence"}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 sm:ml-4">
            <span className="text-xs text-[var(--muted)]">Sector:</span>
            <select
              value={filterSector}
              onChange={e => setFilterSector(e.target.value)}
              className="text-xs px-3 py-1.5 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] text-[var(--secondary)] outline-none"
            >
              {sectors.map(s => (
                <option key={s} value={s}>{s === "all" ? "All Sectors" : s}</option>
              ))}
            </select>
          </div>
          <div className="ml-auto flex items-center gap-3">
            {selectMode ? (
              <>
                <button onClick={selectAll} className="text-[10px] text-[var(--muted)] hover:text-[var(--text)] transition-colors">Select all</button>
                <button onClick={selectNone} className="text-[10px] text-[var(--muted)] hover:text-[var(--text)] transition-colors">Clear</button>
                <button
                  onClick={handleBulkDelete}
                  disabled={selectedTickers.size === 0}
                  className={cn(
                    "text-[11px] font-medium px-3 py-1.5 rounded-md border transition-all",
                    selectedTickers.size > 0
                      ? "border-red-500/40 text-red-400 hover:bg-red-500/10"
                      : "border-[var(--border)] text-[var(--muted)] opacity-50 cursor-not-allowed"
                  )}
                >
                  Delete {selectedTickers.size > 0 ? `(${selectedTickers.size})` : ""}
                </button>
                <button
                  onClick={() => { setSelectMode(false); setSelectedTickers(new Set()); }}
                  className="text-[10px] text-[var(--muted)] hover:text-[var(--text)] transition-colors"
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={() => setSelectMode(true)}
                className="text-[10px] text-[var(--muted)] hover:text-[var(--text)] transition-colors"
              >
                Select
              </button>
            )}
          </div>
        </div>

        {/* Empty state */}
        {sorted.length === 0 && (
          <div className="text-center py-16 text-gray-500">
            <div className="text-4xl mb-4">📡</div>
            <div className="text-lg mb-2">No data yet</div>
            <div className="text-sm">Run <code className="text-[#a78bfa] bg-[#1e1e2e] px-2 py-0.5 rounded">python scripts/run_pipeline.py</code> to generate signals</div>
          </div>
        )}

        {/* Stock list */}
        {sorted.map(stock => (
          <div key={stock.ticker}>
            <StockRow
              stock={stock}
              isSelected={selectedTicker === stock.ticker}
              onClick={() => setSelectedTicker(selectedTicker === stock.ticker ? null : stock.ticker)}
              selectMode={selectMode}
              isChecked={selectedTickers.has(stock.ticker)}
              onCheck={toggleCheck}
            />
            {selectedTicker === stock.ticker && !selectMode && <StockDetail stock={stock} onDelete={() => handleDeleteStock(stock.ticker)} />}
          </div>
        ))}

        {/* Footer */}
        <footer className="mt-8 pt-4 border-t border-[#1e1e2e] text-center text-[10px] text-gray-600">
          Stock Radar v1.0 — Multi-AI Agent System — Live data from {activeScoutCount} scouts — Not financial advice
        </footer>
      </main>
    </div>
  );
}
