/**
 * Pure recompute function for the what-if sandbox.
 *
 * Extracted from WhatIfTab so the scenario manager can call it on ANY set of
 * drivers — not just the currently-edited ones — to populate saved scenarios,
 * power the tornado chart's per-driver perturbations, and feed the sensitivity
 * heatmap's NxN grid. Single source of truth for the math.
 *
 * This mirrors the engine's symbolic walk in target_engine.py, kept on the
 * client because the math is cheap (microseconds per call) and we want
 * sub-frame responsiveness on slider drags.
 */
import type { Payload } from "../types";

export interface Drivers {
  rev_growth_y1: number;          // 0..1+ (e.g. 0.35 = +35% Y1 revenue)
  rev_growth_terminal: number;    // 0..1 terminal growth
  ebitda_margin: number;          // 0..1 EBITDA margin target
  fcf_sbc_margin: number;         // 0..1 FCF/SBC margin target
  ev_ebitda_multiple: number;     // multiple, e.g. 20
  ev_fcf_multiple: number;        // multiple, e.g. 28
  wacc: number;                   // 0..1 discount rate
  blend: number;                  // 0..1 EBITDA-method weight
  term_ps?: number | null;        // for revenue-multiple mode
}

export interface CalcResult {
  y1: number;
  y2: number;
  y3: number;
  y3_ebitda: number;
  y3_fcf: number;
  ev_ebitda: number;
  ev_fcf: number;
  term_ev: number;
  pv: number;
  equity: number;
  price: number;
  upside_vs_current: number;       // (price - current) / current
  delta_vs_model: number;          // (price - engine_base) / engine_base
}

/** Build a Drivers object from the engine's base scenario. */
export function driversFromBase(payload: Payload, currentPS: number): Drivers {
  const base = payload.target.scenarios.base;
  return {
    rev_growth_y1: base.rev_growth_y1,
    rev_growth_terminal: base.rev_growth_terminal,
    ebitda_margin: base.ebitda_margin_target,
    fcf_sbc_margin: base.fcf_sbc_margin_target,
    ev_ebitda_multiple: base.ev_ebitda_multiple,
    ev_fcf_multiple: base.ev_fcf_sbc_multiple,
    wacc: base.discount_rate,
    blend: 0.5,
    term_ps: Math.min(currentPS * 0.6, 25),
  };
}

/**
 * Compute the price + intermediate values from a Drivers object.
 * Branches on the engine's valuation_method.
 */
export function computeWhatIf(drivers: Drivers, payload: Payload): CalcResult {
  const base = payload.target.scenarios.base;
  const ttm = payload.target.ttm_revenue;
  const netDebt = payload.target.net_debt;
  const shares = payload.target.shares_diluted;
  const currentPrice = payload.target.current_price;
  const modelBasePrice = base.price;
  const isRevMultiple = payload.target.valuation_method === "revenue_multiple";

  const { rev_growth_y1: g1, rev_growth_terminal: gT, ebitda_margin: emb,
          fcf_sbc_margin: fmar, ev_ebitda_multiple: mEv, ev_fcf_multiple: mFcf,
          wacc, blend: blendRaw, term_ps: termPS } = drivers;
  // Clamp blend to [0,1]. The slider enforces this in the UI, but tornado /
  // heatmap perturbations multiply by (1±pct) and can push blend above 1.0,
  // which produces a negative weight on the (1-blend) leg and reverses the
  // heatmap's color monotonicity. Engine-side clamp = single source of truth.
  const blend = Math.min(1, Math.max(0, blendRaw));

  const gMid = (g1 + gT) / 2;
  const y1 = ttm * (1 + g1);
  const y2 = y1 * (1 + gMid);
  const y3 = y2 * (1 + gT);

  if (isRevMultiple) {
    const ps = termPS ?? 10;
    const term_ev = y3 * ps;
    const pv = term_ev / Math.pow(1 + wacc, 2);
    const equity = pv - netDebt;
    const price = shares > 0 ? Math.max(0, equity / shares) : 0;
    return {
      y1, y2, y3,
      y3_ebitda: y3 * emb,
      y3_fcf: y3 * fmar,
      ev_ebitda: 0,
      ev_fcf: 0,
      term_ev, pv, equity, price,
      upside_vs_current: currentPrice > 0 ? price / currentPrice - 1 : 0,
      delta_vs_model: modelBasePrice > 0 ? price / modelBasePrice - 1 : 0,
    };
  }

  const y3_ebitda = y3 * emb;
  const y3_fcf = y3 * fmar;
  const ev_ebitda = y3_ebitda * mEv;
  const ev_fcf = y3_fcf * mFcf;
  const term_ev = blend * ev_ebitda + (1 - blend) * ev_fcf;
  const pv = term_ev / Math.pow(1 + wacc, 2);
  const equity = pv - netDebt;
  const price = shares > 0 ? equity / shares : 0;
  return {
    y1, y2, y3, y3_ebitda, y3_fcf, ev_ebitda, ev_fcf, term_ev, pv, equity, price,
    upside_vs_current: currentPrice > 0 ? price / currentPrice - 1 : 0,
    delta_vs_model: modelBasePrice > 0 ? price / modelBasePrice - 1 : 0,
  };
}

/**
 * Tornado data: for each driver, perturb +/- pct (default 10%) and return
 * the absolute price spread. Used for ranking drivers by impact.
 *
 * One-at-a-time perturbation — does NOT model interactions. That's intentional
 * for a tornado (the whole point is "if I'm wrong about ONE thing, how bad
 * is it"). Interactions are surfaced by saving multi-driver scenarios.
 */
export interface TornadoEntry {
  driver: keyof Drivers;
  label: string;
  base_price: number;
  high_price: number;     // driver+pct
  low_price: number;      // driver-pct
  spread: number;         // |high - low|
}

const DRIVER_LABELS: Record<string, string> = {
  rev_growth_y1:        "Y1 revenue growth",
  rev_growth_terminal:  "Terminal growth",
  ebitda_margin:        "EBITDA margin",
  fcf_sbc_margin:       "FCF/SBC margin",
  ev_ebitda_multiple:   "EV/EBITDA multiple",
  ev_fcf_multiple:      "EV/FCF multiple",
  wacc:                 "WACC",
  blend:                "EBITDA method weight",
  term_ps:              "Terminal P/S",
};

export function buildTornado(
  baseDrivers: Drivers,
  payload: Payload,
  pct = 0.10
): TornadoEntry[] {
  const isRevMultiple = payload.target.valuation_method === "revenue_multiple";
  const baseCalc = computeWhatIf(baseDrivers, payload);
  const baseDriverList: (keyof Drivers)[] = isRevMultiple
    ? ["rev_growth_y1", "rev_growth_terminal", "term_ps", "wacc"]
    : ["rev_growth_y1", "rev_growth_terminal", "ebitda_margin",
       "fcf_sbc_margin", "ev_ebitda_multiple", "ev_fcf_multiple",
       "wacc", "blend"];

  const entries: TornadoEntry[] = [];
  for (const k of baseDriverList) {
    const baseVal = baseDrivers[k];
    if (typeof baseVal !== "number") continue;
    const high = computeWhatIf({ ...baseDrivers, [k]: baseVal * (1 + pct) }, payload);
    const low  = computeWhatIf({ ...baseDrivers, [k]: baseVal * (1 - pct) }, payload);
    entries.push({
      driver: k,
      label: DRIVER_LABELS[k as string] || String(k),
      base_price: baseCalc.price,
      high_price: high.price,
      low_price: low.price,
      spread: Math.abs(high.price - low.price),
    });
  }
  entries.sort((a, b) => b.spread - a.spread);
  return entries;
}
