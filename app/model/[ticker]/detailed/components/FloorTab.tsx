"use client";

import type { Payload, ThesisData } from "../types";
import SummaryTab from "./SummaryTab";
import ValuationTab from "./ValuationTab";

/**
 * v2 architecture-v2 §4.2: merge of old "summary" + "valuation" tabs into a
 * single Floor (DCF) view. The DCF engine is repositioned as the conservative
 * downside anchor; the thesis on the Thesis tab is the headline.
 *
 * Drift indicator: when a thesis exists, show the gap between thesis target
 * and DCF base — that gap is the diagnostic signal the architecture-v2 spec
 * calls out (small gap = engine corroborates; large gap = engine missing
 * an unmodeled lever like re-rating, regime shift, trough year).
 */
export default function FloorTab({
  payload,
  thesis,
}: {
  payload: Payload;
  thesis?: ThesisData | null;
}) {
  const dcfBase = payload?.target?.base;
  const thesisTarget = thesis?.thesis_target ?? null;
  const driftPct =
    thesisTarget != null && dcfBase != null && dcfBase > 0
      ? (thesisTarget - dcfBase) / dcfBase
      : null;

  let driftLabel: { label: string; color: string } | null = null;
  if (driftPct != null) {
    const pct = (driftPct * 100).toFixed(0);
    if (Math.abs(driftPct) < 0.15) {
      driftLabel = {
        label: `±${pct}% drift — engine corroborates thesis`,
        color: "text-emerald-300",
      };
    } else if (driftPct > 0) {
      driftLabel = {
        label: `+${pct}% drift — thesis above floor (re-rating / unmodeled lever)`,
        color: "text-yellow-300",
      };
    } else {
      driftLabel = {
        label: `${pct}% drift — thesis below floor (regulatory/cycle risk)`,
        color: "text-orange-300",
      };
    }
  }

  return (
    <div className="space-y-8">
      <div className="rounded-md border border-yellow-500/20 bg-yellow-500/5 p-3 text-[12px] text-yellow-200/90">
        <strong className="text-yellow-300">Floor (DCF) view.</strong>{" "}
        This tab shows the conservative engine-derived target — the floor, not the headline.
        The headline thesis (with conviction, breakout, position sizing) lives on the{" "}
        <em>Thesis</em> tab.
        {driftLabel && (
          <div className={`mt-2 font-mono ${driftLabel.color}`}>{driftLabel.label}</div>
        )}
      </div>
      <SummaryTab payload={payload} />
      <ValuationTab payload={payload} />
    </div>
  );
}
