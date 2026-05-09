"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import type { Stock } from "@/lib/data";
import { inferCurrency } from "@/lib/data";
import type { PipelineProgress, ScoutInfo } from "./types";
import { cn, scoreColor, formatTime } from "./helpers";
import PipelineProgressBar from "./PipelineProgressBar";
import StockRow, { SRWatchlistHeader, SR_GRID } from "./StockRow";
import RunAllThesesButton from "./RunAllThesesButton";
import WatchlistRefreshPanel from "./WatchlistRefreshPanel";
import TickerSearch from "./TickerSearch";
import ScoutPanel from "./ScoutPanel";
import SummaryCards from "./SummaryCards";
import HealthPanel from "./HealthPanel";

// ─── Main Dashboard ───

export default function Dashboard({ stocks, meta }: { stocks: Stock[]; meta: { generatedAt: string; scoutsActive: string[]; scoutDetails: ScoutInfo[] } }) {
  const router = useRouter();
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

        {/* Module 12 — Watchlist convergence refresh on the Watchlist page.
            Discovery convergence panel lives on /discovery (different information architecture):
            this surface shows fresh cross-source signal on names you already track. */}
        <WatchlistRefreshPanel top={8} minClasses={2} />

        {/* SR Production watchlist — CSS-grid layout from May 4 redesign
            (StockRow + SRWatchlistHeader, sr-* tokens, mono numerics, 28px row height). */}
        {sorted.length > 0 && (
          <div style={{
            border: "1px solid var(--sr-rule, #2a2a2a)",
            borderRadius: 6,
            background: "var(--sr-paper, #0e0e10)",
            overflowX: "auto",
            marginBottom: 16,
          }}>
            <div style={{ minWidth: 1208 }}>
              <SRWatchlistHeader />
              {sorted.map((stock, idx) => (
                <StockRow
                  key={stock.ticker}
                  stock={stock}
                  isSelected={false}
                  onClick={() => {
                    if (selectMode) {
                      toggleCheck(stock.ticker);
                    } else {
                      router.push(`/stock/${encodeURIComponent(stock.ticker)}`);
                    }
                  }}
                  selectMode={selectMode}
                  isChecked={selectedTickers.has(stock.ticker)}
                  onCheck={toggleCheck}
                />
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <footer className="mt-8 pt-4 border-t border-[#1e1e2e] text-center text-[10px] text-gray-600">
          Stock Radar v1.0 — Multi-AI Agent System — Live data from {activeScoutCount} scouts — Not financial advice
        </footer>
      </main>
    </div>
  );
}
