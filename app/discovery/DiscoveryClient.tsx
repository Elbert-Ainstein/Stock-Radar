"use client";

import React, { useState, useEffect, useCallback, useRef, lazy, Suspense } from "react";
import FunnelStats from "./FunnelStats";
import ControlBar from "./ControlBar";
import CandidateTable from "./CandidateTable";
import type { SortKey } from "./CandidateTable";

const DiscoveryGlobe = lazy(() => import("../components/DiscoveryGlobe"));

// ─── Types ───
interface Candidate {
  ticker: string;
  name: string;
  sector: string;
  industry?: string;
  price: number;
  change_pct: number;
  market_cap_b: number;
  revenue_growth_pct: number;
  earnings_growth_pct: number;
  gross_margin_pct: number;
  operating_margin_pct: number;
  forward_pe: number | null;
  ps_ratio: number | null;
  distance_from_high_pct: number;
  short_pct: number;
  quant_score: number;
  scores: Record<string, number>;
  signal: string;
  summary: string;
  stage: string;
  rank: number | null;
  ai_confidence?: number | null;
  thesis?: string | null;
  kill_condition?: string | null;
  catalysts?: string[];
  target_range?: { low?: number; base?: number; high?: number };
  tags?: string[];
  hq_city?: string;
  hq_state?: string;
  hq_country?: string;
}

interface DiscoveryState {
  running: boolean;
  progress: { stage: string; message: string; current: number; total: number; percent: number } | null;
  lastRunAt: string;
  totalCandidates: number;
  shortlistCount: number;
  validatedCount: number;
  candidates: Candidate[];
}

function timeAgo(iso: string): string {
  if (!iso) return "Never";
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// ─── Main Component ───
export default function DiscoveryClient() {
  const [state, setState] = useState<DiscoveryState>({
    running: false,
    progress: null,
    lastRunAt: "",
    totalCandidates: 0,
    shortlistCount: 0,
    validatedCount: 0,
    candidates: [],
  });

  const [filter, setFilter] = useState<"all" | "shortlist" | "validated">("shortlist");
  const [sectorFilter, setSectorFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("quant_score");
  const [sortAsc, setSortAsc] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const [addedTickers, setAddedTickers] = useState<Set<string>>(new Set());
  const [showGlobe, setShowGlobe] = useState(true);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // ─── Fetch data ───
  const fetchData = useCallback(async () => {
    try {
      const resp = await fetch("/api/discovery");
      if (resp.ok) {
        const data = await resp.json();
        setState(data);
        return data.running;
      }
    } catch {}
    return false;
  }, []);

  // ─── Polling ───
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      const running = await fetchData();
      if (!running && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }, 3000);
  }, [fetchData]);

  useEffect(() => {
    fetchData().then(running => {
      if (running) startPolling();
    });
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchData, startPolling]);

  // ─── Start scan ───
  const startScan = async (quick = false) => {
    try {
      const resp = await fetch("/api/discovery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quick }),
      });
      if (resp.ok || resp.status === 409) {
        await fetchData();
        startPolling();
      }
    } catch {}
  };

  // ─── Add to watchlist ───
  const addToWatchlist = async (candidate: Candidate) => {
    setAdding(candidate.ticker);
    try {
      const resp = await fetch("/api/discovery", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: candidate.ticker }),
      });
      if (resp.ok) {
        setAddedTickers(prev => new Set(prev).add(candidate.ticker));
      }
    } catch {}
    setAdding(null);
  };

  // ─── Filter & sort ───
  const filtered = state.candidates
    .filter(c => {
      if (filter === "all") return true;
      if (filter === "validated") return c.stage === "validated";
      return c.stage === "shortlist" || c.stage === "validated";
    })
    .filter(c => !sectorFilter || (c.sector || "").toLowerCase().includes(sectorFilter.toLowerCase()))
    .sort((a, b) => {
      const av = (a as any)[sortKey] ?? 0;
      const bv = (b as any)[sortKey] ?? 0;
      return sortAsc ? av - bv : bv - av;
    });

  const sectors = [...new Set(state.candidates.map(c => c.sector).filter(Boolean))].sort();

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      {/* ─── HEADER ─── */}
      <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--bg)]/80 backdrop-blur-xl">
        <div className="max-w-[1400px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <a href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center">
                <span className="text-white font-bold text-sm">SR</span>
              </div>
              <span className="font-semibold text-[var(--text)]">Stock Radar</span>
            </a>
            <nav className="flex gap-4 text-sm">
              <a href="/" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Watchlist</a>
              <span className="text-amber-500 font-medium">Discovery</span>
              <a href="/model" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Models</a>
            </nav>
          </div>
          <div className="text-xs text-[var(--muted)] font-mono">
            {state.lastRunAt ? `Last scan: ${timeAgo(state.lastRunAt)}` : "No scans yet"}
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-8">
        {/* ─── FUNNEL STATS ─── */}
        <FunnelStats
          totalCandidates={state.totalCandidates}
          shortlistCount={state.shortlistCount}
          validatedCount={state.validatedCount}
          promotedCount={addedTickers.size}
        />

        {/* ─── GLOBE VIEW ─── */}
        {filtered.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-medium text-[var(--text)]">Global Distribution</h2>
                <span className="text-[10px] text-[var(--muted)]">Interactive 3D map of shortlisted companies</span>
              </div>
              <button
                onClick={() => setShowGlobe(!showGlobe)}
                className="text-xs text-[var(--muted)] hover:text-[var(--text)] transition-colors px-3 py-1 rounded-lg border border-[var(--border)] hover:border-[var(--accent-muted)]"
              >
                {showGlobe ? "Hide Globe" : "Show Globe"}
              </button>
            </div>
            {showGlobe && (
              <div className="rounded-xl border border-[var(--border)] overflow-hidden">
                <Suspense fallback={
                  <div className="w-full h-[520px] flex items-center justify-center bg-black/50 text-zinc-500 text-sm">
                    Loading globe...
                  </div>
                }>
                  <DiscoveryGlobe candidates={filtered} />
                </Suspense>
              </div>
            )}
          </div>
        )}

        {/* ─── CONTROLS ─── */}
        <ControlBar
          running={state.running}
          filter={filter}
          sectorFilter={sectorFilter}
          sectors={sectors}
          shortlistCount={state.shortlistCount}
          validatedCount={state.validatedCount}
          totalCandidates={state.totalCandidates}
          onStartScan={startScan}
          onFilterChange={setFilter}
          onSectorChange={setSectorFilter}
        />

        {/* ─── PROGRESS BAR ─── */}
        {state.running && state.progress && (
          <div className="mb-6 rounded-xl bg-[var(--card)] border border-amber-500/30 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-amber-400 font-medium uppercase tracking-wider">
                {state.progress.stage}
              </span>
              <span className="text-xs font-mono text-[var(--muted)]">
                {state.progress.current}/{state.progress.total} ({state.progress.percent}%)
              </span>
            </div>
            <div className="h-2 rounded-full bg-[var(--border)] overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-amber-500 to-orange-500 transition-all duration-500"
                style={{ width: `${state.progress.percent}%` }}
              />
            </div>
            <div className="text-xs text-[var(--muted)] mt-2">{state.progress.message}</div>
          </div>
        )}

        {/* ─── CANDIDATE TABLE ─── */}
        {filtered.length > 0 ? (
          <CandidateTable
            candidates={filtered}
            sortKey={sortKey}
            sortAsc={sortAsc}
            onSort={handleSort}
            adding={adding}
            addedTickers={addedTickers}
            onAddToWatchlist={addToWatchlist}
          />
        ) : (
          /* ─── EMPTY STATE ─── */
          <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-16 text-center">
            <div className="text-4xl mb-4">{"\uD83D\uDD2D"}</div>
            <h2 className="text-lg font-semibold text-[var(--text)] mb-2">No candidates yet</h2>
            <p className="text-sm text-[var(--muted)] mb-6 max-w-md mx-auto">
              Run a discovery scan to screen 500+ stocks and find the top candidates.
              The scanner uses quantitative filters — revenue growth, margins, valuation, and relative strength
              — to surface stocks worth a closer look.
            </p>
            <button
              onClick={() => startScan(true)}
              disabled={state.running}
              className="px-6 py-2.5 rounded-lg text-sm font-medium bg-gradient-to-r from-amber-500 to-orange-600 text-white hover:shadow-lg hover:shadow-amber-500/20 transition-all disabled:opacity-50"
            >
              Run Quick Scan (100 stocks)
            </button>
          </div>
        )}

        {/* ─── FOOTER NOTE ─── */}
        {filtered.length > 0 && (
          <div className="mt-4 text-center text-xs text-[var(--muted)]">
            Showing {filtered.length} of {state.totalCandidates} candidates {"\u00B7"} Sorted by {sortKey.replace(/_/g, " ")} {sortAsc ? "\u2191" : "\u2193"}
          </div>
        )}
      </main>
    </div>
  );
}
