import type { DeductionStep, Tab } from "./types";

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function fmtDollar(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return "\u2014";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return "\u2014";
  return (n * 100).toLocaleString("en-US", { maximumFractionDigits: 1 }) + "%";
}

export function fmtMM(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return "\u2014";
  return "$" + (n / 1e6).toLocaleString("en-US", { maximumFractionDigits: 0 }) + "mm";
}

export function fmtStep(s: DeductionStep): string {
  if (s.unit === "$") return fmtDollar(s.value);
  if (s.unit === "$B") return `$${s.value.toFixed(2)}B`;
  if (s.unit === "%") return `${s.value.toFixed(1)}%`;
  if (s.unit === "x") return `${s.value.toFixed(1)}x`;
  if (s.unit === "M") return `${s.value.toFixed(1)}M`;
  return `${s.value.toFixed(2)}${s.unit}`;
}

export function tabLabel(t: Tab): string {
  return {
    summary: "P&L Summary",
    income: "Income Stmt",
    cashflow: "Cash Flow",
    valuation: "Valuation",
    formulas: "\u0192x Formulas",
    whatif: "What-if",
  }[t];
}
