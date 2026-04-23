"use client";

import type { Payload } from "../types";
import { fmtMM, fmtPct } from "../helpers";
import { Row } from "./TableHelpers";

export default function SummaryTab({ payload }: { payload: Payload }) {
  const annual = payload.target.forecast_annual;
  const histAnnual = payload.historicals.annual;
  // Show last 3 historicals + 5 forecast years
  const combined = [
    ...histAnnual.slice(-3).map((h) => ({
      period: h.period,
      revenue: h.revenue ?? 0,
      rev_growth: 0,
      operating_income: h.operating_income ?? 0,
      op_margin:
        h.operating_income && h.revenue ? h.operating_income / h.revenue : 0,
      ebitda: 0,
      ebitda_margin: 0,
      fcf_sbc: 0,
      fcf_sbc_margin: 0,
      net_income: h.net_income ?? 0,
      fcf: 0,
      is_actual: true,
    })),
    ...annual.map((a) => ({ ...a, is_actual: false })),
  ];
  return (
    <div className="rounded-lg border border-neutral-800 overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-neutral-900">
          <tr>
            <th className="text-left px-3 py-2 text-neutral-400 font-medium">$mm</th>
            {combined.map((p) => (
              <th
                key={p.period}
                className={`text-right px-3 py-2 ${
                  p.is_actual ? "text-neutral-400" : "text-blue-300"
                }`}
              >
                {p.period}
                <span className="text-[10px] ml-1">{p.is_actual ? "(A)" : "(E)"}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <Row label="Revenue" cells={combined.map((p) => fmtMM(p.revenue))} bold />
          <Row
            label="YoY growth"
            cells={combined.map((p, i) =>
              i === 0
                ? "\u2014"
                : fmtPct(
                    combined[i].revenue && combined[i - 1].revenue
                      ? combined[i].revenue / combined[i - 1].revenue - 1
                      : null
                  )
            )}
          />
          <Row label="Operating income" cells={combined.map((p) => fmtMM(p.operating_income))} />
          <Row label="Op margin" cells={combined.map((p) => fmtPct(p.op_margin))} />
          <Row label="EBITDA (forecast)" cells={combined.map((p) => (p.is_actual ? "\u2014" : fmtMM(p.ebitda)))} bold />
          <Row label="EBITDA margin" cells={combined.map((p) => (p.is_actual ? "\u2014" : fmtPct(p.ebitda_margin)))} />
          <Row label="FCF \u2212 SBC (forecast)" cells={combined.map((p) => (p.is_actual ? "\u2014" : fmtMM(p.fcf_sbc)))} bold />
          <Row label="FCF-SBC margin" cells={combined.map((p) => (p.is_actual ? "\u2014" : fmtPct(p.fcf_sbc_margin)))} />
          <Row label="Net income" cells={combined.map((p) => fmtMM(p.net_income))} />
        </tbody>
      </table>
    </div>
  );
}
