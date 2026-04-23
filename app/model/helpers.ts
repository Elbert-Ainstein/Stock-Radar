import type { StockData, ValuationMethod, ValuationMethodInfo } from "./types";

// ─── Helpers ───
export function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export function pct(n: number): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

export function clamp(val: number, min: number, max: number) {
  return Math.min(max, Math.max(min, val));
}

// ─── Gordon Growth Model ───
export function gordonPE(requiredReturn: number, terminalGrowth: number): number {
  const diff = requiredReturn - terminalGrowth;
  if (diff <= 0.005) return 200;
  return 1 / diff;
}

/**
 * Auto-detect the most appropriate valuation method for a stock.
 *
 * Decision framework (from institutional practice):
 *   1. Is earnings predictable? -> P/E (forward preferred over trailing)
 *   2. Is it early growth / no earnings? -> P/S
 *   3. Are cashflows meaningful? -> FCF metrics (future enhancement)
 *   4. Is it event-driven/speculative? -> scenario weighting (handled in ScenarioSection)
 *   5. Always prefer forward metrics for growth/transformation stories
 *
 * Special cases:
 *   - High-growth AI/platform: P/S with forward revenue emphasis
 *   - Turnarounds: forward metrics + margin trajectory
 *   - Capital-intensive: EV/EBITDA (future enhancement)
 */
export function detectValuationMethod(stock: StockData): ValuationMethodInfo {
  // Respect explicit override from model_defaults (e.g., user analyzed and decided P/E is correct for RKLB)
  const explicitMethod = stock.target?.model_defaults?.valuation_method;

  const hasPE = (stock.peRatio > 0) || (stock.forwardPe > 0);
  const hasProfits = stock.operatingMarginPct > 0;
  const hasRevenue = stock.psRatio > 0;
  const isProfitable = hasPE && hasProfits;
  const isHighGrowth = stock.revenueGrowthPct > 30;
  const isThinMargin = stock.operatingMarginPct > 0 && stock.operatingMarginPct <= 5;

  // Rule 0: Explicit override -- user/analyst has manually chosen the method for this stock
  if (explicitMethod === "pe") {
    const d = stock.target?.model_defaults;
    return {
      method: "pe",
      label: "Earnings-based (P/E)",
      multipleLabel: "Forward P/E",
      justification: `${stock.ticker} uses P/E valuation based on target assumptions — ${d?.revenue_b ? `$${d.revenue_b}B revenue` : ""}, ${d?.op_margin ? `${(d.op_margin * 100).toFixed(0)}% op margin` : ""}, ${d?.pe_multiple ? `${d.pe_multiple}× P/E` : ""}.`,
      reasons: [
        "Valuation method set explicitly in target model — based on analyst research",
        ...(d?.revenue_b ? [`Target revenue of $${d.revenue_b}B (management guidance or analyst estimate)`] : []),
        ...(d?.op_margin ? [`Target operating margin of ${(d.op_margin * 100).toFixed(0)}%`] : []),
        ...(d?.pe_multiple ? [`P/E of ${d.pe_multiple}× based on peer/sector comparison`] : []),
      ],
    };
  }
  if (explicitMethod === "ps") {
    const d = stock.target?.model_defaults;
    return {
      method: "ps",
      label: "Revenue-based (P/S)",
      multipleLabel: "P/S Multiple",
      justification: `${stock.ticker} uses P/S valuation based on target assumptions — revenue-based model is more appropriate for this company's stage.`,
      reasons: [
        "Valuation method set explicitly in target model — based on analyst research",
        ...(d?.revenue_b ? [`Target revenue of $${d.revenue_b}B`] : []),
        ...(d?.ps_multiple ? [`P/S of ${d.ps_multiple}× based on peer/sector comparison`] : []),
      ],
    };
  }

  // Rule 1: Profitable with meaningful margins -> P/E
  if (isProfitable && stock.operatingMarginPct > 5 && !isThinMargin) {
    const reasons: string[] = [];
    // Prefer forward P/E per institutional practice
    if (stock.forwardPe > 0) reasons.push(`Forward P/E of ${stock.forwardPe.toFixed(1)}× — forward metrics preferred for growth stories`);
    else if (stock.peRatio > 0) reasons.push(`Trailing P/E of ${stock.peRatio.toFixed(1)}× — stable earnings history`);
    reasons.push(`Operating margin of ${stock.operatingMarginPct.toFixed(1)}% — sufficient for earnings-based valuation`);
    if (stock.earningsGrowthPct > 0) reasons.push(`Earnings growing ${stock.earningsGrowthPct.toFixed(0)}% — captures profitability trajectory`);
    if (isHighGrowth) reasons.push(`Despite ${stock.revenueGrowthPct.toFixed(0)}% revenue growth, earnings visibility makes P/E more precise than P/S`);
    reasons.push("Institutional consensus: P/E is the standard for profitable companies with predictable earnings");

    return {
      method: "pe",
      label: "Earnings-based (P/E)",
      multipleLabel: "Forward P/E",
      justification: `${stock.ticker} is profitable with ${stock.operatingMarginPct.toFixed(1)}% operating margins${stock.forwardPe > 0 ? ` and forward P/E of ${stock.forwardPe.toFixed(1)}×` : ""}, making earnings-based valuation the most reliable method.`,
      reasons,
    };
  }

  // Rule 2: Pre-profit, thin margins, or no P/E -> P/S
  const reasons: string[] = [];
  if (!hasPE && !hasProfits) {
    reasons.push("Pre-revenue or pre-profit — no earnings to value against");
  } else if (!hasPE) {
    reasons.push("No meaningful P/E available — negative or negligible earnings");
  } else if (isThinMargin) {
    reasons.push(`Operating margin only ${stock.operatingMarginPct.toFixed(1)}% — too thin for reliable earnings-based valuation`);
    reasons.push("Thin margins mean small changes in costs/revenue mix dramatically swing EPS, making P/E unreliable");
  }
  if (hasRevenue) reasons.push(`Current P/S of ${stock.psRatio.toFixed(1)}× provides market-comparable benchmark`);
  if (isHighGrowth) reasons.push(`Revenue growing ${stock.revenueGrowthPct.toFixed(0)}% — top-line growth is the primary value driver at this stage`);
  if (stock.grossMarginPct > 40) reasons.push(`Gross margin of ${stock.grossMarginPct.toFixed(0)}% indicates scalable unit economics — margins should expand with scale`);
  reasons.push("P/S is the institutional standard for high-growth, pre-profit companies where revenue trajectory and TAM capture matter more than current earnings");

  return {
    method: "ps",
    label: "Revenue-based (P/S)",
    multipleLabel: "P/S Multiple",
    justification: `${stock.ticker} ${!hasPE && !hasProfits ? "is pre-profit with no meaningful earnings" : isThinMargin ? `has thin ${stock.operatingMarginPct.toFixed(1)}% margins` : "lacks meaningful earnings"}, so revenue-based (P/S) valuation better captures its growth trajectory and TAM potential.`,
    reasons,
  };
}

/**
 * Build ValuationMethodInfo for cyclical mode.
 * Used when the engine returns valuation_method = "cyclical_normalized".
 */
export function cyclicalMethodInfo(ticker: string): ValuationMethodInfo {
  return {
    method: "cyclical",
    label: "Cyclical Normalized (EV/EBIT)",
    multipleLabel: "EV/EBIT",
    justification: `${ticker} uses normalized-earnings valuation — mid-cycle EBIT margins averaged over the business cycle, valued at a through-cycle EV/EBIT multiple (Damodaran approach).`,
    reasons: [
      "Cyclical archetype: current earnings may be at peak or trough — normalizing prevents buying at peak multiples",
      "Uses 5-10 year average EBIT margins as 'normalized' baseline",
      "Through-cycle EV/EBIT multiple reflects fair value across the full business cycle",
      "Cycle position indicator adjusts scenario spread (bear case models full cycle turn)",
    ],
  };
}

// ─── Core Equations ───
export function computeTargetPrice(
  revenueB: number,
  opMargin: number,
  taxRate: number,
  sharesM: number,
  peMultiple: number
): number {
  if (sharesM <= 0) return 0;
  const netIncomeB = revenueB * opMargin * (1 - taxRate);
  const eps = (netIncomeB * 1000) / sharesM; // revenue in B, shares in M -> EPS in dollars
  return eps * peMultiple;
}

export function computeTargetPricePS(
  revenueB: number,
  sharesM: number,
  psMultiple: number
): number {
  if (sharesM <= 0) return 0;
  const revenuePerShare = (revenueB * 1000) / sharesM; // revenue in B, shares in M -> RPS in dollars
  return revenuePerShare * psMultiple;
}

/**
 * Cyclical normalized-earnings valuation (Damodaran approach):
 *   Normalized EBIT = Revenue × Normalized EBIT Margin (mid-cycle average)
 *   Enterprise Value = Normalized EBIT × Through-cycle EV/EBIT multiple
 *   Equity Value = EV − Net Debt
 *   Price = Equity Value / Diluted Shares
 *
 * Cycle position adjusts the scenario spread (handled in engine), not the base price.
 */
export function computeTargetPriceCyclical(
  revenueB: number,
  normalizedEbitMargin: number,
  evEbitMultiple: number,
  sharesM: number,
  netDebtB: number = 0
): number {
  if (sharesM <= 0) return 0;
  const normalizedEbitB = revenueB * normalizedEbitMargin;
  const evB = normalizedEbitB * evEbitMultiple;
  const equityB = evB - netDebtB;
  if (equityB <= 0) return 0;
  return (equityB * 1000) / sharesM; // B to M conversion -> price per share
}

// ─── Sensitivity Matrix ───
export function buildSensitivityMatrix(
  baseRevenueB: number,
  opMargin: number,
  taxRate: number,
  sharesM: number,
  baseMultiple: number,
  method: ValuationMethod = "pe",
  netDebtB: number = 0
) {
  // For cyclical mode, the Y-axis is EBIT margins (not revenues) and X-axis is EV/EBIT multiples
  if (method === "cyclical") {
    // Margin rows: spread around normalized margin (opMargin is reused as normalized EBIT margin)
    const marginBase = opMargin;
    const marginStep = 0.03; // 3pp steps
    const margins = [
      marginBase - marginStep * 2,
      marginBase - marginStep,
      marginBase,
      marginBase + marginStep,
      marginBase + marginStep * 2,
    ].filter(m => m > -0.05).map(m => Math.round(m * 1000) / 1000);

    // Multiple columns (EV/EBIT)
    const mStep = Math.max(1, Math.round(baseMultiple * 0.15));
    const multiples = [
      baseMultiple - mStep * 2,
      baseMultiple - mStep,
      baseMultiple,
      baseMultiple + mStep,
      baseMultiple + mStep * 2,
    ].filter(p => p > 0).map(p => Math.round(p));

    const matrix = margins.map(mgn =>
      multiples.map(m => computeTargetPriceCyclical(baseRevenueB, mgn, m, sharesM, netDebtB))
    );

    const baseMarginIdx = margins.findIndex(m => Math.abs(m - marginBase) < 0.001);
    const baseMIdx = multiples.findIndex(p => p === Math.round(baseMultiple));

    return {
      revenues: margins, // repurposed as margins for cyclical
      multiples,
      matrix,
      baseRevIdx: baseMarginIdx >= 0 ? baseMarginIdx : 2,
      baseMIdx: baseMIdx >= 0 ? baseMIdx : 2,
      isCyclical: true,
    };
  }

  // Revenue rows: spread around base
  const revMin = Math.max(0.5, Math.floor(baseRevenueB * 0.6));
  const revMax = Math.ceil(baseRevenueB * 1.3);
  const revStep = Math.max(1, Math.round((revMax - revMin) / 5));
  const revenues: number[] = [];
  for (let r = revMin; r <= revMax + 0.01; r += revStep) revenues.push(Math.round(r));
  if (revenues.length < 4) {
    // fallback for small numbers
    for (let r = Math.max(1, baseRevenueB - 2); r <= baseRevenueB + 3; r++) revenues.push(r);
  }
  // Unique sorted
  const uniqueRevs = [...new Set(revenues)].sort((a, b) => a - b);

  // Multiple columns: 5 values centered on base
  const mStep = Math.max(method === "ps" ? 1 : 2, Math.round(baseMultiple * 0.15));
  const multiples = [
    baseMultiple - mStep * 2,
    baseMultiple - mStep,
    baseMultiple,
    baseMultiple + mStep,
    baseMultiple + mStep * 2,
  ].filter(p => p > 0).map(p => Math.round(p));

  const matrix = uniqueRevs.map(rev =>
    multiples.map(m =>
      method === "ps"
        ? computeTargetPricePS(rev, sharesM, m)
        : computeTargetPrice(rev, opMargin, taxRate, sharesM, m)
    )
  );

  const baseRevIdx = uniqueRevs.findIndex(r => r >= baseRevenueB - 0.5);
  const baseMIdx = multiples.findIndex(p => p === Math.round(baseMultiple));

  return { revenues: uniqueRevs, multiples, matrix, baseRevIdx: baseRevIdx >= 0 ? baseRevIdx : 0, baseMIdx: baseMIdx >= 0 ? baseMIdx : 2 };
}

// ─── Time Path ───
// Uses convex multiple compression via Gordon Growth Model at each quarterly step.
// The prompt instructs Claude to reason about front-loaded compression:
//   "the 30%→20% growth phase destroys more multiple than 10%→0%"
// This function now matches that convexity instead of linearly interpolating.
export function buildTimePath(
  baseRevenueB: number,
  revenueGrowthRate: number,
  opMargin: number,
  taxRate: number,
  sharesM: number,
  startMultiple: number,
  endMultiple: number,
  years: number,
  method: ValuationMethod = "pe",
  requiredReturn: number = 0.12
) {
  const path = [];
  const quarters = years * 4;

  // Derive implied terminal growth from the end multiple via Gordon Growth:
  //   endMultiple = 1 / (r - g_terminal)  →  g_terminal = r - 1/endMultiple
  // This gives us the growth rate the end multiple implies, so we can
  // interpolate growth (which decays) and let the multiple follow convexly.
  const impliedTerminalGrowth = endMultiple > 0
    ? Math.max(0, requiredReturn - 1 / endMultiple)
    : 0.02;

  // Starting growth = the rate that produces startMultiple via Gordon Growth
  const impliedStartGrowth = startMultiple > 0
    ? Math.max(0, requiredReturn - 1 / Math.min(startMultiple, 200))
    : revenueGrowthRate;

  for (let q = 0; q <= quarters; q++) {
    const t = q / 4;
    const rev = baseRevenueB * Math.pow(1 + revenueGrowthRate, t);

    // Growth decays linearly from start to terminal (same as engine)
    const growthAtT = impliedStartGrowth + (impliedTerminalGrowth - impliedStartGrowth) * (t / years);

    // Multiple follows convexly from Gordon Growth: P/E = 1/(r - g)
    // This is strictly convex in g: compression is front-loaded when
    // growth is high and decelerating, exactly matching the prompt's guidance.
    const multiple = gordonPE(requiredReturn, growthAtT);

    // Clamp to reasonable range to avoid infinity near r ≈ g
    const clampedMultiple = clamp(multiple, 1, 200);

    let price: number;
    if (method === "ps") {
      const rps = sharesM > 0 ? (rev * 1000) / sharesM : 0;
      price = rps * clampedMultiple;
    } else {
      const netIncomeB = rev * opMargin * (1 - taxRate);
      const eps = sharesM > 0 ? (netIncomeB * 1000) / sharesM : 0;
      price = eps * clampedMultiple;
    }
    path.push({
      year: Math.round(t * 100) / 100,
      revenue: rev,
      multiple: Math.round(clampedMultiple * 10) / 10,
      price: Math.round(price * 100) / 100,
    });
  }
  return path;
}

// ─── Constants used by CriteriaChecklist and ConfidenceMeter ───
export const WEIGHT_MULTIPLIER: Record<string, number> = { critical: 2, important: 1.5, monitoring: 1 };
export const WEIGHT_LABEL: Record<string, string> = { critical: "Critical", important: "Important", monitoring: "Monitoring" };
export const WEIGHT_DOT: Record<string, string> = {
  critical: "bg-white",
  important: "bg-gray-400",
  monitoring: "bg-gray-600",
};
export const VAR_LABELS: Record<string, string> = { R: "Revenue", M: "Margin", T: "Tax", S: "Capital Structure", P: "Multiple", E: "External/Macro" };
