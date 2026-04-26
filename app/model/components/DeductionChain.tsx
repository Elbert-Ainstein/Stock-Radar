"use client";

import { cn } from "../helpers";
import type { ValuationMethod } from "../types";

const defaultFmt = (price: number) => `$${Math.round(price).toLocaleString()}`;
const defaultFmtB = (priceB: number) => `$${priceB.toFixed(1)}B`;
const defaultFmt2 = (price: number) => `$${price.toFixed(2)}`;

export default function DeductionChain({
  revenueB,
  opMargin,
  taxRate,
  sharesM,
  multiple,
  targetPrice,
  method,
  netDebtB = 0,
  fmt = defaultFmt,
  fmtB = defaultFmtB,
  fmt2 = defaultFmt2,
}: {
  revenueB: number;
  opMargin: number;
  taxRate: number;
  sharesM: number;
  multiple: number;
  targetPrice: number;
  method: ValuationMethod;
  netDebtB?: number;
  fmt?: (price: number) => string;
  fmtB?: (priceB: number) => string;
  fmt2?: (price: number) => string;
}) {
  const marketCapB = (targetPrice * sharesM) / 1000;

  let steps: { label: string; value: string }[];
  if (method === "cyclical") {
    const normalizedEbitB = revenueB * opMargin;
    const evB = normalizedEbitB * multiple;
    const equityB = evB - netDebtB;
    steps = [
      { label: "Revenue", value: fmtB(revenueB) },
      { label: `× ${(opMargin * 100).toFixed(0)}% EBIT margin`, value: `${fmtB(normalizedEbitB).replace(/B$/, '')}B` },
      { label: `× ${multiple.toFixed(0)}× EV/EBIT`, value: `EV ${fmtB(evB)}` },
      { label: `− Net debt`, value: fmtB(equityB) },
      { label: "Price/share", value: fmt(targetPrice) },
    ];
  } else if (method === "ps") {
    const rps = sharesM > 0 ? (revenueB * 1000) / sharesM : 0;
    steps = [
      { label: "Revenue", value: fmtB(revenueB) },
      { label: "Rev/share", value: fmt2(rps) },
      { label: `× ${multiple.toFixed(0)}× P/S`, value: fmt(targetPrice) },
      { label: "Market cap", value: fmtB(marketCapB) },
    ];
  } else {
    const opIncomeB = revenueB * opMargin;
    const netIncomeB = opIncomeB * (1 - taxRate);
    const eps = sharesM > 0 ? (netIncomeB * 1000) / sharesM : 0;
    steps = [
      { label: "Revenue", value: fmtB(revenueB) },
      { label: "Operating income", value: `${fmtB(opIncomeB).replace(/B$/, '')}B` },
      { label: "Net income", value: `${fmtB(netIncomeB).replace(/B$/, '')}B` },
      { label: "EPS", value: fmt2(eps) },
      { label: "Market cap", value: fmtB(marketCapB) },
    ];
  }

  return (
    <div className="flex items-stretch gap-0 overflow-x-auto">
      {steps.map((s, i) => (
        <div key={s.label} className="flex items-stretch">
          <div className="flex flex-col items-center justify-center min-w-[140px] px-5 py-4 bg-[var(--card)] border border-[var(--border)] first:rounded-l-lg last:rounded-r-lg">
            <div className="text-xs text-[var(--secondary)] mb-1.5">{s.label}</div>
            <div className="text-xl font-mono font-bold text-[var(--text)]">{s.value}</div>
          </div>
          {i < steps.length - 1 && (
            <div className="flex items-center -mx-px z-10">
              <div className="w-0 h-0 border-t-[10px] border-t-transparent border-b-[10px] border-b-transparent border-l-[8px] border-l-[var(--border)]" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
