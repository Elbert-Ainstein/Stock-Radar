"use client";

import { cn, pct } from "../helpers";

const defaultFmt = (price: number) => `$${Math.round(price).toLocaleString()}`;

export default function ScenarioSection({
  targetPrice,
  currentPrice,
  bearProb,
  baseProb,
  bullProb,
  bearPrice,
  bullPrice,
  fmt = defaultFmt,
}: {
  targetPrice: number;
  currentPrice: number;
  bearProb: number;
  baseProb: number;
  bullProb: number;
  bearPrice: number;
  bullPrice: number;
  fmt?: (price: number) => string;
}) {
  const scenarios = [
    { name: "Bear", prob: bearProb, price: bearPrice, color: "text-rose-400", bg: "bg-rose-400" },
    { name: "Base", prob: baseProb, price: targetPrice, color: "text-amber-400", bg: "bg-amber-400" },
    { name: "Bull", prob: bullProb, price: bullPrice, color: "text-emerald-400", bg: "bg-emerald-400" },
  ];
  const ev = scenarios.reduce((sum, s) => sum + s.prob * s.price, 0);
  const upside = currentPrice > 0 ? ((ev / currentPrice) - 1) * 100 : 0;

  return (
    <div>
      <div className="grid grid-cols-3 gap-3 mb-4">
        {scenarios.map(s => (
          <div key={s.name} className="p-4 rounded-lg bg-[var(--bg)] border border-[var(--border)]">
            <div className="flex items-center justify-between mb-2">
              <span className={cn("text-xs font-semibold uppercase", s.color)}>{s.name}</span>
              <span className="text-xs text-[var(--muted)] font-mono">{(s.prob * 100).toFixed(0)}%</span>
            </div>
            <div className="text-2xl font-mono font-bold text-[var(--text)]">{fmt(s.price)}</div>
            <div className="mt-2 h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
              <div className={cn("h-full rounded-full", s.bg)} style={{ width: `${s.prob * 100}%`, opacity: 0.7 }} />
            </div>
          </div>
        ))}
      </div>
      <div className={cn(
        "p-4 rounded-lg border text-center",
        upside > 20 ? "border-emerald-500/30 bg-emerald-500/5" : "border-amber-500/30 bg-amber-500/5"
      )}>
        <div className="text-xs text-[var(--secondary)] mb-1">Probability-weighted expected value</div>
        <div className="text-3xl font-mono font-bold text-[var(--text)]">{fmt(ev)}</div>
        <div className={cn("text-sm font-mono mt-1", upside > 20 ? "text-emerald-400" : "text-amber-400")}>
          {pct(upside)} risk-adjusted return {upside > 20 ? "— attractive" : "— below 20% threshold"}
        </div>
      </div>
    </div>
  );
}
