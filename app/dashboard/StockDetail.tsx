import type { Stock } from "@/lib/data";
import { cn, scoreColor, signalBg, signalColor, signalIcon, aiColor } from "./helpers";

// ─── Stock Detail Panel ───

export default function StockDetail({ stock, onDelete }: { stock: Stock; onDelete: () => void }) {
  return (
    <div className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-lg p-4 sm:p-6 mt-2 mb-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold font-mono">{stock.ticker} <span className="text-[var(--muted)] text-base sm:text-lg font-normal">{stock.name}</span></h2>
          <div className="flex gap-2 mt-2">
            {stock.tags.map(t => (
              <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--hover)] text-[var(--accent-muted)] border border-[var(--border)]">{t}</span>
            ))}
          </div>
        </div>
        <div className="flex items-start gap-4">
          <div className="text-right">
            <div className={cn("text-4xl font-mono font-bold", scoreColor(stock.score))}>{stock.score.toFixed(1)}</div>
            <div className="text-xs text-[var(--muted)] mt-1">Composite Score</div>
          </div>
          <button
            onClick={onDelete}
            className="text-[var(--muted)] hover:text-[var(--danger)] transition-colors p-1.5 rounded-md hover:bg-[var(--danger-bg)]"
            title={`Remove ${stock.ticker} from watchlist`}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 4h10M6.5 4V3a1 1 0 011-1h1a1 1 0 011 1v1M5.5 7v4.5M8 7v4.5M10.5 7v4.5M4.5 4l.5 8.5a1 1 0 001 1h4a1 1 0 001-1L11.5 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
        </div>
      </div>

      {/* Thesis */}
      {stock.thesis && (
        <div className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-[var(--accent-muted)] mb-2 font-semibold">10x Thesis</h3>
          <p className="text-sm text-[var(--secondary)] leading-relaxed">{stock.thesis}</p>
        </div>
      )}

      {/* Kill Condition */}
      {stock.killCondition && (() => {
        const kEval = stock.killConditionEval;
        const kStatus = kEval?.status || "unchecked";
        const statusBadge = kStatus === "triggered"
          ? { label: "THESIS BREAK", cls: "bg-red-500/20 text-red-400 border-red-500/40" }
          : kStatus === "warning"
          ? { label: "WATCH", cls: "bg-yellow-500/20 text-yellow-400 border-yellow-500/40" }
          : kStatus === "safe"
          ? { label: "SAFE", cls: "bg-green-500/15 text-green-400 border-green-500/30" }
          : null;
        return (
          <div className={cn("mb-6 p-3 rounded-lg border",
            kStatus === "triggered" ? "bg-red-500/10 border-red-500/30" :
            kStatus === "warning" ? "bg-yellow-500/10 border-yellow-500/30" :
            "bg-[var(--danger-bg)] border-[var(--danger)]/15"
          )}>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-xs uppercase tracking-wider text-[var(--danger)] font-semibold">Kill Condition</h3>
              {statusBadge && (
                <span className={cn("text-[9px] px-1.5 py-0.5 rounded border font-mono", statusBadge.cls)}>
                  {statusBadge.label}
                </span>
              )}
            </div>
            <p className="text-sm text-[var(--secondary)]">{stock.killCondition}</p>
            {kEval?.reasoning && kStatus !== "safe" && (
              <p className="text-[11px] text-[var(--muted)] mt-2 italic">{kEval.reasoning}</p>
            )}
          </div>
        );
      })()}

      {/* Scout Signals */}
      <div className="mb-6">
        <h3 className="text-xs uppercase tracking-wider text-[var(--accent-muted)] mb-3 font-semibold">Scout Signals</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {stock.signals.map((sig, i) => (
            <div key={i} className={cn("p-3 rounded-lg border", signalBg(sig.signal))}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className={cn("text-xs font-bold", signalColor(sig.signal))}>{signalIcon(sig.signal)}</span>
                  <span className="text-xs font-semibold" style={{ color: aiColor(sig.ai) }}>{sig.scout}</span>
                  <span className="text-[10px] text-[var(--muted)]">via {sig.ai}</span>
                </div>
                <span className={cn("text-[10px] font-mono uppercase font-semibold", signalColor(sig.signal))}>{sig.signal}</span>
              </div>
              <p className="text-xs text-[var(--secondary)] leading-relaxed">{sig.summary}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Catalysts */}
      {stock.catalysts.length > 0 && (
        <div className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-[var(--secondary)] mb-2 font-semibold">Upcoming Catalysts</h3>
          <div className="flex flex-wrap gap-2">
            {stock.catalysts.map((c, i) => (
              <span key={i} className="text-xs px-3 py-1.5 rounded-lg bg-[var(--hover)] border border-[var(--border)] text-[var(--secondary)]">{c}</span>
            ))}
          </div>
        </div>
      )}

      {/* Target Price Model Links */}
      <div className="pt-4 border-t border-[var(--border)] flex flex-wrap gap-2">
        <a
          href={`/model?ticker=${stock.ticker}`}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--hover)] border border-[var(--border)] text-[var(--text)] hover:bg-[var(--card)] hover:border-[var(--border-hover)] transition-all text-sm font-semibold"
        >
          <span>📐</span>
          <span>Brief Model</span>
          <span className="text-xs font-mono opacity-60">→ Sliders · Scenarios</span>
        </a>
        <a
          href={`/model/${stock.ticker}/detailed`}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-400/10 border border-emerald-400/30 text-emerald-400 hover:bg-emerald-400/15 hover:border-emerald-400/50 transition-all text-sm font-semibold"
        >
          <span>📊</span>
          <span>Detailed Model</span>
          <span className="text-xs font-mono opacity-70">→ Full workbook</span>
        </a>
      </div>
    </div>
  );
}
