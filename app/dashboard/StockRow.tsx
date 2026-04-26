import type { Stock } from "@/lib/data";
import { cn, scoreColor, scoreBg } from "./helpers";
import Sparkline from "./Sparkline";

// ─── Stock Card (Collapsed) ───

export default function StockRow({
  stock,
  isSelected,
  onClick,
  selectMode = false,
  isChecked = false,
  onCheck,
}: {
  stock: Stock;
  isSelected: boolean;
  onClick: () => void;
  selectMode?: boolean;
  isChecked?: boolean;
  onCheck?: (ticker: string) => void;
}) {
  const bullishCount = stock.signals.filter(s => s.signal === "bullish").length;
  const totalScouts = stock.signals.length;

  return (
    <div
      onClick={selectMode ? () => onCheck?.(stock.ticker) : onClick}
      className={cn(
        "stock-card cursor-pointer border rounded-lg p-3 sm:p-4 mb-2",
        isSelected && !selectMode ? "bg-[var(--card)] border-[var(--accent-muted)]" : "bg-[var(--bg-elevated)] border-[var(--border)]",
        selectMode && isChecked && "border-red-500/40 bg-red-500/5"
      )}
    >
      <div className="flex items-center gap-2 sm:gap-4 flex-wrap sm:flex-nowrap">
        {/* Checkbox (select mode) */}
        {selectMode && (
          <div className="flex-shrink-0" onClick={e => { e.stopPropagation(); onCheck?.(stock.ticker); }}>
            <div className={cn(
              "w-5 h-5 rounded border-2 flex items-center justify-center transition-all",
              isChecked ? "bg-red-500 border-red-500" : "border-[var(--border)] hover:border-[var(--muted)]"
            )}>
              {isChecked && <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2.5 6L5 8.5L9.5 3.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>}
            </div>
          </div>
        )}

        {/* Ticker + Name */}
        <div className="min-w-[100px] sm:min-w-[140px]">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-lg">{stock.ticker}</span>
            {stock.scoreDelta > 0.5 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-400/10 text-emerald-400 border border-emerald-400/20">NEW ↑</span>
            )}
          </div>
          <div className="text-xs text-[var(--muted)] mt-0.5">{stock.name}</div>
        </div>

        {/* Price */}
        <div className="min-w-[80px] sm:min-w-[90px] text-right">
          <div className="font-mono font-semibold">${stock.price.toFixed(2)}</div>
          <div className={cn("text-xs font-mono", stock.change >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]")}>
            {stock.change >= 0 ? "+" : ""}{stock.change.toFixed(2)} ({stock.changePct >= 0 ? "+" : ""}{stock.changePct.toFixed(2)}%)
          </div>
        </div>

        {/* Score */}
        <div className="min-w-[80px] text-center">
          <div className={cn("font-mono text-2xl font-bold", scoreColor(stock.score))}>{stock.score.toFixed(1)}</div>
          <div className="text-[10px] text-[var(--muted)]">
            {stock.scoreDelta > 0 && <span className="text-[var(--success)]">↑{stock.scoreDelta.toFixed(1)}</span>}
            {stock.scoreDelta < 0 && <span className="text-[var(--danger)]">↓{Math.abs(stock.scoreDelta).toFixed(1)}</span>}
            {stock.scoreDelta === 0 && <span className="text-[var(--muted)]">—</span>}
          </div>
        </div>

        {/* Score bar */}
        <div className="hidden md:block flex-1 min-w-[100px] max-w-[200px]">
          <div className="w-full h-2 bg-[var(--border)] rounded-full overflow-hidden">
            <div className={cn("h-full rounded-full score-bar", scoreBg(stock.score))} style={{ width: `${stock.score * 10}%`, opacity: 0.7 }} />
          </div>
          <div className="flex justify-between text-[10px] text-[var(--faint)] mt-1">
            <span>0</span>
            <span>10</span>
          </div>
        </div>

        {/* Scout convergence + data completeness */}
        <div className="hidden lg:block min-w-[80px] text-center">
          <div className="text-sm">
            <span className="text-[var(--success)] font-mono font-semibold">{bullishCount}</span>
            <span className="text-[var(--muted)]">/{totalScouts}</span>
          </div>
          <div className="text-[10px] text-[var(--muted)]">scouts bullish</div>
          {stock.dataQuality && (
            <div
              className={cn(
                "text-[10px] font-mono mt-0.5 px-1 py-0.5 rounded",
                stock.dataQuality.confidence === "high"
                  ? "text-emerald-400 bg-emerald-400/10"
                  : stock.dataQuality.confidence === "medium"
                  ? "text-yellow-400 bg-yellow-400/10"
                  : "text-amber-400 bg-amber-400/10"
              )}
              title={[
                stock.dataQuality.confidence_score
                  ? `Confidence: ${(stock.dataQuality.confidence_score * 100).toFixed(0)}%`
                  : null,
                ...(stock.dataQuality.warnings || []),
              ].filter(Boolean).join("\n") || "Full scout coverage"}
            >
              {stock.dataQuality.scouts_scored}/{stock.dataQuality.scouts_total} data
              {stock.dataQuality.confidence_score > 0 && (
                <span className="ml-1 opacity-70">
                  {(stock.dataQuality.confidence_score * 100).toFixed(0)}%
                </span>
              )}
            </div>
          )}
        </div>

        {/* Sparkline */}
        <div className="hidden lg:block min-w-[120px]">
          <Sparkline data={stock.scoreHistory} color={stock.scoreDelta >= 0 ? "#34d399" : "#f43f5e"} />
        </div>

        {/* Sector tag */}
        <div className="hidden sm:block min-w-[80px] lg:min-w-[120px] text-right">
          <span className="text-[10px] px-2 py-1 rounded-full bg-[var(--border)] text-[var(--secondary)]">{stock.sector}</span>
        </div>
      </div>
    </div>
  );
}
