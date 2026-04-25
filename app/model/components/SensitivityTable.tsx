"use client";

import { cn } from "../helpers";
import type { ValuationMethod } from "../types";

export default function SensitivityTable({
  revenues,
  multiples,
  matrix,
  targetPrice,
  currentPrice,
  baseRevIdx,
  baseMIdx,
  opMargin,
  taxRate,
  sharesM,
  method,
  multipleLabel,
}: {
  revenues: number[];
  multiples: number[];
  matrix: number[][];
  targetPrice: number;
  currentPrice: number;
  baseRevIdx: number;
  baseMIdx: number;
  opMargin: number;
  taxRate: number;
  sharesM: number;
  method: ValuationMethod;
  multipleLabel: string;
}) {
  function cellBg(price: number, isBase: boolean): string {
    if (price >= targetPrice * 1.05) return "bg-[#1a3a2a]"; // green -- above target
    if (price >= targetPrice * 0.85) return "bg-[#2a3a2a]"; // light green -- near target
    if (price >= currentPrice * 1.1) return "bg-[#2d2a1a]"; // yellow -- upside from current
    if (price >= currentPrice * 0.9) return "bg-[#2a2520]"; // cream -- near current
    return "bg-[#1e1e2e]"; // dark -- below current
  }

  function cellText(price: number): string {
    if (price >= targetPrice * 1.05) return "text-emerald-300";
    if (price >= targetPrice * 0.85) return "text-emerald-200/80";
    if (price >= currentPrice * 1.1) return "text-amber-200";
    if (price >= currentPrice * 0.9) return "text-[var(--secondary)]";
    return "text-[var(--secondary)]";
  }

  const isCyclical = method === "cyclical";
  const subtitle = isCyclical
    ? `Sensitivity — target price at varying EBIT margin \u00D7 EV/EBIT (${sharesM.toFixed(0)}M shares)`
    : method === "ps"
    ? `Sensitivity — target price at varying revenue \u00D7 P/S (${sharesM.toFixed(0)}M shares)`
    : `Sensitivity — target price at varying revenue \u00D7 P/E (${(opMargin * 100).toFixed(0)}% op margin, ${(taxRate * 100).toFixed(0)}% tax, ${sharesM.toFixed(0)}M shares)`;

  const rowLabel = isCyclical ? "EBIT Margin" : "Revenue";

  return (
    <div className="overflow-x-auto">
      <div className="text-sm text-[var(--secondary)] mb-3">{subtitle}</div>
      <table className="w-full text-sm font-mono border-collapse">
        <thead>
          <tr>
            <th className="py-2.5 px-3 text-left text-[var(--muted)] text-xs font-normal">{rowLabel} ↓ / {multipleLabel} →</th>
            {multiples.map((m, j) => (
              <th
                key={m}
                className={cn(
                  "py-2.5 px-3 text-center text-xs",
                  j === baseMIdx ? "text-[#60a5fa] font-bold bg-[#60a5fa]/5" : "text-[var(--secondary)] font-normal"
                )}
              >
                {m}×
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {revenues.map((rev, i) => (
            <tr key={i} className={cn(i === baseRevIdx && "bg-[#60a5fa]/3")}>
              <td className={cn(
                "py-2.5 px-3 text-[var(--secondary)] font-semibold border-t border-[var(--border)]",
                i === baseRevIdx && "text-[var(--text)]"
              )}>
                {isCyclical ? `${(rev * 100).toFixed(0)}%` : `$${rev}B`}
              </td>
              {matrix[i].map((price, j) => {
                const isBase = i === baseRevIdx && j === baseMIdx;
                return (
                  <td
                    key={j}
                    className={cn(
                      "py-2.5 px-3 text-center border-t border-[var(--border)]",
                      cellBg(price, isBase),
                      cellText(price),
                      isBase && "font-bold ring-1 ring-[#60a5fa]/40"
                    )}
                  >
                    ${Math.round(price).toLocaleString()}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
