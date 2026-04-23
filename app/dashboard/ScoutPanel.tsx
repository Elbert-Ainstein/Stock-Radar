import type { ScoutInfo } from "./types";
import { cn } from "./helpers";

// ─── Scout Status Panel ───

export default function ScoutPanel({
  scoutDetails,
  scoutAccuracy,
  feedbackLoaded,
  formatTime,
}: {
  scoutDetails: ScoutInfo[];
  scoutAccuracy: any[];
  feedbackLoaded: boolean;
  formatTime: (iso: string) => string;
}) {
  return (
    <div className="border-b border-[var(--border)] bg-[var(--bg-elevated)]">
      <div className="max-w-[1400px] mx-auto px-6 py-4">
        <div className="grid grid-cols-3 gap-3">
          {scoutDetails.map(scout => {
            const isActive = scout.signalCount > 0;
            return (
              <div
                key={scout.name}
                className={cn(
                  "p-3 rounded-lg border",
                  isActive
                    ? "bg-[var(--success-bg)] border-[var(--success)]/20"
                    : "bg-[var(--bg)] border-[var(--border)] opacity-60"
                )}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={cn("w-2 h-2 rounded-full", isActive ? "bg-[var(--success)]" : "bg-[var(--muted)]")} />
                  <span className="text-xs font-medium text-[var(--text)]">{scout.name}</span>
                  {scout.requiresKey && !isActive && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400 border border-amber-400/20">API key needed</span>
                  )}
                </div>
                <div className="text-[10px] text-[var(--muted)]">
                  {isActive
                    ? `${scout.signalCount} signals · ${scout.generatedAt ? formatTime(scout.generatedAt) : "—"}`
                    : scout.requiresKey
                      ? "Not configured — add API key to .env"
                      : "No data yet — run pipeline"
                  }
                </div>
              </div>
            );
          })}
        </div>

        {/* Scout Accuracy (Feedback Loop) */}
        {scoutAccuracy.length > 0 && (() => {
          const acc30 = scoutAccuracy.filter((a: any) => a.window_days === 30);
          if (acc30.length === 0) return null;
          return (
            <div className="mt-4 pt-4 border-t border-[var(--border)]">
              <h4 className="text-[10px] uppercase tracking-wider text-[var(--accent-muted)] font-semibold mb-3">
                Scout Accuracy — 30-Day Track Record
              </h4>
              <div className="grid grid-cols-3 gap-2">
                {acc30.map((a: any) => {
                  const acc = a.accuracy_pct || 0;
                  const total = a.total_signals || 0;
                  const barColor = acc >= 60 ? "bg-[var(--success)]" : acc >= 50 ? "bg-amber-400" : "bg-[var(--danger)]";
                  const textColor = acc >= 60 ? "text-[var(--success)]" : acc >= 50 ? "text-amber-400" : "text-[var(--danger)]";
                  return (
                    <div key={a.scout} className="p-2 rounded-lg bg-[var(--bg)] border border-[var(--border)]">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] font-medium text-[var(--text)] capitalize">{a.scout}</span>
                        <span className={cn("text-[11px] font-mono font-bold", textColor)}>{acc.toFixed(1)}%</span>
                      </div>
                      <div className="w-full h-1 bg-[var(--border)] rounded-full overflow-hidden mb-1">
                        <div className={cn("h-full rounded-full", barColor)} style={{ width: `${Math.min(100, acc)}%` }} />
                      </div>
                      <div className="flex justify-between text-[9px] text-[var(--muted)]">
                        <span>{a.hits}/{total} hits</span>
                        <span>avg {(a.avg_return_pct || 0) >= 0 ? "+" : ""}{(a.avg_return_pct || 0).toFixed(1)}%</span>
                      </div>
                      {(a.bullish_accuracy > 0 || a.bearish_accuracy > 0) && (
                        <div className="flex gap-2 mt-1 text-[9px]">
                          {a.bullish_accuracy > 0 && <span className="text-emerald-400">▲ {a.bullish_accuracy.toFixed(0)}%</span>}
                          {a.bearish_accuracy > 0 && <span className="text-rose-400">▼ {a.bearish_accuracy.toFixed(0)}%</span>}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="text-[9px] text-[var(--faint)] mt-2">
                Accuracy = did the signal direction (bullish/bearish) match the actual 30-day price movement? Weights auto-adjust when enough data accumulates.
              </p>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
