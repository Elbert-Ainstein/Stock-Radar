"use client";

import type { ThesisData } from "../types";

const FILTER_LABELS: Record<string, string> = {
  demand_inflecting: "Demand inflecting",
  ceiling_visible: "No ceiling visible",
  best_competitor: "Best competitor",
  complete_chain: "Causal chain complete",
  macro_supportive: "Macro supportive",
};

export default function SetupTab({
  thesis,
  loading,
}: {
  thesis: ThesisData | null;
  loading: boolean;
}) {
  if (loading) return <div className="text-sm text-neutral-400">Loading setup…</div>;
  if (!thesis || !thesis.exists || !thesis.filters) {
    return <div className="text-sm text-neutral-400 italic">No thesis run yet — run thesis to populate filters.</div>;
  }

  const filters = thesis.filters;
  const entries = Object.entries(FILTER_LABELS).map(([key, label]) => ({
    key,
    label,
    pass: filters[key]?.pass ?? false,
    evidence: filters[key]?.evidence ?? "",
  }));
  const passCount = entries.filter((e) => e.pass).length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs uppercase tracking-wider text-neutral-400 font-semibold">Setup Quality</h3>
        <span className="text-[11px] font-mono text-neutral-500">{passCount}/{entries.length} pass</span>
      </div>
      <div className="space-y-2">
        {entries.map((f) => (
          <div
            key={f.key}
            className={`p-3 rounded-md border ${
              f.pass ? "bg-emerald-500/5 border-emerald-500/25" : "bg-red-500/5 border-red-500/25"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-semibold">{f.label}</span>
              <span className={`text-[10px] font-mono uppercase ${f.pass ? "text-emerald-400" : "text-red-400"}`}>
                {f.pass ? "PASS" : "FAIL"}
              </span>
            </div>
            {f.evidence && <p className="text-xs text-neutral-300 leading-snug">{f.evidence}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
