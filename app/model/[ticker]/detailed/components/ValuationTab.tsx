"use client";

import type { Payload } from "../types";
import { fmtDollar, fmtMM, fmtPct, fmtStep, capitalize } from "../helpers";
import { ScenarioRow } from "./TableHelpers";

export default function ValuationTab({ payload }: { payload: Payload }) {
  const scenarios = payload.target.scenarios;
  const order: Array<keyof typeof scenarios> = ["downside", "base", "upside"];
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-neutral-800 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-neutral-900">
            <tr>
              <th className="text-left px-3 py-2 text-neutral-400 font-medium">Line</th>
              {order.map((k) => (
                <th
                  key={k}
                  className={`text-right px-3 py-2 ${
                    k === "base"
                      ? "text-blue-300 bg-blue-950/20"
                      : "text-neutral-400"
                  }`}
                >
                  {capitalize(k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <ScenarioRow label="Rev growth Y1" order={order} scenarios={scenarios} get={(s) => fmtPct(s.rev_growth_y1)} />
            <ScenarioRow label="Rev growth terminal" order={order} scenarios={scenarios} get={(s) => fmtPct(s.rev_growth_terminal)} />
            <ScenarioRow label="EBITDA margin target" order={order} scenarios={scenarios} get={(s) => fmtPct(s.ebitda_margin_target)} />
            <ScenarioRow label="FCF-SBC margin target" order={order} scenarios={scenarios} get={(s) => fmtPct(s.fcf_sbc_margin_target)} />
            <ScenarioRow label="EV/EBITDA mult" order={order} scenarios={scenarios} get={(s) => s.ev_ebitda_multiple != null ? `${s.ev_ebitda_multiple.toFixed(1)}x` : "\u2014"} />
            <ScenarioRow label="EV/(FCF-SBC) mult" order={order} scenarios={scenarios} get={(s) => s.ev_fcf_sbc_multiple != null ? `${s.ev_fcf_sbc_multiple.toFixed(1)}x` : "\u2014"} />
            <ScenarioRow label="WACC" order={order} scenarios={scenarios} get={(s) => fmtPct(s.discount_rate)} />
            <tr className="border-t-2 border-neutral-700 bg-neutral-900/50">
              <td className="px-3 py-1.5 font-semibold">Y3 Revenue</td>
              {order.map((k) => (
                <td
                  key={k}
                  className={`px-3 py-1.5 text-right font-mono ${k === "base" ? "bg-blue-950/20" : ""}`}
                >
                  {fmtMM(scenarios[k].terminal_revenue)}
                </td>
              ))}
            </tr>
            <ScenarioRow label="Y3 EBITDA" order={order} scenarios={scenarios} get={(s) => fmtMM(s.terminal_ebitda)} bold />
            <ScenarioRow label="Y3 FCF \u2212 SBC" order={order} scenarios={scenarios} get={(s) => fmtMM(s.terminal_fcf_sbc)} bold />
            <ScenarioRow label="EV via EBITDA" order={order} scenarios={scenarios} get={(s) => fmtMM(s.ev_from_ebitda)} />
            <ScenarioRow label="EV via (FCF-SBC)" order={order} scenarios={scenarios} get={(s) => fmtMM(s.ev_from_fcf_sbc)} />
            <ScenarioRow label="Terminal EV (blend)" order={order} scenarios={scenarios} get={(s) => fmtMM(s.terminal_ev_blended)} bold />
            <ScenarioRow label="PV of terminal EV" order={order} scenarios={scenarios} get={(s) => fmtMM(s.pv_ev_blended)} />
            <ScenarioRow label="Equity value" order={order} scenarios={scenarios} get={(s) => fmtMM(s.equity_value)} />
            <tr className="border-t-2 border-neutral-700 bg-neutral-900">
              <td className="px-3 py-2 font-semibold">Price per share</td>
              {order.map((k) => (
                <td
                  key={k}
                  className={`px-3 py-2 text-right font-mono font-semibold text-lg ${
                    k === "base" ? "text-blue-300 bg-blue-950/30" : ""
                  }`}
                >
                  {fmtDollar(scenarios[k].price)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Method-comparison: Base scenario, EBITDA vs FCF-SBC */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-neutral-800 p-4 bg-neutral-900/30">
          <div className="text-xs uppercase tracking-wider text-neutral-400 mb-2">
            EV / EBITDA method (base)
          </div>
          <div className="space-y-1 text-sm">
            <div>
              EV: <span className="font-mono">{fmtMM(scenarios.base.ev_from_ebitda)}</span>
            </div>
            <div>
              PV EV: <span className="font-mono">{fmtMM(scenarios.base.pv_ev_from_ebitda)}</span>
            </div>
            <div className="text-lg mt-2">
              Price:{" "}
              <span className="font-mono font-semibold">
                {fmtDollar(scenarios.base.price_from_ebitda)}
              </span>
            </div>
          </div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-4 bg-neutral-900/30">
          <div className="text-xs uppercase tracking-wider text-neutral-400 mb-2">
            EV / (FCF-SBC) method (base)
          </div>
          <div className="space-y-1 text-sm">
            <div>
              EV: <span className="font-mono">{fmtMM(scenarios.base.ev_from_fcf_sbc)}</span>
            </div>
            <div>
              PV EV: <span className="font-mono">{fmtMM(scenarios.base.pv_ev_from_fcf_sbc)}</span>
            </div>
            <div className="text-lg mt-2">
              Price:{" "}
              <span className="font-mono font-semibold">
                {fmtDollar(scenarios.base.price_from_fcf_sbc)}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-blue-700 bg-blue-950/30 p-4">
        <div className="text-xs uppercase tracking-wider text-blue-300 mb-1">
          Blended base target (50/50)
        </div>
        <div className="text-2xl font-mono font-semibold">
          {fmtDollar(scenarios.base.price)}
        </div>
        <div className="text-xs text-neutral-400 mt-1">
          Horizon: {payload.target.terminal_year}
        </div>
      </div>

      {/* Deduction chain */}
      <div className="rounded-lg border border-neutral-800 overflow-hidden">
        <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400">
          Base-scenario deduction chain
        </div>
        <table className="w-full text-sm">
          <tbody>
            {payload.target.steps.map((s, i) => (
              <tr
                key={i}
                className={`border-t border-neutral-800 ${
                  i % 2 === 0 ? "bg-neutral-950" : "bg-neutral-900/30"
                }`}
              >
                <td className="px-3 py-1.5 text-neutral-300">{s.label}</td>
                <td className="px-3 py-1.5 text-neutral-500 text-xs font-mono">{s.formula}</td>
                <td className="px-3 py-1.5 text-right font-mono">{fmtStep(s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
