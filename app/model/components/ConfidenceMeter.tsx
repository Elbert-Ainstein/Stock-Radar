"use client";

import { cn, WEIGHT_MULTIPLIER } from "../helpers";
import type { Criterion } from "../types";

export default function ConfidenceMeter({
  criteria,
  targetPrice,
}: {
  criteria: (Criterion & { met: boolean })[];
  targetPrice: number;
}) {
  if (!criteria.length) return null;

  // 3-state scoring: met = positive, failed = negative, not_yet = neutral (pending)
  const metCount = criteria.filter(c => c.met).length;
  const failedCount = criteria.filter(c => c.status === "failed" && !c.met).length;
  const pendingCount = criteria.length - metCount - failedCount;

  // Score: start at 50% (neutral), go up for met, down for failed, pending stays neutral
  const totalWeight = criteria.reduce((sum, c) => sum + WEIGHT_MULTIPLIER[c.weight], 0);
  const metWeight = criteria.reduce((sum, c) => c.met ? sum + WEIGHT_MULTIPLIER[c.weight] : sum, 0);
  const failedWeight = criteria.reduce((sum, c) => (c.status === "failed" && !c.met) ? sum + WEIGHT_MULTIPLIER[c.weight] : sum, 0);

  const score = totalWeight > 0
    ? 50 + ((metWeight / totalWeight) * 50) - ((failedWeight / totalWeight) * 50)
    : 50;

  // Calculate adjusted target price from criteria impacts
  let adjustedPct = 0;
  criteria.forEach(c => {
    const pct = c.price_impact_pct || 0;
    if (c.price_impact_direction === "down_if_failed") {
      if (c.status === "failed" && !c.met) adjustedPct -= Math.abs(pct);
    } else {
      if (c.met) adjustedPct += pct;
    }
  });
  const adjustedTarget = Math.round(targetPrice * (1 + adjustedPct / 100));
  const totalUpside = criteria
    .filter(c => c.price_impact_direction !== "down_if_failed")
    .reduce((s, c) => s + (c.price_impact_pct || 0), 0);
  const totalDownside = criteria
    .filter(c => c.price_impact_direction === "down_if_failed")
    .reduce((s, c) => s + Math.abs(c.price_impact_pct || 0), 0);

  let tier: string;
  let tierColor: string;
  let action: string;
  if (failedCount === 0 && metCount === 0) {
    tier = "Early Stage";
    tierColor = "text-[var(--accent-muted)]";
    action = "Criteria not yet evaluated \u2014 run pipeline for updates";
  } else if (score >= 80) {
    tier = "High Confidence";
    tierColor = "text-emerald-400";
    action = "Aggressive target achievable \u2014 Hold / Add";
  } else if (score >= 60) {
    tier = "Moderate Confidence";
    tierColor = "text-emerald-300";
    action = "Base target supported \u2014 Hold / Watch";
  } else if (score >= 50) {
    tier = "Monitoring";
    tierColor = "text-amber-300";
    action = `${pendingCount} criteria pending \u2014 track progress each quarter`;
  } else if (score >= 35) {
    tier = "Low Confidence";
    tierColor = "text-amber-400";
    action = "Multiple criteria failing \u2014 Trim or reassess";
  } else {
    tier = "Thesis Broken";
    tierColor = "text-rose-400";
    action = "Re-evaluate or exit position";
  }

  return (
    <div className="p-5 rounded-xl bg-[var(--bg)] border border-[var(--border)]">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className={cn("text-2xl font-bold font-mono", tierColor)}>{tier}</div>
          <div className="text-xs text-[var(--muted)] mt-1">{action}</div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-mono font-bold text-[var(--text)]">{score.toFixed(0)}%</div>
          <div className="text-xs text-[var(--muted)]">
            {metCount} met \u00B7 {failedCount} failed \u00B7 {pendingCount} pending
          </div>
        </div>
      </div>

      {/* Adjusted target price */}
      <div className="mb-4 p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)]">
        <div className="text-[10px] text-[var(--muted)] mb-1">Criteria-adjusted target</div>
        <div className="flex items-baseline gap-3">
          <span className={cn(
            "text-2xl font-mono font-bold",
            adjustedPct > 0 ? "text-emerald-400" : adjustedPct < 0 ? "text-rose-400" : "text-[var(--secondary)]"
          )}>
            ${adjustedTarget.toLocaleString()}
          </span>
          <span className={cn(
            "text-sm font-mono",
            adjustedPct > 0 ? "text-emerald-400" : adjustedPct < 0 ? "text-rose-400" : "text-[var(--muted)]"
          )}>
            {adjustedPct >= 0 ? "+" : ""}{adjustedPct.toFixed(1)}%
          </span>
          <span className="text-xs text-[var(--faint)]">from ${targetPrice.toLocaleString()} base</span>
        </div>
        <div className="flex gap-4 mt-2 text-[10px]">
          <span className="text-emerald-400/70">Upside pool: +{totalUpside}%</span>
          <span className="text-rose-400/70">Risk pool: \u2212{totalDownside}%</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="relative h-3 rounded-full bg-[var(--border)] overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            score >= 80 ? "bg-emerald-400" : score >= 60 ? "bg-emerald-300/70" : score >= 50 ? "bg-[var(--accent-muted)]" : score >= 35 ? "bg-amber-400" : "bg-rose-400"
          )}
          style={{ width: `${score}%` }}
        />
        {/* Threshold markers */}
        {[35, 50, 60, 80].map(t => (
          <div key={t} className="absolute top-0 h-full w-px bg-[var(--faint)]" style={{ left: `${t}%` }} />
        ))}
      </div>
      <div className="flex justify-between text-[9px] text-[var(--faint)] mt-1 relative">
        <span>Broken</span>
        <span style={{ position: "absolute", left: "35%" }}>Low</span>
        <span style={{ position: "absolute", left: "50%" }}>Monitoring</span>
        <span style={{ position: "absolute", left: "60%" }}>Base</span>
        <span>Aggressive</span>
      </div>

      {/* Decision framework */}
      <div className="grid grid-cols-4 gap-2 mt-4">
        {[
          { label: "\u226580%", desc: "Aggressive", range: "Add", active: score >= 80 },
          { label: "60-80%", desc: "Base", range: "Hold", active: score >= 60 && score < 80 },
          { label: "35-60%", desc: "Monitoring", range: "Watch", active: score >= 35 && score < 60 },
          { label: "<35%", desc: "Broken", range: "Exit", active: score < 35 },
        ].map(t => (
          <div key={t.label} className={cn(
            "p-2 rounded-lg border text-center transition-all",
            t.active ? "border-[var(--border-hover)] bg-[var(--hover)]" : "border-[var(--border)] opacity-40"
          )}>
            <div className="text-xs font-mono font-bold text-[var(--secondary)]">{t.label}</div>
            <div className="text-[10px] text-[var(--muted)]">{t.desc}</div>
            <div className="text-[10px] font-semibold text-[var(--secondary)]">{t.range}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
