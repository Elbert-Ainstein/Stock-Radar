import React from "react";
import type { GlobeCandidate } from "./geo-data";
import { signalColor, signalLabel } from "./globe-helpers";

interface GlobeTooltipProps {
  candidate: GlobeCandidate;
  x: number;
  y: number;
}

export default function GlobeTooltip({ candidate, x, y }: GlobeTooltipProps) {
  return (
    <div
      className="absolute pointer-events-none z-50"
      style={{
        left: x + 12,
        top: y - 10,
      }}
    >
      <div className="bg-zinc-900/95 backdrop-blur-sm border border-zinc-700/60 rounded-lg px-3 py-2 shadow-xl">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-sm text-white">
            {candidate.ticker}
          </span>
          <span
            className="text-[10px] font-medium px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: signalColor(candidate.signal) + "22",
              color: signalColor(candidate.signal),
            }}
          >
            {signalLabel(candidate.signal)}
          </span>
        </div>
        <div className="text-[11px] text-zinc-400 mt-0.5">{candidate.name}</div>
        <div className="text-[10px] text-zinc-500 mt-0.5">
          Score: {candidate.quant_score.toFixed(1)} ·{" "}
          ${candidate.market_cap_b.toFixed(1)}B
        </div>
      </div>
    </div>
  );
}
