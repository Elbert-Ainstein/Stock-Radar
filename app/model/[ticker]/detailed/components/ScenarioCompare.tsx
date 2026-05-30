"use client";

/**
 * ScenarioCompare — Phase 1b 3-up scenario comparison cards.
 *
 * Three columns side-by-side: engine base / active edit / a chosen comparison
 * scenario from the saved list. Each card shows:
 *   - scenario name + computed price + upside vs current
 *   - driver values rendered as a table; rows are highlighted when the driver
 *     differs from the engine base (so the user can see "what's different
 *     about this scenario at a glance")
 *
 * The active card always reflects the user's current edits (live recompute);
 * the other two cards show their saved snapshots.
 */
import { useEffect, useState } from "react";
import type { Payload } from "../types";
import {
  type Drivers,
  type CalcResult,
  computeWhatIf,
} from "../lib/whatif-engine";
import { fmtDollar, fmtPct } from "../helpers";

interface SavedScenario {
  id: string;
  scenario_name: string;
  drivers: Drivers;
  computed_price: number;
  upside_vs_current: number | null;
  delta_vs_model: number | null;
  spot_at_save: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  /** "revenue_multiple" | "ev_ebitda" | null. Pre-2026-05-09b rows are null. */
  valuation_method?: "revenue_multiple" | "ev_ebitda" | null;
}

const DRIVER_DISPLAY: Array<{ key: keyof Drivers; label: string; fmt: (v: number) => string; isPct: boolean }> = [
  { key: "rev_growth_y1",       label: "Y1 rev growth",     fmt: (v) => `${(v * 100).toFixed(1)}%`, isPct: true },
  { key: "rev_growth_terminal", label: "Terminal growth",   fmt: (v) => `${(v * 100).toFixed(1)}%`, isPct: true },
  { key: "ebitda_margin",       label: "EBITDA margin",     fmt: (v) => `${(v * 100).toFixed(1)}%`, isPct: true },
  { key: "fcf_sbc_margin",      label: "FCF−SBC margin",    fmt: (v) => `${(v * 100).toFixed(1)}%`, isPct: true },
  { key: "ev_ebitda_multiple",  label: "EV/EBITDA mult",    fmt: (v) => `${v.toFixed(1)}x`,         isPct: false },
  { key: "ev_fcf_multiple",     label: "EV/FCF mult",       fmt: (v) => `${v.toFixed(1)}x`,         isPct: false },
  { key: "wacc",                label: "WACC",              fmt: (v) => `${(v * 100).toFixed(2)}%`, isPct: true },
  { key: "blend",               label: "Blend (EBITDA wt)", fmt: (v) => `${(v * 100).toFixed(0)}%`, isPct: true },
];

interface Props {
  baseDrivers: Drivers;
  activeDrivers: Drivers;
  activeName: string;
  activeCalc: CalcResult;
  saved: SavedScenario[];
  payload: Payload;
  currentPrice: number;
}

export default function ScenarioCompare({
  baseDrivers, activeDrivers, activeName, activeCalc, saved, payload, currentPrice,
}: Props) {
  const baseCalc = computeWhatIf(baseDrivers, payload);

  // Compare-against scenario: default to first saved if available, else null.
  // useState() runs once at first render — at that point saved is [] because
  // loadSaved() in WhatIfTab is still in flight. The useEffect below fires
  // when saved arrives so the third card auto-populates instead of staying
  // empty for every returning user with prior scenarios.
  const [compareName, setCompareName] = useState<string>(saved[0]?.scenario_name || "");
  useEffect(() => {
    if (!compareName && saved.length > 0) setCompareName(saved[0].scenario_name);
  }, [saved, compareName]);
  const compare = saved.find((s) => s.scenario_name === compareName);
  const compareCalc = compare ? computeWhatIf(compare.drivers, payload) : null;

  // Mode-mismatch flag: shown as a small badge on the compare card so the
  // user knows the recomputed price is using current-mode math on drivers
  // saved under a different mode. Pre-2026-05-09b rows have null mode and
  // are treated as "unknown" (no badge) since we can't tell what mode they
  // were saved in.
  const currentMode: "revenue_multiple" | "ev_ebitda" =
    payload.target.valuation_method === "revenue_multiple" ? "revenue_multiple" : "ev_ebitda";
  const compareModeMismatch = !!(compare?.valuation_method && compare.valuation_method !== currentMode);

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/30">
      <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400 flex items-center justify-between">
        <span>Scenario comparison · drivers diffed against engine base</span>
        <div className="flex items-center gap-2 text-[10px] normal-case">
          <span className="text-neutral-500">compare-vs:</span>
          <select
            value={compareName}
            onChange={(e) => setCompareName(e.target.value)}
            className="bg-neutral-800 text-neutral-200 text-[11px] rounded px-1.5 py-0.5 border border-neutral-700"
            disabled={saved.length === 0}
          >
            {saved.length === 0 && <option>(no saved scenarios)</option>}
            {saved.map((s) => (
              <option key={s.id} value={s.scenario_name}>{s.scenario_name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 p-3">
        <ScenarioCard
          title="Engine base"
          subtitle="system"
          drivers={baseDrivers}
          baseDrivers={baseDrivers}
          price={baseCalc.price}
          upside={baseCalc.upside_vs_current}
          currentPrice={currentPrice}
          accent="neutral"
        />
        <ScenarioCard
          title={activeName}
          subtitle="editing"
          drivers={activeDrivers}
          baseDrivers={baseDrivers}
          price={activeCalc.price}
          upside={activeCalc.upside_vs_current}
          currentPrice={currentPrice}
          accent="emerald"
        />
        {compare && compareCalc ? (
          <ScenarioCard
            title={compare.scenario_name}
            subtitle={compareModeMismatch ? "saved · mode mismatch" : "saved"}
            drivers={compare.drivers}
            baseDrivers={baseDrivers}
            price={compareCalc.price}
            upside={compareCalc.upside_vs_current}
            currentPrice={currentPrice}
            accent="violet"
            modeMismatch={compareModeMismatch}
          />
        ) : (
          <div className="rounded-md border border-dashed border-neutral-700 bg-neutral-950 p-4 flex items-center justify-center text-xs text-neutral-500 italic text-center">
            Save a scenario to populate this slot. The comparison highlights<br />
            which drivers differ between scenarios.
          </div>
        )}
      </div>
    </div>
  );
}

function ScenarioCard({
  title, subtitle, drivers, baseDrivers, price, upside, currentPrice, accent, modeMismatch,
}: {
  title: string;
  subtitle: string;
  drivers: Drivers;
  baseDrivers: Drivers;
  price: number;
  upside: number;
  currentPrice: number;
  accent: "neutral" | "emerald" | "violet";
  modeMismatch?: boolean;
}) {
  const accentBg = modeMismatch
    ? "bg-amber-950/40 border-amber-700"
    : accent === "emerald"
    ? "bg-emerald-950/40 border-emerald-700"
    : accent === "violet"
      ? "bg-violet-950/40 border-violet-700"
      : "bg-neutral-950 border-neutral-700";
  const accentInk = accent === "emerald"
    ? "text-emerald-300"
    : accent === "violet"
      ? "text-violet-300"
      : "text-neutral-400";

  return (
    <div className={`rounded-md border p-3 ${accentBg}`}>
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <div>
          <div className="text-sm font-semibold text-neutral-100 truncate" title={title}>{title}</div>
          <div className={`text-[9px] uppercase tracking-wider ${accentInk}`}>{subtitle}</div>
        </div>
      </div>
      <div className="font-mono text-2xl font-semibold text-neutral-100 mb-1">{fmtDollar(price)}</div>
      <div className={`text-[11px] font-mono mb-3 ${upside >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
        {upside >= 0 ? "+" : ""}{fmtPct(upside)} vs {fmtDollar(currentPrice)}
      </div>

      <div className="border-t border-neutral-800 pt-2">
        <table className="w-full text-[10.5px] font-mono">
          <tbody>
            {DRIVER_DISPLAY.map(({ key, label, fmt }) => {
              const v = drivers[key];
              const baseV = baseDrivers[key];
              if (typeof v !== "number" || typeof baseV !== "number") return null;
              const isDiff = Math.abs(v - baseV) > 1e-9;
              const deltaPct = baseV !== 0 ? ((v - baseV) / Math.abs(baseV)) * 100 : 0;
              return (
                <tr key={String(key)} className={isDiff ? "bg-amber-900/20" : ""}>
                  <td className="py-0.5 pr-2 text-neutral-400 truncate">{label}</td>
                  <td className="py-0.5 pr-1 text-right text-neutral-100">{fmt(v)}</td>
                  <td className="py-0.5 pl-1 text-right">
                    {isDiff && (
                      <span className={deltaPct >= 0 ? "text-emerald-400" : "text-rose-400"}>
                        {deltaPct >= 0 ? "+" : ""}{deltaPct.toFixed(0)}%
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
