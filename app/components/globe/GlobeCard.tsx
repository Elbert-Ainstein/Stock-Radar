import React from "react";
import type { GlobeCandidate } from "./geo-data";
import { scoreColor, signalColor, signalLabel } from "./globe-helpers";

interface GlobeCardProps {
  candidate: GlobeCandidate;
  onClose: () => void;
}

export default function GlobeCard({ candidate, onClose }: GlobeCardProps) {
  return (
    <div
      className="absolute inset-0 flex items-center justify-center z-50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="bg-zinc-900/98 backdrop-blur-md border border-zinc-700/70 rounded-2xl shadow-2xl p-6 max-w-md w-full mx-4"
        style={{ maxHeight: "80%", overflowY: "auto" }}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-3">
              <span className="text-2xl font-bold font-mono text-white">
                {candidate.ticker}
              </span>
              <span
                className="text-xs font-medium px-2 py-1 rounded-full"
                style={{
                  backgroundColor: signalColor(candidate.signal) + "22",
                  color: signalColor(candidate.signal),
                  border: `1px solid ${signalColor(candidate.signal)}44`,
                }}
              >
                {signalLabel(candidate.signal)}
              </span>
            </div>
            <div className="text-sm text-zinc-400 mt-1">{candidate.name}</div>
            <div className="text-xs text-zinc-500 mt-0.5">
              {candidate.sector}
              {candidate.industry ? ` · ${candidate.industry}` : ""}
            </div>
            {(candidate.hq_city || candidate.hq_country) && (
              <div className="text-xs text-zinc-500 mt-0.5">
                {"\uD83D\uDCCD"} {[candidate.hq_city, candidate.hq_state, candidate.hq_country].filter(Boolean).join(", ")}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-white transition-colors text-lg leading-none p-1"
          >
            {"\u2715"}
          </button>
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-zinc-800/60 rounded-lg p-3 text-center">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Score</div>
            <div
              className="text-xl font-bold mt-1"
              style={{ color: scoreColor(candidate.quant_score) }}
            >
              {candidate.quant_score.toFixed(1)}
            </div>
          </div>
          <div className="bg-zinc-800/60 rounded-lg p-3 text-center">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Price</div>
            <div className="text-xl font-bold text-white mt-1">
              ${candidate.price.toFixed(2)}
            </div>
          </div>
          <div className="bg-zinc-800/60 rounded-lg p-3 text-center">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Mkt Cap</div>
            <div className="text-xl font-bold text-white mt-1">
              ${candidate.market_cap_b.toFixed(1)}B
            </div>
          </div>
          <div className="bg-zinc-800/60 rounded-lg p-3 text-center">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Rev Growth</div>
            <div
              className="text-lg font-bold mt-1"
              style={{
                color: candidate.revenue_growth_pct > 25 ? "#34d399" : "#fbbf24",
              }}
            >
              {candidate.revenue_growth_pct.toFixed(0)}%
            </div>
          </div>
          <div className="bg-zinc-800/60 rounded-lg p-3 text-center">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Change</div>
            <div
              className="text-lg font-bold mt-1"
              style={{
                color: candidate.change_pct >= 0 ? "#34d399" : "#f87171",
              }}
            >
              {candidate.change_pct >= 0 ? "+" : ""}
              {candidate.change_pct.toFixed(1)}%
            </div>
          </div>
          {candidate.ai_confidence != null && (
            <div className="bg-zinc-800/60 rounded-lg p-3 text-center">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider">
                AI Conf.
              </div>
              <div className="text-lg font-bold text-violet-400 mt-1">
                {(candidate.ai_confidence * 100).toFixed(0)}%
              </div>
            </div>
          )}
        </div>

        {/* Tags */}
        {candidate.tags && candidate.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {candidate.tags.map((tag) => (
              <span
                key={tag}
                className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/25"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Thesis */}
        {candidate.thesis && (
          <div className="mb-4">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">
              Investment Thesis
            </div>
            <div className="text-sm text-zinc-300 leading-relaxed">
              {candidate.thesis}
            </div>
          </div>
        )}

        {/* Target Range */}
        {candidate.target_range &&
          (candidate.target_range.low ||
            candidate.target_range.base ||
            candidate.target_range.high) && (
            <div className="mb-4">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">
                Target Range
              </div>
              <div className="flex items-center gap-2">
                <div className="text-center flex-1">
                  <div className="text-[10px] text-rose-400">Bear</div>
                  <div className="text-sm font-bold text-rose-300">
                    ${candidate.target_range.low?.toFixed(0) || "\u2014"}
                  </div>
                </div>
                <div className="flex-1 h-1.5 bg-gradient-to-r from-rose-500/40 via-amber-500/40 to-emerald-500/40 rounded-full" />
                <div className="text-center flex-1">
                  <div className="text-[10px] text-amber-400">Base</div>
                  <div className="text-sm font-bold text-amber-300">
                    ${candidate.target_range.base?.toFixed(0) || "\u2014"}
                  </div>
                </div>
                <div className="flex-1 h-1.5 bg-gradient-to-r from-amber-500/40 to-emerald-500/40 rounded-full" />
                <div className="text-center flex-1">
                  <div className="text-[10px] text-emerald-400">Bull</div>
                  <div className="text-sm font-bold text-emerald-300">
                    ${candidate.target_range.high?.toFixed(0) || "\u2014"}
                  </div>
                </div>
              </div>
            </div>
          )}

        {/* Stage badge */}
        <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
          <span className="text-[10px] text-zinc-500">Stage:</span>
          <span
            className="text-[10px] font-medium px-2 py-0.5 rounded-full"
            style={{
              backgroundColor:
                candidate.stage === "validated"
                  ? "rgba(139,92,246,0.15)"
                  : candidate.stage === "shortlist"
                  ? "rgba(59,130,246,0.15)"
                  : "rgba(107,114,128,0.15)",
              color:
                candidate.stage === "validated"
                  ? "#a78bfa"
                  : candidate.stage === "shortlist"
                  ? "#60a5fa"
                  : "#9ca3af",
            }}
          >
            {candidate.stage.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  );
}
