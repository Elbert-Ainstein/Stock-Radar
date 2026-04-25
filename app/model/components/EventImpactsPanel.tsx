"use client";

import { useState } from "react";
import { cn } from "../helpers";
import type { EventImpactsPayload } from "../types";

function EventTypeBadge({ type, direction }: { type: string; direction: "up" | "down" }) {
  const upColor = "text-[var(--success)] bg-[var(--success-bg)]";
  const downColor = "text-[var(--danger)] bg-[var(--danger-bg)]";
  const cls = direction === "up" ? upColor : downColor;
  return (
    <span className={cn("inline-block px-1.5 py-[1px] rounded text-[9px] font-mono", cls)}>
      {type}
    </span>
  );
}

export default function EventImpactsPanel({
  impacts,
  criteriaAdjustedTarget,
  ticker,
}: {
  impacts: EventImpactsPayload;
  criteriaAdjustedTarget: number;
  ticker?: string;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showWeighting, setShowWeighting] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);

  const handleRebuild = async () => {
    if (rebuilding) return;
    setRebuilding(true);
    try {
      const res = await fetch("/api/rebuild", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: ticker || null }),
      });
      if (res.ok) {
        // Poll until done, then reload
        const poll = setInterval(async () => {
          try {
            const r = await fetch("/api/rebuild");
            const s = await r.json();
            if (!s.running) {
              clearInterval(poll);
              setRebuilding(false);
              window.location.reload();
            }
          } catch {}
        }, 2000);
      } else {
        setRebuilding(false);
      }
    } catch {
      setRebuilding(false);
    }
  };
  const events = impacts.events || [];
  const summary = impacts.summary;
  const projection = impacts.projection_score;
  const blend = impacts.blend;

  // Spectrum badge
  const spectrumScore = projection?.score ?? 0.5;
  const spectrumLabel =
    spectrumScore >= 0.7 ? "Projection-heavy" : spectrumScore >= 0.4 ? "Balanced" : "Returns-heavy";
  const spectrumColor =
    spectrumScore >= 0.7
      ? "bg-purple-500/15 text-purple-400 border-purple-500/30"
      : spectrumScore >= 0.4
      ? "bg-blue-500/15 text-blue-400 border-blue-500/30"
      : "bg-amber-500/15 text-amber-400 border-amber-500/30";

  if (!events.length) {
    return (
      <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] border-dashed p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[13px] text-[var(--muted)]">Recent events</div>
            <div className="text-[10px] text-[var(--faint)] mt-1">
              {impacts.reasoner_available
                ? "No material events detected from the last scout pass."
                : "Event reasoner unavailable \u2014 requires ANTHROPIC_API_KEY. See docs/event_target_plan.md."}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {impacts.blend_available && (
              <span className={cn("text-[9px] px-1.5 py-0.5 rounded border font-mono", spectrumColor)}>
                {spectrumLabel}
              </span>
            )}
            <div className="text-[10px] text-[var(--faint)] font-mono">0 events</div>
          </div>
        </div>
      </div>
    );
  }

  const adjPct = summary.event_adjustment_pct;
  const criteriaTarget = criteriaAdjustedTarget || 0;
  const blendTarget = blend?.final_target ?? impacts.proposed_target_with_events;
  const deltaVsCriteria = blendTarget - criteriaTarget;
  const diffPct = criteriaTarget > 0 ? Math.abs(deltaVsCriteria / criteriaTarget * 100) : 0;
  const adjColor =
    adjPct > 0 ? "text-[var(--success)]" : adjPct < 0 ? "text-[var(--danger)]" : "text-[var(--muted)]";

  return (
    <div className="rounded-xl bg-[var(--card)] border border-[var(--border)] p-5">
      {/* Header + summary strip */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <div>
            <div className="text-[13px] text-[var(--muted)]">
              Event impacts
              {impacts.merge_enabled ? "" : " \u2014 audit preview"}
            </div>
            <div className="text-[10px] text-[var(--faint)] mt-1">
              {impacts.merge_enabled
                ? "Events are merged into the authoritative target."
                : "Events displayed side-by-side with criteria target for sanity check."}
            </div>
          </div>
          {impacts.blend_available && (
            <span className={cn("text-[9px] px-1.5 py-0.5 rounded border font-mono whitespace-nowrap", spectrumColor)}>
              {spectrumLabel}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono">
          <button
            type="button"
            onClick={handleRebuild}
            disabled={rebuilding}
            className={cn(
              "px-2 py-1 rounded border text-[9px] transition-all",
              rebuilding
                ? "border-[var(--border)] text-[var(--muted)] cursor-not-allowed opacity-50"
                : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--hover)]"
            )}
            title={ticker ? `Rebuild analysis for ${ticker}` : "Rebuild analysis"}
          >
            {rebuilding ? "Rebuilding..." : `Rebuild${ticker ? ` ${ticker}` : ""}`}
          </button>
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono">
          <span className="text-[var(--muted)]">
            {summary.event_count} event{summary.event_count === 1 ? "" : "s"}
            {" \u00B7 "}
            <span className="text-[var(--success)]">{summary.up_count}↑</span>
            {" / "}
            <span className="text-[var(--danger)]">{summary.down_count}↓</span>
          </span>
          <span className={cn("tabular-nums", adjColor)}>
            {adjPct >= 0 ? "+" : ""}
            {adjPct.toFixed(1)}%
          </span>
          {summary.capped && (
            <span className="text-[var(--warning)] text-[9px]" title="Total event adjustment hit \u00B115% cap">
              CAP
            </span>
          )}
        </div>
      </div>

      {/* Target comparison: criteria-only vs with-events (weighted) */}
      {criteriaTarget > 0 && (
        <div className="mb-4 rounded-lg bg-[var(--bg)] border border-[var(--border)] p-3">
          <div className="flex items-center gap-4 text-[11px]">
            <div>
              <div className="text-[var(--muted)] mb-0.5">Criteria-only</div>
              <div className="font-mono tabular-nums text-[var(--text)]">
                ${criteriaTarget.toLocaleString()}
              </div>
            </div>
            <div className="text-[var(--faint)]">→</div>
            <div>
              <div className="text-[var(--muted)] mb-0.5">With events (weighted)</div>
              <div className={cn("font-mono tabular-nums", adjColor)}>
                ${blendTarget.toLocaleString()}
                {deltaVsCriteria !== 0 && (
                  <span className="ml-1 text-[9px]">
                    ({deltaVsCriteria > 0 ? "+" : ""}${deltaVsCriteria.toLocaleString()})
                  </span>
                )}
              </div>
            </div>
            <div className="ml-auto flex items-center gap-2">
              {diffPct > 5 && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 font-mono">
                  {diffPct.toFixed(0)}% diff
                </span>
              )}
              <span className="text-[9px] text-[var(--faint)]">
                {impacts.merge_enabled ? "MERGED" : "audit-only"}
              </span>
            </div>
          </div>

          {/* Event weight indicator */}
          {blend && (
            <div className="mt-2 pt-2 border-t border-[var(--border)] flex items-center gap-3 text-[10px]">
              <span className="text-[var(--muted)]">
                Event weight: <span className="font-mono tabular-nums text-[var(--text)]">{(blend.event_weight * 100).toFixed(0)}%</span>
              </span>
              <span className="text-[var(--faint)]">·</span>
              <span className="text-[var(--muted)]">
                Raw events: <span className="font-mono tabular-nums">{blend.event_pct_raw >= 0 ? "+" : ""}{blend.event_pct_raw.toFixed(1)}%</span>
              </span>
              <span className="text-[var(--faint)]">·</span>
              <span className="text-[var(--muted)]">
                After weighting: <span className="font-mono tabular-nums">{blend.event_pct_weighted >= 0 ? "+" : ""}{blend.event_pct_weighted.toFixed(1)}%</span>
              </span>
            </div>
          )}
        </div>
      )}

      {/* "Why this weighting?" collapsible section */}
      {impacts.blend_available && projection && blend && (
        <div className="mb-4">
          <button
            type="button"
            onClick={() => setShowWeighting(!showWeighting)}
            className="flex items-center gap-1.5 text-[10px] text-[var(--accent)] hover:underline cursor-pointer"
          >
            <svg
              width="10" height="10" viewBox="0 0 10 10" fill="none"
              className={cn("transition-transform", showWeighting && "rotate-90")}
            >
              <path d="M3 1.5L7 5L3 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Why this weighting?
          </button>

          {showWeighting && (
            <div className="mt-2 rounded-lg bg-[var(--bg)] border border-[var(--border)] p-3 space-y-3">
              {/* Projection score explanation */}
              <div>
                <div className="text-[9px] text-[var(--faint)] mb-1">Projection score trail</div>
                <div className="text-[10px] text-[var(--secondary)] font-mono leading-relaxed">
                  {projection.final_explanation}
                </div>
              </div>

              {/* Contributors table */}
              {projection.contributors.length > 0 && (
                <div>
                  <div className="text-[9px] text-[var(--faint)] mb-1">Score contributors</div>
                  <div className="rounded border border-[var(--border)] overflow-hidden">
                    <table className="w-full text-[10px]">
                      <thead>
                        <tr className="bg-[var(--card)]">
                          <th className="text-left px-2 py-1 text-[var(--muted)] font-normal">Signal</th>
                          <th className="text-right px-2 py-1 text-[var(--muted)] font-normal">Source</th>
                          <th className="text-right px-2 py-1 text-[var(--muted)] font-normal">Delta</th>
                        </tr>
                      </thead>
                      <tbody>
                        {projection.contributors.map((c, i) => (
                          <tr key={i} className="border-t border-[var(--border)]">
                            <td className="px-2 py-1 text-[var(--text)]">{c.label}</td>
                            <td className="px-2 py-1 text-right font-mono tabular-nums text-[var(--secondary)]">
                              {c.source}
                            </td>
                            <td className={cn(
                              "px-2 py-1 text-right font-mono tabular-nums",
                              c.delta > 0 ? "text-[var(--success)]" : c.delta < 0 ? "text-[var(--danger)]" : "text-[var(--muted)]"
                            )}>
                              {c.delta >= 0 ? "+" : ""}{c.delta.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Blend formula */}
              <div>
                <div className="text-[9px] text-[var(--faint)] mb-1">Blend formula</div>
                <div className="text-[10px] text-[var(--text)] font-mono bg-[var(--card)] rounded px-2 py-1.5 leading-relaxed">
                  {blend.formula}
                </div>
              </div>

              {/* Summary row */}
              <div className="pt-1 flex items-center gap-4 text-[9px] text-[var(--faint)] font-mono">
                <span>spectrum: {spectrumScore.toFixed(2)}</span>
                <span>event_weight: {blend.event_weight.toFixed(2)}</span>
                <span>final: ${blend.final_target.toLocaleString()}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Event list */}
      <div className="space-y-1.5">
        {events.map((ev) => {
          const isExpanded = expandedId === ev.event_id;
          const contrib = ev.expected_contribution_pct;
          const contribColor =
            contrib > 0 ? "text-[var(--success)]" : contrib < 0 ? "text-[var(--danger)]" : "text-[var(--muted)]";
          const evidenceItem = ev.evidence?.[0];
          return (
            <div
              key={ev.event_id}
              className="rounded-lg border border-[var(--border)] bg-[var(--bg)] overflow-hidden"
            >
              <div
                className="p-3 cursor-pointer transition-all hover:bg-[var(--hover)]"
                onClick={() => setExpandedId(isExpanded ? null : ev.event_id)}
              >
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <EventTypeBadge type={ev.type} direction={ev.direction} />
                      <span className="text-[9px] text-[var(--faint)] font-mono">
                        {ev.detected_by}
                      </span>
                      {evidenceItem?.date && (
                        <span className="text-[9px] text-[var(--faint)] font-mono">
                          {evidenceItem.date}
                        </span>
                      )}
                    </div>
                    <div className="text-[12px] text-[var(--text)] truncate">{ev.summary}</div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className={cn("text-[11px] font-mono tabular-nums", contribColor)}>
                      {contrib >= 0 ? "+" : ""}
                      {contrib.toFixed(2)}%
                    </span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedId(isExpanded ? null : ev.event_id);
                      }}
                      className="text-[var(--muted)] hover:text-[var(--text)] p-0.5"
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 14 14"
                        fill="none"
                        className={cn("transition-transform", isExpanded && "rotate-180")}
                      >
                        <path
                          d="M3.5 5.25L7 8.75L10.5 5.25"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="border-t border-[var(--border)] bg-[var(--card)] p-4 space-y-3 text-[11px]">
                  {/* Metrics row */}
                  <div className="grid grid-cols-4 gap-3">
                    <div>
                      <div className="text-[9px] text-[var(--faint)] mb-0.5">Magnitude</div>
                      <div className="font-mono tabular-nums text-[var(--text)]">
                        {ev.magnitude_pct >= 0 ? "+" : ""}
                        {ev.magnitude_pct.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] text-[var(--faint)] mb-0.5">Probability</div>
                      <div className="font-mono tabular-nums text-[var(--text)]">
                        {(ev.probability * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] text-[var(--faint)] mb-0.5">
                        Chain conf. (compounded)
                      </div>
                      <div className="font-mono tabular-nums text-[var(--text)]">
                        {(ev.compounded_confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] text-[var(--faint)] mb-0.5">Recency</div>
                      <div className="font-mono tabular-nums text-[var(--text)]">
                        {(ev.recency_weight * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>

                  {/* Rationale */}
                  {ev.rationale && (
                    <div>
                      <div className="text-[9px] text-[var(--faint)] mb-0.5">Scout rationale</div>
                      <div className="text-[var(--secondary)]">{ev.rationale}</div>
                    </div>
                  )}

                  {/* Causal chain */}
                  {ev.chain && ev.chain.length > 0 && (
                    <div>
                      <div className="text-[9px] text-[var(--faint)] mb-1.5">
                        Causal chain (reasoner: {ev.reasoner})
                      </div>
                      <div className="space-y-1.5">
                        {ev.chain.map((link) => (
                          <div
                            key={link.level}
                            className="flex items-start gap-2 p-2 rounded bg-[var(--bg)]"
                          >
                            <span className="text-[9px] font-mono text-[var(--faint)] mt-[2px]">
                              L{link.level}
                            </span>
                            <div className="flex-1">
                              <div className="text-[var(--text)]">{link.claim}</div>
                              {link.reasoning && (
                                <div className="text-[var(--muted)] text-[10px] mt-0.5">
                                  {link.reasoning}
                                </div>
                              )}
                            </div>
                            <span className="text-[9px] font-mono tabular-nums text-[var(--muted)] mt-[2px]">
                              {(link.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Evidence */}
                  {ev.evidence && ev.evidence.length > 0 && ev.evidence[0]?.url && (
                    <div>
                      <div className="text-[9px] text-[var(--faint)] mb-0.5">Source</div>
                      {ev.evidence.map((e, i) => (
                        <a
                          key={i}
                          href={e.url || "#"}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[var(--accent)] hover:underline block truncate"
                        >
                          {e.source || "link"} — {e.headline || e.url}
                        </a>
                      ))}
                    </div>
                  )}

                  <div className="pt-1 text-[9px] text-[var(--faint)] font-mono flex gap-3">
                    <span>horizon ~{ev.time_horizon_months}mo</span>
                    <span>type: {ev.type_display}</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
