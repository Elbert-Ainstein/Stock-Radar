"use client";

import type { ThesisRun } from "@/lib/data";
import { cn } from "./helpers";

const FILTER_LABELS: Record<string, string> = {
  demand_inflecting: "Demand inflecting",
  ceiling_visible: "No ceiling visible",
  best_competitor: "Best competitor",
  complete_chain: "Causal chain complete",
  macro_supportive: "Macro supportive",
};

function currencySymbol(currency: string): string {
  if (currency === "HKD") return "HK$";
  if (currency === "EUR") return "€";
  if (currency === "GBP") return "£";
  if (currency === "JPY") return "¥";
  return "$";
}

function fmtPriceImpact(n: number | null | undefined, currency = "USD"): string {
  const sym = currencySymbol(currency);
  // Guard against null/undefined/NaN — Supabase nulls coerce to undefined
  // through the TypeScript number type at runtime.
  if (n == null || !Number.isFinite(n)) return "—";
  if (n === 0) return `${sym}0`;
  const abs = Math.abs(n);
  const sign = n >= 0 ? "+" : "−";
  if (abs >= 1000) return `${sign}${sym}${(abs / 1000).toFixed(1)}k`;
  return `${sign}${sym}${abs.toFixed(0)}`;
}

function fmtProb(p: number | null | undefined): string {
  if (p == null || !Number.isFinite(p)) return "—";
  return `${(p * 100).toFixed(0)}%`;
}

export default function SetupAndRisks({
  thesis,
  currency = "USD",
}: {
  thesis: ThesisRun;
  currency?: string;
}) {
  const filters = thesis.filters || {};
  const filterEntries = Object.entries(FILTER_LABELS).map(([key, label]) => ({
    key,
    label,
    pass: filters[key]?.pass ?? false,
    evidence: filters[key]?.evidence ?? "",
  }));
  const filterPassCount = filterEntries.filter((f) => f.pass).length;

  const risks = (thesis.top_risks || []).slice(0, 3);
  const catalysts = (thesis.top_catalysts || []).slice(0, 3);
  const killTriggers = thesis.kill_triggers || [];

  return (
    <>
      {/* Setup Quality */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs uppercase tracking-wider text-[var(--accent-muted)] font-semibold">
            Setup Quality
          </h3>
          <span className="text-[10px] font-mono text-[var(--muted)]">
            {filterPassCount}/{filterEntries.length} pass
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {filterEntries.map((f) => (
            <div
              key={f.key}
              className={cn(
                "p-2.5 rounded-md border text-xs",
                f.pass
                  ? "bg-emerald-500/5 border-emerald-500/25"
                  : "bg-red-500/5 border-red-500/25",
              )}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[var(--text)]">{f.label}</span>
                <span
                  className={cn(
                    "text-[10px] font-mono uppercase",
                    f.pass ? "text-emerald-400" : "text-red-400",
                  )}
                >
                  {f.pass ? "PASS" : "FAIL"}
                </span>
              </div>
              {f.evidence && (
                <p className="text-[11px] text-[var(--secondary)] leading-snug line-clamp-3">
                  {f.evidence}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Risks + Catalysts (side by side on wide screens) */}
      <div className="mb-6 grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Top Risks */}
        <div>
          <h3 className="text-xs uppercase tracking-wider text-red-400/80 mb-2 font-semibold">
            Top Risks (thesis-breaking)
          </h3>
          <div className="space-y-2">
            {risks.length === 0 ? (
              <p className="text-xs text-[var(--muted)] italic">No risks recorded.</p>
            ) : (
              risks.map((r, i) => (
                <div
                  key={i}
                  className="p-2.5 rounded-md border border-red-500/20 bg-red-500/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-[var(--text)] flex-1">
                      {r.name}
                    </span>
                    <span className="text-[10px] font-mono text-red-400 whitespace-nowrap">
                      {fmtProb(r.probability)} · {fmtPriceImpact(r.price_impact, currency)}
                    </span>
                  </div>
                  {r.early_signal && (
                    <p className="text-[11px] text-[var(--muted)] mt-1 italic">
                      Watch: {r.early_signal}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
        {/* Top Catalysts */}
        <div>
          <h3 className="text-xs uppercase tracking-wider text-emerald-400/80 mb-2 font-semibold">
            Top Catalysts (thesis-extending)
          </h3>
          <div className="space-y-2">
            {catalysts.length === 0 ? (
              <p className="text-xs text-[var(--muted)] italic">No catalysts recorded.</p>
            ) : (
              catalysts.map((c, i) => (
                <div
                  key={i}
                  className="p-2.5 rounded-md border border-emerald-500/20 bg-emerald-500/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-[var(--text)] flex-1">
                      {c.name}
                    </span>
                    <span className="text-[10px] font-mono text-emerald-400 whitespace-nowrap">
                      {fmtProb(c.probability)} · {fmtPriceImpact(c.price_impact, currency)}
                    </span>
                  </div>
                  {c.confirming_signal && (
                    <p className="text-[11px] text-[var(--muted)] mt-1 italic">
                      Confirms: {c.confirming_signal}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Kill Triggers */}
      {killTriggers.length > 0 && (
        <div className="mb-6">
          <h3 className="text-xs uppercase tracking-wider text-red-400/80 mb-2 font-semibold">
            Kill Triggers (sell on)
          </h3>
          <ul className="space-y-1.5">
            {killTriggers.map((kt, i) => (
              <li
                key={i}
                className="text-xs text-[var(--secondary)] pl-4 relative before:content-['•'] before:absolute before:left-0 before:text-red-400"
              >
                {kt}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
