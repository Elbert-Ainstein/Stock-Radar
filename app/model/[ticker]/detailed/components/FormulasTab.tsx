"use client";

import type { Payload } from "../types";
import { fmtDollar, fmtMM, fmtPct, fmtStep, capitalize } from "../helpers";
import { DriverRow } from "./TableHelpers";

export default function FormulasTab({ payload }: { payload: Payload }) {
  const scenarios = payload.target.scenarios;
  const order: Array<"downside" | "base" | "upside"> = ["downside", "base", "upside"];
  const ttm = payload.target.ttm_revenue;
  const netDebt = payload.target.net_debt;
  const shares = payload.target.shares_diluted;

  // Build symbolic formula walk for each scenario, mirroring target_engine.py.
  type FRow = {
    label: string;
    formula: string; // symbolic formula (Excel-like)
    scenarioValues: Record<string, string>; // rendered values per scenario
    note?: string;
  };

  const rows: FRow[] = [
    {
      label: "TTM Revenue",
      formula: "= sum(last 4 quarters revenue)",
      scenarioValues: Object.fromEntries(order.map((k) => [k, fmtMM(ttm)])),
      note: "Source: yfinance quarterly income statement",
    },
    {
      label: "Y1 Revenue",
      formula: "= TTM_Revenue \u00d7 (1 + rev_growth_y1)",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(ttm * (1 + scenarios[k].rev_growth_y1))])
      ),
    },
    {
      label: "Y3 Revenue",
      formula:
        "= TTM_Revenue \u00d7 (1 + g_y1) \u00d7 (1 + g_mid) \u00d7 (1 + g_terminal)   [g_mid = avg(g_y1, g_terminal)]",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(scenarios[k].terminal_revenue)])
      ),
    },
    {
      label: "Y3 EBITDA",
      formula: "= Y3_Revenue \u00d7 ebitda_margin_target",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(scenarios[k].terminal_ebitda)])
      ),
    },
    {
      label: "Y3 FCF \u2212 SBC",
      formula: "= Y3_Revenue \u00d7 fcf_sbc_margin_target",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(scenarios[k].terminal_fcf_sbc)])
      ),
    },
    {
      label: "EV via EBITDA",
      formula: "= Y3_EBITDA \u00d7 EV/EBITDA_multiple",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(scenarios[k].ev_from_ebitda)])
      ),
    },
    {
      label: "EV via (FCF \u2212 SBC)",
      formula: "= Y3_FCF_SBC \u00d7 EV/(FCF-SBC)_multiple",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(scenarios[k].ev_from_fcf_sbc)])
      ),
    },
    {
      label: "Terminal EV (blend)",
      formula: "= 0.5 \u00d7 EV_via_EBITDA + 0.5 \u00d7 EV_via_FCF_SBC",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(scenarios[k].terminal_ev_blended)])
      ),
    },
    {
      label: "PV of Terminal EV",
      formula: "= Terminal_EV / (1 + WACC)^2",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(scenarios[k].pv_ev_blended)])
      ),
      note: "2-year discount (Y3 target, today anchored at Y1)",
    },
    {
      label: "Equity value",
      formula: "= PV_Terminal_EV \u2212 Net_Debt",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtMM(scenarios[k].equity_value)])
      ),
    },
    {
      label: "Price per share",
      formula: "= Equity_value / Shares_diluted",
      scenarioValues: Object.fromEntries(
        order.map((k) => [k, fmtDollar(scenarios[k].price)])
      ),
    },
  ];

  // Formula inputs (constants)
  const inputs = [
    { label: "TTM Revenue", value: fmtMM(ttm) },
    { label: "Net Debt", value: fmtMM(netDebt) },
    { label: "Shares (diluted)", value: `${(shares / 1e6).toFixed(1)}M` },
  ];

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/30 p-4">
        <div className="text-xs uppercase tracking-wider text-neutral-400 mb-2">
          How to read this tab
        </div>
        <div className="text-sm text-neutral-300 space-y-1">
          <div>
            Each row is one computed line item. The <span className="font-mono text-blue-300">Formula</span> column
            shows the equation (Excel-style). The three right columns show the computed value under
            each scenario&apos;s driver set.
          </div>
          <div className="text-xs text-neutral-400">
            Drivers differ per scenario — see the Valuation tab for each scenario&apos;s growth rates,
            margins, multiples, and WACC.
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-neutral-800 overflow-hidden">
        <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400">
          Model inputs (hardcoded)
        </div>
        <table className="w-full text-sm">
          <tbody>
            {inputs.map((inp, i) => (
              <tr key={i} className="border-t border-neutral-800">
                <td className="px-3 py-1.5 text-neutral-300 w-1/3">{inp.label}</td>
                <td className="px-3 py-1.5 text-neutral-500 text-xs font-mono">hardcoded</td>
                <td className="px-3 py-1.5 text-right font-mono">{inp.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-lg border border-neutral-800 overflow-x-auto">
        <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400">
          Formula walk — each row shows its equation and per-scenario result
        </div>
        <table className="w-full text-sm">
          <thead className="bg-neutral-900/50">
            <tr>
              <th className="text-left px-3 py-2 text-neutral-400 font-medium w-40">Line</th>
              <th className="text-left px-3 py-2 text-neutral-400 font-medium">Formula</th>
              {order.map((k) => (
                <th
                  key={k}
                  className={`text-right px-3 py-2 ${
                    k === "base" ? "text-blue-300 bg-blue-950/20" : "text-neutral-400"
                  }`}
                >
                  {capitalize(k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={i}
                className={`border-t border-neutral-800 ${
                  r.label === "Price per share" ? "bg-neutral-900 font-semibold" : ""
                }`}
              >
                <td className="px-3 py-1.5 text-neutral-200">{r.label}</td>
                <td className="px-3 py-1.5 text-neutral-400 text-xs font-mono">
                  {r.formula}
                  {r.note && <div className="text-neutral-500 text-[10px] mt-0.5">{r.note}</div>}
                </td>
                {order.map((k) => (
                  <td
                    key={k}
                    className={`px-3 py-1.5 text-right font-mono ${
                      k === "base" ? "bg-blue-950/20 text-blue-200" : "text-neutral-300"
                    }`}
                  >
                    {r.scenarioValues[k]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Driver values per scenario */}
      <div className="rounded-lg border border-neutral-800 overflow-x-auto">
        <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400">
          Driver values (the variables in the formulas above)
        </div>
        <table className="w-full text-sm">
          <thead className="bg-neutral-900/50">
            <tr>
              <th className="text-left px-3 py-2 text-neutral-400 font-medium">Driver</th>
              {order.map((k) => (
                <th
                  key={k}
                  className={`text-right px-3 py-2 ${
                    k === "base" ? "text-blue-300 bg-blue-950/20" : "text-neutral-400"
                  }`}
                >
                  {capitalize(k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <DriverRow label="rev_growth_y1" order={order} scenarios={scenarios} get={(s) => fmtPct(s.rev_growth_y1)} />
            <DriverRow label="rev_growth_terminal" order={order} scenarios={scenarios} get={(s) => fmtPct(s.rev_growth_terminal)} />
            <DriverRow label="ebitda_margin_target" order={order} scenarios={scenarios} get={(s) => fmtPct(s.ebitda_margin_target)} />
            <DriverRow label="fcf_sbc_margin_target" order={order} scenarios={scenarios} get={(s) => fmtPct(s.fcf_sbc_margin_target)} />
            <DriverRow label="ev_ebitda_multiple" order={order} scenarios={scenarios} get={(s) => s.ev_ebitda_multiple != null ? `${s.ev_ebitda_multiple.toFixed(1)}x` : "\u2014"} />
            <DriverRow label="ev_fcf_sbc_multiple" order={order} scenarios={scenarios} get={(s) => s.ev_fcf_sbc_multiple != null ? `${s.ev_fcf_sbc_multiple.toFixed(1)}x` : "\u2014"} />
            <DriverRow label="discount_rate (WACC)" order={order} scenarios={scenarios} get={(s) => fmtPct(s.discount_rate)} />
          </tbody>
        </table>
      </div>

      {/* Full base-scenario deduction chain from engine */}
      <div className="rounded-lg border border-neutral-800 overflow-hidden">
        <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400">
          Base-scenario deduction chain (from engine)
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
                <td className="px-3 py-1.5 text-neutral-300 w-56">{s.label}</td>
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
