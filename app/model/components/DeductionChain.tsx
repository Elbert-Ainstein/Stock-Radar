"use client";

import { cn } from "../helpers";
import type { ValuationMethod } from "../types";

export default function DeductionChain({
  revenueB,
  opMargin,
  taxRate,
  sharesM,
  multiple,
  targetPrice,
  method,
  netDebtB = 0,
}: {
  revenueB: number;
  opMargin: number;
  taxRate: number;
  sharesM: number;
  multiple: number;
  targetPrice: number;
  method: ValuationMethod;
  netDebtB?: number;
}) {
  const marketCapB = (targetPrice * sharesM) / 1000;

  let steps: { label: string; value: string }[];
  if (method === "cyclical") {
    const normalizedEbitB = revenueB * opMargin;
    const evB = normalizedEbitB * multiple;
    const equityB = evB - netDebtB;
    steps = [
      { label: "Revenue", value: `$${revenueB.toFixed(1)}B` },
      { label: `\u00D7 ${(opMargin * 100).toFixed(0)}% EBIT margin`, value: `$${normalizedEbitB.toFixed(2)}B` },
      { label: `\u00D7 ${multiple.toFixed(0)}\u00D7 EV/EBIT`, value: `EV $${evB.toFixed(1)}B` },
      { label: `\u2212 Net debt`, value: `$${equityB.toFixed(1)}B` },
      { label: "Price/share", value: `$${targetPrice.toFixed(0)}` },
    ];
  } else if (method === "ps") {
    const rps = sharesM > 0 ? (revenueB * 1000) / sharesM : 0;
    steps = [
      { label: "Revenue", value: `$${revenueB.toFixed(1)}B` },
      { label: "Rev/share", value: `$${rps.toFixed(2)}` },
      { label: `\u00D7 ${multiple.toFixed(0)}\u00D7 P/S`, value: `$${targetPrice.toFixed(0)}` },
      { label: "Market cap", value: `$${marketCapB.toFixed(0)}B` },
    ];
  } else {
    const opIncomeB = revenueB * opMargin;
    const netIncomeB = opIncomeB * (1 - taxRate);
    const eps = sharesM > 0 ? (netIncomeB * 1000) / sharesM : 0;
    steps = [
      { label: "Revenue", value: `$${revenueB.toFixed(1)}B` },
      { label: "Operating income", value: `$${opIncomeB.toFixed(2)}B` },
      { label: "Net income", value: `$${netIncomeB.toFixed(2)}B` },
      { label: "EPS", value: `$${eps.toFixed(2)}` },
      { label: "Market cap", value: `$${marketCapB.toFixed(0)}B` },
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
