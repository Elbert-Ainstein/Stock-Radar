"use client";

import React, { useState } from "react";

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

export type SortKey = "rank" | "quant_score" | "revenue_growth_pct" | "gross_margin_pct" | "forward_pe" | "market_cap_b" | "distance_from_high_pct";

// ─── Helpers ───
function scoreColor(score: number): string {
  if (score >= 8) return "text-emerald-400";
  if (score >= 6.5) return "text-green-400";
  if (score >= 5) return "text-amber-400";
  if (score >= 3.5) return "text-orange-400";
  return "text-rose-400";
}

function signalBadge(signal: string) {
  const colors: Record<string, string> = {
    bullish: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    bearish: "bg-rose-500/15 text-rose-400 border-rose-500/30",
    neutral: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
  };
  return colors[signal] || colors.neutral;
}

function formatNum(n: number | null | undefined, decimals = 1): string {
  if (n == null || isNaN(n)) return "\u2014";
  return n.toFixed(decimals);
}

interface CandidateTableProps {
  candidates: Candidate[];
  sortKey: SortKey;
  sortAsc: boolean;
  onSort: (key: SortKey) => void;
  adding: string | null;
  addedTickers: Set<string>;
  onAddToWatchlist: (candidate: Candidate) => void;
}

export default function CandidateTable({
  candidates,
  sortKey,
  sortAsc,
  onSort,
  adding,
  addedTickers,
  onAddToWatchlist,
}: CandidateTableProps) {
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

  const SortIcon = ({ k }: { k: SortKey }) => (
    <span className="ml-1 text-[10px] opacity-50">
      {sortKey === k ? (sortAsc ? "\u25B2" : "\u25BC") : "\u21C5"}
    </span>
  );

  return (
    <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-[11px] uppercase tracking-wider text-[var(--muted)]">
              <th className="px-4 py-3 text-left cursor-pointer hover:text-[var(--text)]" onClick={() => onSort("rank")}>
                #<SortIcon k="rank" />
              </th>
              <th className="px-4 py-3 text-left">Ticker</th>
              <th className="px-4 py-3 text-left">Signal</th>
              <th className="px-4 py-3 text-right cursor-pointer hover:text-[var(--text)]" onClick={() => onSort("quant_score")}>
                Score<SortIcon k="quant_score" />
              </th>
              <th className="px-4 py-3 text-right cursor-pointer hover:text-[var(--text)]" onClick={() => onSort("market_cap_b")}>
                Mkt Cap<SortIcon k="market_cap_b" />
              </th>
              <th className="px-4 py-3 text-right cursor-pointer hover:text-[var(--text)]" onClick={() => onSort("revenue_growth_pct")}>
                Rev Grw<SortIcon k="revenue_growth_pct" />
              </th>
              <th className="px-4 py-3 text-right cursor-pointer hover:text-[var(--text)]" onClick={() => onSort("gross_margin_pct")}>
                Gross M<SortIcon k="gross_margin_pct" />
              </th>
              <th className="px-4 py-3 text-right cursor-pointer hover:text-[var(--text)]" onClick={() => onSort("forward_pe")}>
                Fwd PE<SortIcon k="forward_pe" />
              </th>
              <th className="px-4 py-3 text-right cursor-pointer hover:text-[var(--text)]" onClick={() => onSort("distance_from_high_pct")}>
                vs 52H<SortIcon k="distance_from_high_pct" />
              </th>
              <th className="px-4 py-3 text-left">Summary</th>
              <th className="px-4 py-3 text-center">Action</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c, i) => {
              const isExpanded = expandedTicker === c.ticker;
              const hasAI = c.stage === "validated" && c.thesis;
              return (
                <React.Fragment key={c.ticker}>
                  <tr
                    className={`border-b border-[var(--border)]/50 hover:bg-[var(--bg)]/50 transition-colors ${hasAI ? "cursor-pointer" : ""}`}
                    onClick={() => hasAI && setExpandedTicker(isExpanded ? null : c.ticker)}
                  >
                    <td className="px-4 py-3 text-[var(--muted)] font-mono text-xs">
                      {c.rank || i + 1}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-[var(--text)]">{c.ticker}</span>
                        {c.stage === "validated" && (
                          <span className="text-[8px] px-1 py-0.5 rounded bg-violet-500/15 text-violet-400 border border-violet-500/30 font-mono">AI</span>
                        )}
                      </div>
                      <div className="text-[10px] text-[var(--muted)] max-w-[120px] truncate">{c.name || c.sector || ""}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${signalBadge(c.signal)}`}>
                        {c.signal}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className={`font-mono font-bold ${scoreColor(c.quant_score)}`}>
                        {c.quant_score.toFixed(1)}
                      </div>
                      {c.ai_confidence != null && c.ai_confidence > 0 && (
                        <div className="text-[9px] text-violet-400 font-mono">{(c.ai_confidence * 100).toFixed(0)}% conf</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-[var(--muted)]">
                      ${formatNum(c.market_cap_b)}B
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      <span className={c.revenue_growth_pct > 20 ? "text-emerald-400" : c.revenue_growth_pct > 0 ? "text-[var(--text)]" : "text-rose-400"}>
                        {formatNum(c.revenue_growth_pct)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-[var(--muted)]">
                      {formatNum(c.gross_margin_pct)}%
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-[var(--muted)]">
                      {c.forward_pe ? formatNum(c.forward_pe) : "\u2014"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      <span className={c.distance_from_high_pct < 10 ? "text-emerald-400" : c.distance_from_high_pct > 30 ? "text-rose-400" : "text-[var(--muted)]"}>
                        {formatNum(c.distance_from_high_pct)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--muted)] max-w-[200px] truncate">
                      {c.thesis ? c.thesis.slice(0, 80) + "..." : c.summary}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {addedTickers.has(c.ticker) ? (
                        <span className="text-[10px] text-emerald-400 font-medium">Added {"\u2713"}</span>
                      ) : (
                        <button
                          onClick={(e) => { e.stopPropagation(); onAddToWatchlist(c); }}
                          disabled={adding === c.ticker}
                          className="text-[10px] px-3 py-1 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20 transition-colors font-medium disabled:opacity-50"
                        >
                          {adding === c.ticker ? "Adding..." : "+ Watch"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {/* Expanded AI detail row */}
                  {isExpanded && hasAI && (
                    <tr key={`${c.ticker}-detail`} className="bg-[var(--bg)]/30">
                      <td colSpan={11} className="px-6 py-4">
                        <div className="grid grid-cols-2 gap-6 max-w-4xl">
                          <div>
                            <h4 className="text-[10px] uppercase tracking-wider text-violet-400 font-semibold mb-1">10x Thesis</h4>
                            <p className="text-xs text-[var(--secondary)] leading-relaxed">{c.thesis}</p>

                            {c.kill_condition && (
                              <div className="mt-3">
                                <h4 className="text-[10px] uppercase tracking-wider text-rose-400 font-semibold mb-1">Kill Condition</h4>
                                <p className="text-xs text-[var(--muted)]">{c.kill_condition}</p>
                              </div>
                            )}
                          </div>
                          <div>
                            {c.catalysts && c.catalysts.length > 0 && (
                              <div className="mb-3">
                                <h4 className="text-[10px] uppercase tracking-wider text-amber-400 font-semibold mb-1">Catalysts</h4>
                                <ul className="text-xs text-[var(--secondary)] space-y-0.5">
                                  {c.catalysts.map((cat, ci) => (
                                    <li key={ci} className="flex items-start gap-1.5">
                                      <span className="text-amber-400 mt-0.5">{"\u203A"}</span>
                                      <span>{cat}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {c.target_range && (c.target_range.base || c.target_range.high) && (
                              <div className="mb-3">
                                <h4 className="text-[10px] uppercase tracking-wider text-emerald-400 font-semibold mb-1">3-Year Target Range</h4>
                                <div className="flex gap-4 text-xs font-mono">
                                  {c.target_range.low != null && <span className="text-rose-400">Bear: ${c.target_range.low}</span>}
                                  {c.target_range.base != null && <span className="text-[var(--text)]">Base: ${c.target_range.base}</span>}
                                  {c.target_range.high != null && <span className="text-emerald-400">Bull: ${c.target_range.high}</span>}
                                </div>
                                {c.price > 0 && c.target_range.base && (
                                  <div className="text-[10px] text-[var(--muted)] mt-1">
                                    Current: ${c.price} {"\u2192"} {((c.target_range.base / c.price - 1) * 100).toFixed(0)}% upside (base)
                                  </div>
                                )}
                              </div>
                            )}

                            {c.tags && c.tags.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 mt-2">
                                {c.tags.map((tag, ti) => (
                                  <span key={ti} className="text-[9px] px-2 py-0.5 rounded-full bg-[var(--border)] text-[var(--muted)]">{tag}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
