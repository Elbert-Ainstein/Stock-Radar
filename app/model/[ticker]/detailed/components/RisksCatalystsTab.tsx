"use client";

import type { ThesisData } from "../types";

export default function RisksCatalystsTab({
  thesis,
  loading,
}: {
  thesis: ThesisData | null;
  loading: boolean;
}) {
  if (loading) return <div className="text-sm text-neutral-400">Loading risks/catalysts…</div>;
  if (!thesis || !thesis.exists) {
    return <div className="text-sm text-neutral-400 italic">No thesis run yet.</div>;
  }

  const risks = thesis.top_risks || [];
  const catalysts = thesis.top_catalysts || [];
  const killTriggers = thesis.kill_triggers || [];

  const fmtImpact = (n: number) => {
    if (!Number.isFinite(n)) return "—";
    if (n === 0) return "$0";
    const sign = n >= 0 ? "+" : "−";
    const abs = Math.abs(n);
    return abs >= 1000 ? `${sign}$${(abs / 1000).toFixed(1)}k` : `${sign}$${abs.toFixed(0)}`;
  };
  const fmtProb = (p: number) => (Number.isFinite(p) ? `${(p * 100).toFixed(0)}%` : "—");

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-xs uppercase tracking-wider text-red-400/80 mb-3 font-semibold">Top Risks</h3>
        {risks.length === 0 ? (
          <p className="text-xs text-neutral-500 italic">No risks recorded.</p>
        ) : (
          <div className="space-y-2">
            {risks.map((r, i) => (
              <div key={i} className="p-3 rounded-md border border-red-500/25 bg-red-500/5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold">{r.name}</span>
                  <span className="text-[10px] font-mono text-red-400 whitespace-nowrap">
                    {fmtProb(r.probability)} · {fmtImpact(r.price_impact)}
                  </span>
                </div>
                {r.early_signal && <p className="text-[11px] text-neutral-400 italic">Watch: {r.early_signal}</p>}
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="text-xs uppercase tracking-wider text-emerald-400/80 mb-3 font-semibold">Top Catalysts</h3>
        {catalysts.length === 0 ? (
          <p className="text-xs text-neutral-500 italic">No catalysts recorded.</p>
        ) : (
          <div className="space-y-2">
            {catalysts.map((c, i) => (
              <div key={i} className="p-3 rounded-md border border-emerald-500/25 bg-emerald-500/5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold">{c.name}</span>
                  <span className="text-[10px] font-mono text-emerald-400 whitespace-nowrap">
                    {fmtProb(c.probability)} · {fmtImpact(c.price_impact)}
                  </span>
                </div>
                {c.confirming_signal && <p className="text-[11px] text-neutral-400 italic">Confirms: {c.confirming_signal}</p>}
              </div>
            ))}
          </div>
        )}
      </div>

      {killTriggers.length > 0 && (
        <div>
          <h3 className="text-xs uppercase tracking-wider text-red-400/80 mb-2 font-semibold">Kill Triggers (sell on)</h3>
          <ul className="space-y-1.5">
            {killTriggers.map((kt, i) => (
              <li key={i} className="text-xs text-neutral-300 pl-4 relative before:content-['•'] before:absolute before:left-0 before:text-red-400">
                {kt}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
