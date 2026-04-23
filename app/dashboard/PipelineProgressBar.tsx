import type { PipelineProgress } from "./types";

// ─── Pipeline Progress Bar (Global) ───

export default function PipelineProgressBar({ progress, onDismiss }: { progress: PipelineProgress | null; onDismiss?: () => void }) {
  const stageLabels: Record<string, string> = {
    quant: "Quant Screener",
    insider: "Insider Tracker",
    social: "Social Sentiment",
    news: "News Scanner",
    fundamentals: "Fundamentals",
    youtube: "YouTube Intel",
    analyst: "Analyst Scoring",
    model: "Model Generation",
    complete: "Complete",
    error: "Error",
    queued: "Queued Stocks",
  };

  const pct = progress?.percent ?? 0;
  const stageName = progress ? (stageLabels[progress.stage] || progress.stage) : "Starting...";
  const msg = progress?.message || "Initializing pipeline...";

  return (
    <div className="border-b border-[var(--accent-muted)]/30 bg-[var(--bg-elevated)]">
      <div className="max-w-[1400px] mx-auto px-6 py-3">
        <div className="flex items-center gap-3 mb-2">
          <span className="w-3 h-3 border-[1.5px] border-[var(--accent-muted)] border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-semibold text-[var(--text)]">Pipeline Running</span>
          <span className="text-[10px] text-[var(--muted)]">·</span>
          <span className="text-[10px] font-mono text-[var(--accent-muted)]">{stageName}</span>
          {progress && (
            <span className="text-[10px] text-[var(--muted)] ml-auto">
              Stage {progress.current}/{progress.total}
            </span>
          )}
        </div>
        {/* Progress bar */}
        <div className="w-full h-1.5 bg-[var(--border)] rounded-full overflow-hidden mb-1.5">
          <div
            className="h-full rounded-full transition-all duration-700 ease-out"
            style={{
              width: `${Math.max(pct, 3)}%`,
              background: "linear-gradient(90deg, var(--accent-muted), #a78bfa)",
            }}
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-[var(--secondary)]">{msg}</span>
          <span className="text-[10px] font-mono text-[var(--muted)]">{pct}%</span>
        </div>
      </div>
    </div>
  );
}
