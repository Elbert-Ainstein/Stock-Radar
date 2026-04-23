import { cn, scoreColor } from "./helpers";

// ─── Summary Cards ───

export default function SummaryCards({
  stockCount,
  avgScore,
  totalBullish,
  totalSignals,
  topPick,
}: {
  stockCount: number;
  avgScore: number;
  totalBullish: number;
  totalSignals: number;
  topPick: { ticker: string; score: number } | null;
}) {
  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-lg p-4">
        <div className="text-xs text-[var(--muted)] mb-1">Watchlist</div>
        <div className="text-2xl font-bold font-mono">{stockCount}</div>
        <div className="text-[10px] text-[var(--faint)]">stocks tracked</div>
      </div>
      <div className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-lg p-4">
        <div className="text-xs text-[var(--muted)] mb-1">Avg Score</div>
        <div className={cn("text-2xl font-bold font-mono", scoreColor(avgScore))}>{avgScore.toFixed(1)}</div>
        <div className="text-[10px] text-[var(--faint)]">across watchlist</div>
      </div>
      <div className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-lg p-4">
        <div className="text-xs text-[var(--muted)] mb-1">Bullish Signals</div>
        <div className="text-2xl font-bold font-mono text-[var(--success)]">{totalBullish}<span className="text-[var(--muted)] text-sm">/{totalSignals}</span></div>
        <div className="text-[10px] text-[var(--faint)]">{totalSignals ? ((totalBullish / totalSignals) * 100).toFixed(0) : 0}% positive</div>
      </div>
      <div className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-lg p-4">
        <div className="text-xs text-[var(--muted)] mb-1">Top Pick</div>
        <div className="text-2xl font-bold font-mono text-[var(--accent-muted)]">{topPick?.ticker || "—"}</div>
        <div className="text-[10px] text-[var(--faint)]">score {topPick?.score.toFixed(1) || "—"}</div>
      </div>
    </div>
  );
}
