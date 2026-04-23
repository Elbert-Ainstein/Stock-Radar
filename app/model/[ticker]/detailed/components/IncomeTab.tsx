"use client";

import type { Payload } from "../types";
import { fmtMM, fmtPct } from "../helpers";
import { Row } from "./TableHelpers";

export default function IncomeTab({ payload }: { payload: Payload }) {
  const hist = payload.historicals.quarterly;
  const fcst = payload.target.forecast_quarterly.slice(0, 4);
  return (
    <div className="rounded-lg border border-neutral-800 overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-neutral-900">
          <tr>
            <th className="text-left px-3 py-2 text-neutral-400 font-medium">
              Quarterly ($mm)
            </th>
            {hist.map((p) => (
              <th key={p.period} className="text-right px-3 py-2 text-neutral-400">
                {p.period}
              </th>
            ))}
            {fcst.map((p) => (
              <th key={p.period} className="text-right px-3 py-2 text-blue-300">
                {p.period} (E)
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <Row
            label="Revenue"
            cells={[
              ...hist.map((p) => fmtMM(p.revenue)),
              ...fcst.map((p) => fmtMM(p.revenue)),
            ]}
            bold
          />
          <Row
            label="Operating income"
            cells={[
              ...hist.map((p) => fmtMM(p.operating_income)),
              ...fcst.map((p) => fmtMM(p.operating_income)),
            ]}
          />
          <Row
            label="Net income"
            cells={[
              ...hist.map((p) => fmtMM(p.net_income)),
              ...fcst.map((p) => fmtMM(p.net_income)),
            ]}
          />
          <Row
            label="Op margin"
            cells={[
              ...hist.map((p) =>
                p.operating_income != null && p.revenue
                  ? fmtPct(p.operating_income / p.revenue)
                  : "\u2014"
              ),
              ...fcst.map((p) => fmtPct(p.op_margin)),
            ]}
          />
        </tbody>
      </table>
    </div>
  );
}
