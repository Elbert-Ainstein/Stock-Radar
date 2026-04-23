"use client";

import type { Payload } from "../types";
import { fmtMM } from "../helpers";
import { Row } from "./TableHelpers";

export default function CashTab({ payload }: { payload: Payload }) {
  const annual = payload.target.forecast_annual;
  const ttm = payload.historicals.ttm;
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-neutral-800 p-4 bg-neutral-900/30">
        <div className="text-xs uppercase tracking-wider text-neutral-400 mb-2">
          TTM actuals
        </div>
        <div className="grid grid-cols-5 gap-4 text-sm">
          <div><span className="text-neutral-400">Revenue: </span>{fmtMM(ttm.revenue)}</div>
          <div><span className="text-neutral-400">Op income: </span>{fmtMM(ttm.operating_income)}</div>
          <div><span className="text-neutral-400">EBITDA: </span>{fmtMM(ttm.ebitda)}</div>
          <div><span className="text-neutral-400">FCF: </span>{fmtMM(ttm.fcf)}</div>
          <div><span className="text-neutral-400">FCF &minus; SBC: </span>{fmtMM(payload.target.ttm_fcf_sbc)}</div>
        </div>
      </div>
      <div className="rounded-lg border border-neutral-800 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-neutral-900">
            <tr>
              <th className="text-left px-3 py-2 text-neutral-400 font-medium">
                5-year forecast ($mm)
              </th>
              {annual.map((p) => (
                <th key={p.period} className="text-right px-3 py-2 text-blue-300">
                  {p.period}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <Row label="Revenue" cells={annual.map((p) => fmtMM(p.revenue))} bold />
            <Row label="EBITDA" cells={annual.map((p) => fmtMM(p.ebitda))} />
            <Row label="FCF &minus; SBC" cells={annual.map((p) => fmtMM(p.fcf_sbc))} bold />
            <Row label="Free cash flow" cells={annual.map((p) => fmtMM(p.fcf))} />
            <Row label="Net income" cells={annual.map((p) => fmtMM(p.net_income))} />
          </tbody>
        </table>
      </div>
    </div>
  );
}
