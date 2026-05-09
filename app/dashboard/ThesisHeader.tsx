"use client";

import type { ThesisRun } from "@/lib/data";
import { cn } from "./helpers";
import ThesisRerunButton from "./ThesisRerunButton";

const CONVICTION_STYLE: Record<string, string> = {
  HIGH:    "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  MEDIUM:  "bg-yellow-500/10 text-yellow-300 border-yellow-500/25",
  LOW:     "bg-orange-500/10 text-orange-300 border-orange-500/25",
  BROKEN:  "bg-red-500/15 text-red-400 border-red-500/30",
};

function fmtPrice(n: number | null, currency = "USD"): string {
  if (n == null) return "—";
  const sym = currency === "HKD" ? "HK$" : currency === "EUR" ? "€" : "$";
  return `${sym}${n.toLocaleString(undefined, { maximumFractionDigits: n >= 100 ? 0 : 2 })}`;
}

function fmtPct(n: number | null): string {
  if (n == null) return "—";
  return `${n.toFixed(0)}%`;
}

export function ConvictionBadge({ conviction }: { conviction: string | null }) {
  if (!conviction) return null;
  const cls = CONVICTION_STYLE[conviction] || "bg-[var(--border)] text-[var(--muted)] border-[var(--border)]";
  return (
    <span className={cn("text-[10px] px-1.5 py-0.5 rounded border font-mono uppercase tracking-wider", cls)}>
      {conviction}
    </span>
  );
}

/**
 * Compact destination + conviction inline. Used in the StockRow card.
 * Renders nothing if no thesis exists — caller should render an empty state.
 */
export function ThesisInline({
  thesis,
  currency = "USD",
}: {
  thesis: ThesisRun | null | undefined;
  currency?: string;
}) {
  if (!thesis || thesis.thesis_target == null) return null;
  return (
    <div className="flex flex-col items-end gap-0.5">
      <div className="flex items-center gap-1.5">
        <span className="text-[9px] text-[var(--muted)] uppercase tracking-wider">Destination</span>
        <ConvictionBadge conviction={thesis.conviction} />
      </div>
      <div className="font-mono font-bold text-base text-emerald-400">
        {fmtPrice(thesis.thesis_target, currency)}
      </div>
    </div>
  );
}

/**
 * Full destination/floor/breakout/conviction header for the detail panel.
 */
export function ThesisHeaderPanel({
  thesis,
  currency = "USD",
  spotPrice,
  ticker,
  onRerunComplete,
}: {
  thesis: ThesisRun | null | undefined;
  currency?: string;
  spotPrice?: number;
  ticker: string;
  onRerunComplete?: () => void;
}) {
  if (!thesis) {
    return (
      <div className="mb-6 p-4 rounded-lg border border-dashed border-[var(--border)] bg-[var(--hover)]/30">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h3 className="text-xs uppercase tracking-wider text-[var(--accent-muted)] mb-1 font-semibold">Thesis</h3>
            <p className="text-sm text-[var(--muted)]">
              No thesis run on file for {ticker}. Trigger one to see destination, conviction, risks, catalysts.
            </p>
          </div>
          <ThesisRerunButton ticker={ticker} onComplete={onRerunComplete} />
        </div>
      </div>
    );
  }

  const upsideToThesis =
    thesis.thesis_target && spotPrice
      ? ((thesis.thesis_target - spotPrice) / spotPrice) * 100
      : null;

  const filterPasses = thesis.filters
    ? Object.values(thesis.filters).filter((f) => f?.pass).length
    : 0;
  const filterTotal = thesis.filters ? Object.keys(thesis.filters).length : 5;

  return (
    <div className="mb-6 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)]">
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <h3 className="text-xs uppercase tracking-wider text-[var(--accent-muted)] font-semibold">
            Thesis · {thesis.prompt_version}
          </h3>
          <ConvictionBadge conviction={thesis.conviction} />
        </div>
        <ThesisRerunButton
          ticker={ticker}
          lastRunAt={thesis.run_at}
          onComplete={onRerunComplete}
        />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div>
          <div className="text-[9px] text-[var(--muted)] uppercase tracking-wider">Destination</div>
          <div className="font-mono font-bold text-xl text-emerald-400">
            {fmtPrice(thesis.thesis_target, currency)}
          </div>
          {upsideToThesis !== null && (
            <div
              className={cn(
                "text-[10px] font-mono",
                upsideToThesis >= 0 ? "text-emerald-400" : "text-red-400",
              )}
            >
              {upsideToThesis >= 0 ? "+" : ""}
              {upsideToThesis.toFixed(0)}%
            </div>
          )}
        </div>
        <div>
          <div className="text-[9px] text-[var(--muted)] uppercase tracking-wider">Breakout</div>
          <div className="font-mono font-bold text-xl text-emerald-300/80">
            {fmtPrice(thesis.breakout_price, currency)}
          </div>
        </div>
        <div>
          <div className="text-[9px] text-[var(--muted)] uppercase tracking-wider">Risk-adj</div>
          <div className="font-mono font-bold text-base text-[var(--text)]/80">
            {fmtPrice(thesis.risk_adj_target, currency)}
          </div>
        </div>
        <div>
          <div className="text-[9px] text-[var(--muted)] uppercase tracking-wider">Floor (DCF)</div>
          <div className="font-mono font-bold text-base text-yellow-400/80">
            {/* The DCF floor lives in the analysis row, not the thesis. We surface
                it in the existing engine card below. Show spot here as a comparison. */}
            {fmtPrice(spotPrice ?? null, currency)}
          </div>
          <div className="text-[9px] text-[var(--muted)]">spot</div>
        </div>
        <div>
          <div className="text-[9px] text-[var(--muted)] uppercase tracking-wider">Position</div>
          <div className="font-mono font-bold text-base text-[var(--text)]">
            {fmtPct(thesis.position_size_pct)}
          </div>
          <div className="text-[9px] text-[var(--muted)]">
            buy ≤{fmtPrice(thesis.buy_below, currency)} · trim ≥{fmtPrice(thesis.trim_above, currency)}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-3 text-[10px] text-[var(--muted)]">
        <span>
          Setup <span className="font-mono text-[var(--text)]">{filterPasses}/{filterTotal}</span> filters
        </span>
        {thesis.coverage_quality && (
          <span>
            Coverage <span className="font-mono text-[var(--text)]">{thesis.coverage_quality}</span>
          </span>
        )}
        <span>
          Run <span className="font-mono text-[var(--text)]">
            {new Date(thesis.run_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
          </span>
        </span>
        {thesis.trigger_reason && (
          <span className="opacity-60">via {thesis.trigger_reason}</span>
        )}
      </div>
    </div>
  );
}
