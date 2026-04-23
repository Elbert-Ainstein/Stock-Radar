"use client";

import { useState } from "react";
import { cn, WEIGHT_DOT, WEIGHT_LABEL, VAR_LABELS } from "../helpers";
import type { Criterion } from "../types";

export default function CriteriaChecklist({
  criteria,
  onToggle,
  targetPrice,
}: {
  criteria: (Criterion & { met: boolean })[];
  onToggle: (id: string) => void;
  targetPrice: number;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!criteria.length) return null;

  return (
    <div className="space-y-1.5">
      {criteria.map(c => {
        const impactPct = c.price_impact_pct || 0;
        const isDownRisk = c.price_impact_direction === "down_if_failed";
        const impactDollar = Math.round(targetPrice * Math.abs(impactPct) / 100);
        const isExpanded = expandedId === c.id;
        const progress = c.progress_pct;
        const autoStatus = c.evaluation_note ? c.status : null;

        // Determine display status: auto-eval overrides manual if available
        const effectivelyMet = autoStatus === "met" || c.met;
        const effectivelyFailed = autoStatus === "failed" && !c.met;

        return (
          <div key={c.id} className="rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden">
            {/* Header row */}
            <div
              className={cn(
                "p-3.5 cursor-pointer transition-all hover:bg-[var(--hover)]",
                effectivelyMet && "bg-[var(--success-bg)]"
              )}
              onClick={() => onToggle(c.id)}
            >
              <div className="flex items-center gap-3">
                {/* Checkbox */}
                <div className={cn(
                  "w-[18px] h-[18px] rounded border-[1.5px] flex items-center justify-center flex-shrink-0 transition-all",
                  effectivelyMet ? "bg-[var(--text)] border-[var(--text)]" : "border-[var(--muted)]"
                )}>
                  {effectivelyMet && <span className="text-[9px] text-[var(--bg)] font-bold">{"\u2713"}</span>}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn("text-[13px] font-medium truncate", effectivelyMet ? "text-[var(--text)] line-through opacity-60" : "text-[var(--text)]")}>
                      {c.label}
                    </span>
                    <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", WEIGHT_DOT[c.weight])} title={WEIGHT_LABEL[c.weight]} />
                  </div>
                </div>
                {/* Price impact */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {impactPct !== 0 && (
                    <span className={cn(
                      "text-[10px] font-mono tabular-nums",
                      effectivelyMet && !isDownRisk ? "text-[var(--text)]" : effectivelyFailed && isDownRisk ? "text-[var(--danger)]" : "text-[var(--muted)]"
                    )}>
                      {isDownRisk ? `\u2212$${impactDollar}` : `+$${impactDollar}`}
                    </span>
                  )}
                  {/* Expand toggle */}
                  <button
                    onClick={(e) => { e.stopPropagation(); setExpandedId(isExpanded ? null : c.id); }}
                    className="text-[var(--muted)] hover:text-[var(--text)] transition-colors p-0.5"
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className={cn("transition-transform", isExpanded && "rotate-180")}>
                      <path d="M3.5 5.25L7 8.75L10.5 5.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                </div>
              </div>

              {/* Progress bar (mini, always visible) */}
              {progress != null && !effectivelyMet && (
                <div className="mt-2 ml-[30px]">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1 rounded-full bg-[var(--border)] overflow-hidden">
                      <div className="h-full rounded-full bg-[var(--muted)] transition-all duration-500" style={{ width: `${progress}%` }} />
                    </div>
                    <span className="text-[9px] font-mono text-[var(--muted)] tabular-nums">{progress.toFixed(0)}%</span>
                  </div>
                </div>
              )}
            </div>

            {/* Expanded detail panel */}
            {isExpanded && (
              <div className="px-3.5 pb-3.5 border-t border-[var(--border)]">
                <div className="pt-3 space-y-3">
                  {/* Description */}
                  <p className="text-[11px] text-[var(--secondary)] leading-relaxed">{c.detail}</p>

                  {/* Progress report */}
                  <div className="p-3 rounded-lg bg-[var(--bg)]">
                    <div className="text-[10px] font-medium text-[var(--muted)] uppercase tracking-wider mb-2">Progress</div>
                    {c.current_label && c.target_label ? (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-[12px]">
                          <span className="text-[var(--secondary)]">Current: <span className="font-mono font-medium text-[var(--text)]">{c.current_label}</span></span>
                          <span className="text-[var(--secondary)]">Target: <span className="font-mono font-medium text-[var(--text)]">{c.target_label}</span></span>
                        </div>
                        {progress != null && (
                          <div>
                            <div className="h-2 rounded-full bg-[var(--border)] overflow-hidden">
                              <div
                                className={cn(
                                  "h-full rounded-full transition-all duration-700",
                                  progress >= 100 ? "bg-[var(--text)]" : progress >= 70 ? "bg-[var(--secondary)]" : "bg-[var(--muted)]"
                                )}
                                style={{ width: `${Math.min(progress, 100)}%` }}
                              />
                            </div>
                            <div className="flex justify-between mt-1 text-[9px] text-[var(--muted)]">
                              <span>0%</span>
                              <span className="font-mono font-medium">{progress.toFixed(1)}% complete</span>
                              <span>100%</span>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-[11px] text-[var(--muted)]">
                        {c.evaluation_note || "No data yet \u2014 run the pipeline to collect metrics."}
                      </p>
                    )}
                    {c.evaluation_note && c.current_label && (
                      <p className="text-[10px] text-[var(--secondary)] mt-2 leading-relaxed">{c.evaluation_note}</p>
                    )}
                  </div>

                  {/* Relevant news */}
                  {c.relevant_news && c.relevant_news.length > 0 && (
                    <div className="p-3 rounded-lg bg-[var(--bg)]">
                      <div className="text-[10px] font-medium text-[var(--muted)] uppercase tracking-wider mb-2">Related news</div>
                      <div className="space-y-1.5">
                        {c.relevant_news.map((n, i) => (
                          <a
                            key={i}
                            href={n.url || "#"}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block text-[11px] text-[var(--secondary)] hover:text-[var(--text)] transition-colors leading-snug"
                            onClick={e => e.stopPropagation()}
                          >
                            {n.title}
                            {n.source && <span className="text-[var(--muted)] ml-1">\u2014 {n.source}</span>}
                            {n.date && <span className="text-[var(--muted)] ml-1">{n.date}</span>}
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Impact justification */}
                  <div className="p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)]">
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="text-[10px] font-medium text-[var(--muted)] uppercase tracking-wider">Price impact</div>
                      <span className={cn(
                        "text-[11px] font-mono font-semibold",
                        isDownRisk ? "text-rose-400/80" : "text-emerald-400/80"
                      )}>
                        {isDownRisk ? `\u2212$${impactDollar}` : `+$${impactDollar}`} ({isDownRisk ? `\u2212${Math.abs(impactPct)}%` : `+${impactPct}%`})
                      </span>
                    </div>
                    {c.detail && (
                      <p className="text-[10px] text-[var(--secondary)] leading-relaxed">{c.detail}</p>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-[9px] text-[var(--faint)]">
                      {c.variable.split(",").map(v => (
                        <span key={v} className="font-mono px-1.5 py-0.5 rounded bg-[var(--border)]">{VAR_LABELS[v.trim()] || v.trim()}</span>
                      ))}
                      <span className="ml-auto">{WEIGHT_LABEL[c.weight]}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
