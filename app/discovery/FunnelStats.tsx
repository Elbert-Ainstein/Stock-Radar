import React from "react";

interface FunnelStatsProps {
  totalCandidates: number;
  shortlistCount: number;
  validatedCount: number;
  promotedCount: number;
}

export default function FunnelStats({
  totalCandidates,
  shortlistCount,
  validatedCount,
  promotedCount,
}: FunnelStatsProps) {
  return (
    <div className="grid grid-cols-5 gap-4 mb-8">
      <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-5">
        <div className="text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1">Universe</div>
        <div className="text-3xl font-mono font-bold text-[var(--text)]">500+</div>
        <div className="text-xs text-[var(--muted)] mt-1">Static + Finviz + Yahoo</div>
      </div>
      <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-5">
        <div className="text-[11px] uppercase tracking-wider text-[var(--muted)] mb-1">Passed Filters</div>
        <div className="text-3xl font-mono font-bold text-[var(--text)]">{totalCandidates || "\u2014"}</div>
        <div className="text-xs text-[var(--muted)] mt-1">RevG &gt;15%, GM &gt;30%, $0.5-100B</div>
      </div>
      <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-5">
        <div className="text-[11px] uppercase tracking-wider text-amber-400 mb-1">Shortlist</div>
        <div className="text-3xl font-mono font-bold text-amber-400">{shortlistCount || "\u2014"}</div>
        <div className="text-xs text-[var(--muted)] mt-1">10x score {"\u2265"} 7.0</div>
      </div>
      <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-5">
        <div className="text-[11px] uppercase tracking-wider text-violet-400 mb-1">AI Validated</div>
        <div className="text-3xl font-mono font-bold text-violet-400">{validatedCount || "\u2014"}</div>
        <div className="text-xs text-[var(--muted)] mt-1">Perplexity + Claude</div>
      </div>
      <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-5">
        <div className="text-[11px] uppercase tracking-wider text-emerald-400 mb-1">Promoted</div>
        <div className="text-3xl font-mono font-bold text-emerald-400">{promotedCount}</div>
        <div className="text-xs text-[var(--muted)] mt-1">Added to watchlist</div>
      </div>
    </div>
  );
}
