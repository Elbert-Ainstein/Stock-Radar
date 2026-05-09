"use client";

import type { ThesisData } from "../types";

const CONVICTION_COLOR: Record<string, string> = {
  HIGH: "text-emerald-400",
  MEDIUM: "text-yellow-300",
  LOW: "text-orange-300",
  BROKEN: "text-red-400",
};

export default function ThesisTab({
  thesis,
  loading,
}: {
  thesis: ThesisData | null;
  loading: boolean;
}) {
  if (loading) return <div className="text-sm text-neutral-400">Loading thesis…</div>;
  if (!thesis || !thesis.exists || !thesis.thesis_target) {
    return (
      <div className="rounded-lg border border-dashed border-neutral-700 bg-neutral-900/40 p-6">
        <h3 className="text-sm uppercase tracking-wider text-neutral-400 mb-2 font-semibold">No thesis yet</h3>
        <p className="text-sm text-neutral-300">
          Run the thesis pipeline to populate this tab. The thesis is the headline
          conviction view; the Floor (DCF) tab below is the conservative anchor.
        </p>
      </div>
    );
  }

  const fmt = (n: number | null | undefined) =>
    n == null ? "—" : "$" + n.toLocaleString(undefined, { maximumFractionDigits: n >= 100 ? 0 : 2 });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
          <div className="text-[10px] uppercase tracking-wider text-emerald-400/80 font-semibold mb-1">Destination</div>
          <div className="text-2xl font-mono font-bold text-emerald-400">{fmt(thesis.thesis_target)}</div>
        </div>
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
          <div className="text-[10px] uppercase tracking-wider text-emerald-400/60 font-semibold mb-1">Breakout</div>
          <div className="text-2xl font-mono font-bold text-emerald-300/80">{fmt(thesis.breakout_price)}</div>
        </div>
        <div className="rounded-lg border border-neutral-700 bg-neutral-900/40 p-4">
          <div className="text-[10px] uppercase tracking-wider text-neutral-400 font-semibold mb-1">Risk-adj</div>
          <div className="text-2xl font-mono font-bold text-neutral-200">{fmt(thesis.risk_adj_target)}</div>
        </div>
        <div className="rounded-lg border border-neutral-700 bg-neutral-900/40 p-4">
          <div className="text-[10px] uppercase tracking-wider text-neutral-400 font-semibold mb-1">Conviction</div>
          <div className={`text-xl font-mono font-bold ${CONVICTION_COLOR[thesis.conviction || ""] || "text-neutral-200"}`}>
            {thesis.conviction || "—"}
          </div>
          <div className="text-[10px] text-neutral-500 mt-1">
            {thesis.position_size_pct != null ? `${thesis.position_size_pct}% position` : ""}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div className="rounded-lg border border-neutral-800 p-3">
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 mb-1">Buy below</div>
          <div className="font-mono">{fmt(thesis.buy_below)}</div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-3">
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 mb-1">Trim above</div>
          <div className="font-mono">{fmt(thesis.trim_above)}</div>
        </div>
      </div>

      <div className="text-[11px] text-neutral-500 flex flex-wrap gap-3">
        {thesis.prompt_version && <span>Prompt {thesis.prompt_version}</span>}
        {thesis.run_at && <span>Run {new Date(thesis.run_at).toLocaleString()}</span>}
        {thesis.coverage_quality && <span>Coverage {thesis.coverage_quality}</span>}
        {thesis.trigger_reason && <span>via {thesis.trigger_reason}</span>}
      </div>

      {thesis.markdown_path && (
        <p className="text-xs text-neutral-400 italic">
          Full markdown analysis: <code className="px-1 py-0.5 rounded bg-neutral-800 text-neutral-300">{thesis.markdown_path}</code>
        </p>
      )}
    </div>
  );
}
