"use client";

/**
 * SensitivityHeatmap — Phase 1b component.
 *
 * 5x5 (default) or 7x7 (toggle) grid. Picks the top-2 drivers from the tornado
 * automatically — no user choice needed; the tornado already ranked them by
 * impact. Each cell perturbs both drivers ±25% from base in equal steps, then
 * computes the resulting price via the same engine as WhatIfTab.
 *
 * Color scale (per Hume's spec): midpoint at currentPrice. Cells with price
 * BELOW current shade red (downside), cells ABOVE shade green (upside). White-
 * ish at the current-price line. This makes the "which corner is dangerous"
 * pattern immediately visible.
 *
 * The 5x5 vs 7x7 toggle: 5x5 is 25 cells, very readable. 7x7 is 49 cells, finer
 * resolution at the cost of density. Hume confirmed 5x5 default.
 */
import { useMemo, useState } from "react";
import type { Payload } from "../types";
import {
  type Drivers,
  type TornadoEntry,
  computeWhatIf,
} from "../lib/whatif-engine";
import { fmtDollar } from "../helpers";

interface Props {
  baseDrivers: Drivers;
  payload: Payload;
  tornado: TornadoEntry[];
  currentPrice: number;
}

const PERTURB_RANGE = 0.25;  // ±25% from base value across the grid
const SIZES = [5, 7] as const;
type GridSize = (typeof SIZES)[number];

/** Map a price to a CSS background color, midpoint = currentPrice. */
function priceToColor(price: number, current: number, vmin: number, vmax: number): string {
  if (price >= current) {
    // Green scale: 0..1 from current to vmax
    const t = vmax > current ? Math.min(1, (price - current) / (vmax - current)) : 0;
    // Tailwind emerald-500 is rgb(16, 185, 129); blend toward it from white
    const r = Math.round(255 - t * (255 - 16));
    const g = Math.round(255 - t * (255 - 185));
    const b = Math.round(255 - t * (255 - 129));
    return `rgb(${r}, ${g}, ${b})`;
  } else {
    // Red scale: 0..1 from vmin to current
    const t = vmin < current ? Math.min(1, (current - price) / (current - vmin)) : 0;
    // Tailwind rose-500 is rgb(244, 63, 94)
    const r = Math.round(255 - t * (255 - 244));
    const g = Math.round(255 - t * (255 - 63));
    const b = Math.round(255 - t * (255 - 94));
    return `rgb(${r}, ${g}, ${b})`;
  }
}

/** Generate the N values for an axis, centered on baseValue ±PERTURB_RANGE. */
function axisValues(baseValue: number, n: GridSize): number[] {
  const out: number[] = [];
  const step = (2 * PERTURB_RANGE) / (n - 1);
  for (let i = 0; i < n; i++) {
    out.push(baseValue * (1 - PERTURB_RANGE + i * step));
  }
  return out;
}

const DRIVER_FMT: Record<string, (v: number) => string> = {
  rev_growth_y1: (v) => `${(v * 100).toFixed(1)}%`,
  rev_growth_terminal: (v) => `${(v * 100).toFixed(1)}%`,
  ebitda_margin: (v) => `${(v * 100).toFixed(1)}%`,
  fcf_sbc_margin: (v) => `${(v * 100).toFixed(1)}%`,
  ev_ebitda_multiple: (v) => `${v.toFixed(1)}x`,
  ev_fcf_multiple: (v) => `${v.toFixed(1)}x`,
  wacc: (v) => `${(v * 100).toFixed(2)}%`,
  blend: (v) => `${(v * 100).toFixed(0)}%`,
  term_ps: (v) => `${v.toFixed(1)}x`,
};
function fmtDriver(k: keyof Drivers, v: number): string {
  return (DRIVER_FMT[k as string] || ((x: number) => x.toFixed(2)))(v);
}

export default function SensitivityHeatmap({
  baseDrivers, payload, tornado, currentPrice,
}: Props) {
  const [size, setSize] = useState<GridSize>(5);

  // Top-2 drivers by spread; if tornado has fewer, gracefully degrade.
  // Memoized: without this, slice(0,2) returns a fresh array reference every
  // render → defeats the grid's useMemo and re-runs 25-49 computeWhatIf calls
  // on every parent re-render (e.g. every slider drag in WhatIfTab).
  const top2 = useMemo(() => tornado.slice(0, 2), [tornado]);

  const grid = useMemo(() => {
    if (top2.length < 2) return null;
    const xKey = top2[0].driver;
    const yKey = top2[1].driver;
    const xBase = baseDrivers[xKey] as number;
    const yBase = baseDrivers[yKey] as number;
    if (typeof xBase !== "number" || typeof yBase !== "number") return null;

    const xs = axisValues(xBase, size);
    const ys = axisValues(yBase, size);
    const cells: number[][] = [];
    let vmin = Infinity, vmax = -Infinity;
    for (let r = 0; r < size; r++) {
      const row: number[] = [];
      for (let c = 0; c < size; c++) {
        const drivers: Drivers = {
          ...baseDrivers,
          [xKey]: xs[c],
          [yKey]: ys[r],
        };
        const p = computeWhatIf(drivers, payload).price;
        row.push(p);
        if (p < vmin) vmin = p;
        if (p > vmax) vmax = p;
      }
      cells.push(row);
    }
    return { xKey, yKey, xs, ys, cells, vmin, vmax, xLabel: top2[0].label, yLabel: top2[1].label };
  }, [baseDrivers, payload, top2, size]);

  if (!grid) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/30 p-4 text-xs text-neutral-500 italic">
        Sensitivity heatmap unavailable — tornado has fewer than 2 numeric drivers.
      </div>
    );
  }

  const { xKey, yKey, xs, ys, cells, vmin, vmax, xLabel, yLabel } = grid;

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/30">
      <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400 flex items-center justify-between">
        <span>
          Sensitivity · <span className="text-neutral-200">{xLabel}</span>
          <span className="text-neutral-500"> × </span>
          <span className="text-neutral-200">{yLabel}</span>
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] normal-case text-neutral-500">
            current: <span className="font-mono text-neutral-300">{fmtDollar(currentPrice)}</span>
          </span>
          <div className="flex gap-0">
            {SIZES.map((s) => (
              <button
                key={s}
                onClick={() => setSize(s)}
                className={`px-2 py-0.5 text-[10px] border ${
                  size === s
                    ? "bg-neutral-700 text-neutral-100 border-neutral-600"
                    : "bg-neutral-900 text-neutral-400 border-neutral-700 hover:bg-neutral-800"
                } ${s === SIZES[0] ? "rounded-l" : ""} ${s === SIZES[SIZES.length - 1] ? "rounded-r" : ""}`}
              >
                {s}×{s}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="p-3 overflow-x-auto">
        <table className="text-[11px] font-mono mx-auto" style={{ borderCollapse: "separate", borderSpacing: 1 }}>
          <thead>
            <tr>
              <th className="px-1 py-1 text-right text-neutral-500 font-normal" style={{ width: 80 }}>
                {yLabel} ↓ / {xLabel} →
              </th>
              {xs.map((x, i) => (
                <th key={i} className="px-1 py-1 text-center text-neutral-400 font-normal" style={{ minWidth: 56 }}>
                  {fmtDriver(xKey, x)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* Iterate ys top-down (highest at top). Note: ys array is low→high, so reverse for display */}
            {[...cells].reverse().map((row, rIdx) => {
              const yIdxOriginal = cells.length - 1 - rIdx;
              return (
                <tr key={rIdx}>
                  <td className="px-1 py-1 text-right text-neutral-300">
                    {fmtDriver(yKey, ys[yIdxOriginal])}
                  </td>
                  {row.map((price, cIdx) => {
                    const bg = priceToColor(price, currentPrice, vmin, vmax);
                    // Choose ink color based on luminance for legibility
                    const t = price >= currentPrice
                      ? (vmax > currentPrice ? (price - currentPrice) / (vmax - currentPrice) : 0)
                      : (vmin < currentPrice ? (currentPrice - price) / (currentPrice - vmin) : 0);
                    const ink = t > 0.5 ? "#fff" : "#1c1917";
                    return (
                      <td
                        key={cIdx}
                        title={`${xLabel} ${fmtDriver(xKey, xs[cIdx])} × ${yLabel} ${fmtDriver(yKey, ys[yIdxOriginal])} → ${fmtDollar(price)}`}
                        style={{
                          background: bg,
                          color: ink,
                          padding: "5px 6px",
                          textAlign: "center",
                          minWidth: 56,
                          fontWeight: 600,
                          letterSpacing: "0.01em",
                          borderRadius: 2,
                        }}
                      >
                        {fmtDollar(price)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="mt-2 text-[10px] text-neutral-500">
          Each cell perturbs the top-2 drivers ±{(PERTURB_RANGE * 100).toFixed(0)}% from current values.
          Green = upside vs current price, red = downside. Color saturation maps to magnitude.
        </div>
      </div>
    </div>
  );
}
