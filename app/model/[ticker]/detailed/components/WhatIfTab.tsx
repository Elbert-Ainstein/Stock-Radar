"use client";

/**
 * WhatIfTab — Phase 1 scenario sandbox.
 *
 * Replaces the previous single-scenario slider tab with a full scenario manager:
 *   - Save/name/load/delete custom scenarios (persisted to Supabase via
 *     /api/scenarios/[ticker])
 *   - Tornado chart ranking drivers by absolute price impact
 *   - Live recompute on slider drag using the pure engine helper
 *     (lib/whatif-engine.ts)
 *
 * Phase 1b additions: 3-up scenario comparison cards, sensitivity heatmap on
 * top-2 drivers from the tornado, cross-mode mismatch warning when loading
 * a scenario saved under a different valuation_method.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────────────────┐
 *   │ Scenario rail (horizontal scroll): [Engine base][My bull][...]  │
 *   ├─────────────────────────────────────────────────────────────────┤
 *   │ 3-up comparison cards: base / active / saved                    │
 *   ├─────────────────────────────────────────────────────────────────┤
 *   │ Drivers              │ Live recomputed price + walk             │
 *   │ (sliders)            │                                          │
 *   ├─────────────────────────────────────────────────────────────────┤
 *   │ Tornado chart — drivers ranked by ±10% perturbation impact      │
 *   ├─────────────────────────────────────────────────────────────────┤
 *   │ Sensitivity heatmap — 5×5 / 7×7 on top-2 drivers from tornado   │
 *   └─────────────────────────────────────────────────────────────────┘
 */
import { useEffect, useMemo, useState } from "react";
import type { Payload } from "../types";
import { fmtDollar, fmtMM, fmtPct } from "../helpers";
import { Slider, WalkRow } from "./TableHelpers";
import {
  type Drivers,
  type CalcResult,
  type TornadoEntry,
  driversFromBase,
  computeWhatIf,
  buildTornado,
} from "../lib/whatif-engine";
import SensitivityHeatmap from "./SensitivityHeatmap";
import ScenarioCompare from "./ScenarioCompare";

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

export default function WhatIfTab({ payload, ticker }: { payload: Payload; ticker: string }) {
  const tk = ticker;

  const ttm = payload.target.ttm_revenue;
  const currentPrice = payload.target.current_price;
  const modelBasePrice = payload.target.scenarios.base.price;
  const isRevMultiple = payload.target.valuation_method === "revenue_multiple";
  const shares = payload.target.shares_diluted;
  const mcap = currentPrice * shares;
  const currentPS = ttm > 0 ? mcap / ttm : 10;

  const baseDrivers = useMemo(() => driversFromBase(payload, currentPS), [payload, currentPS]);

  // Active editable drivers — start at engine base
  const [drivers, setDrivers] = useState<Drivers>(baseDrivers);
  const [activeName, setActiveName] = useState<string>("Engine base");

  // Saved scenarios from Supabase
  const [saved, setSaved] = useState<SavedScenario[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [newName, setNewName] = useState("");
  // Cross-mode warning: surfaces when the user loads a scenario saved under
  // a different valuation_method (e.g. EV/EBITDA scenario loaded after the
  // engine flipped to revenue-multiple). Math still runs but driver semantics
  // diverge — flag so the user knows the comparison is suspect.
  const [modeWarning, setModeWarning] = useState<string | null>(null);
  const currentMode: "revenue_multiple" | "ev_ebitda" =
    payload.target.valuation_method === "revenue_multiple" ? "revenue_multiple" : "ev_ebitda";

  async function loadSaved() {
    if (!tk) return;
    setLoadingSaved(true);
    try {
      const res = await fetch(`/api/scenarios/${encodeURIComponent(tk)}`, { cache: "no-store" });
      const j = await res.json();
      setSaved(j.scenarios || []);
    } catch { /* network blip; non-fatal */ }
    finally { setLoadingSaved(false); }
  }

  useEffect(() => { loadSaved(); }, [tk]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live recompute
  const calc = useMemo(() => computeWhatIf(drivers, payload), [drivers, payload]);
  const tornado = useMemo(() => buildTornado(drivers, payload, 0.10), [drivers, payload]);

  // Driver setters (one per field)
  const set = <K extends keyof Drivers>(k: K, v: Drivers[K]) =>
    setDrivers((prev) => ({ ...prev, [k]: v }));

  const reset = () => {
    setDrivers(baseDrivers);
    setActiveName("Engine base");
    setModeWarning(null);
  };

  const loadScenario = (s: SavedScenario) => {
    setDrivers(s.drivers);
    setActiveName(s.scenario_name);
    // Mode-mismatch detection. s.valuation_method may be null for rows
    // saved before the 2026-05-09b migration — those are silently allowed
    // (we can't tell what mode they were saved in). For known-mode rows
    // that don't match the current engine, warn.
    if (s.valuation_method && s.valuation_method !== currentMode) {
      setModeWarning(
        `"${s.scenario_name}" was saved under ${s.valuation_method === "revenue_multiple" ? "revenue-multiple" : "EV/EBITDA"} valuation; ` +
        `current engine is using ${currentMode === "revenue_multiple" ? "revenue-multiple" : "EV/EBITDA"}. ` +
        `Driver semantics differ — the recomputed price may be misleading. Re-save under the current mode if you want to keep using it.`
      );
    } else {
      setModeWarning(null);
    }
  };

  const saveCurrentAs = async (name: string) => {
    setSaveError(null);
    if (!tk) { setSaveError("missing ticker"); return; }
    if (!name.trim()) { setSaveError("name required"); return; }
    try {
      const res = await fetch(`/api/scenarios/${encodeURIComponent(tk)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_name: name.trim(),
          drivers,
          computed_price: calc.price,
          upside_vs_current: calc.upside_vs_current,
          delta_vs_model: calc.delta_vs_model,
          spot_at_save: currentPrice,
          valuation_method: currentMode,
        }),
      });
      const j = await res.json();
      if (!res.ok || j.error) throw new Error(j.error || `HTTP ${res.status}`);
      setActiveName(name.trim());
      setShowSaveDialog(false);
      setNewName("");
      loadSaved();
    } catch (e: any) {
      setSaveError(e.message || "save failed");
    }
  };

  const deleteScenario = async (name: string) => {
    if (!tk) return;
    if (!confirm(`Delete scenario "${name}"?`)) return;
    try {
      await fetch(
        `/api/scenarios/${encodeURIComponent(tk)}?name=${encodeURIComponent(name)}`,
        { method: "DELETE" }
      );
      if (activeName === name) reset();
      loadSaved();
    } catch { /* swallow */ }
  };

  return (
    <div className="space-y-4">
      {/* Mode banner */}
      <div className={`rounded-lg border text-xs p-3 ${
        isRevMultiple
          ? "border-violet-800 bg-violet-950/30 text-violet-200"
          : "border-amber-800 bg-amber-950/30 text-amber-200"
      }`}>
        {isRevMultiple ? (
          <>
            <span className="font-semibold">Revenue-Multiple mode.</span> P/S-based valuation —
            adjust the terminal P/S multiple and growth sliders. Current P/S: {currentPS.toFixed(1)}x.
          </>
        ) : (
          <>
            <span className="font-semibold">What-if sandbox.</span> Save scenarios to compare
            them later. The engine&apos;s base scenario is preserved — this tab is a sandbox.
          </>
        )}
      </div>

      {/* Scenario rail */}
      <ScenarioRail
        activeName={activeName}
        baseDrivers={baseDrivers}
        baseCalc={computeWhatIf(baseDrivers, payload)}
        saved={saved}
        loading={loadingSaved}
        onSelectBase={reset}
        onSelect={loadScenario}
        onDelete={deleteScenario}
        onOpenSave={() => { setNewName(activeName === "Engine base" ? "" : `${activeName} (copy)`); setShowSaveDialog(true); }}
      />

      {showSaveDialog && (
        <SaveDialog
          name={newName}
          onChange={setNewName}
          onCancel={() => { setShowSaveDialog(false); setNewName(""); setSaveError(null); }}
          onSave={() => saveCurrentAs(newName)}
          error={saveError}
        />
      )}

      {modeWarning && (
        <div className="rounded-lg border border-amber-700 bg-amber-950/30 p-3 text-xs text-amber-200 flex items-start justify-between gap-3">
          <div className="flex-1"><span className="font-semibold">Mode mismatch.</span> {modeWarning}</div>
          <button
            onClick={() => setModeWarning(null)}
            className="text-amber-400 hover:text-amber-200 text-base leading-none"
            aria-label="Dismiss"
          >×</button>
        </div>
      )}

      {/* 3-up scenario comparison: engine base / active edit / chosen saved */}
      <ScenarioCompare
        baseDrivers={baseDrivers}
        activeDrivers={drivers}
        activeName={activeName}
        activeCalc={calc}
        saved={saved}
        payload={payload}
        currentPrice={currentPrice}
      />

      {/* Drivers + Output */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/30 p-4 space-y-3">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs uppercase tracking-wider text-neutral-400">
              Drivers <span className="text-neutral-500 normal-case">· editing &ldquo;{activeName}&rdquo;</span>
            </div>
            <button onClick={reset} className="text-[10px] text-neutral-400 hover:text-neutral-200">
              Reset to engine base
            </button>
          </div>
          <Slider label="Rev growth Y1" value={drivers.rev_growth_y1} onChange={(v) => set("rev_growth_y1", v)} min={-0.5} max={3.0} step={0.005} fmt={fmtPct} />
          <Slider label="Rev growth terminal" value={drivers.rev_growth_terminal} onChange={(v) => set("rev_growth_terminal", v)} min={-0.1} max={1.0} step={0.005} fmt={fmtPct} />
          {isRevMultiple ? (
            <Slider label="Terminal P/S multiple (Y3)" value={drivers.term_ps ?? 10} onChange={(v) => set("term_ps", v)} min={1} max={50} step={0.5} fmt={(v) => `${v.toFixed(1)}x`} />
          ) : (
            <>
              <Slider label="EBITDA margin target" value={drivers.ebitda_margin} onChange={(v) => set("ebitda_margin", v)} min={0} max={0.7} step={0.005} fmt={fmtPct} />
              <Slider label="FCF − SBC margin target" value={drivers.fcf_sbc_margin} onChange={(v) => set("fcf_sbc_margin", v)} min={-0.1} max={0.6} step={0.005} fmt={fmtPct} />
              <Slider label="EV / EBITDA multiple" value={drivers.ev_ebitda_multiple} onChange={(v) => set("ev_ebitda_multiple", v)} min={2} max={80} step={0.5} fmt={(v) => `${v.toFixed(1)}x`} />
              <Slider label="EV / (FCF − SBC) multiple" value={drivers.ev_fcf_multiple} onChange={(v) => set("ev_fcf_multiple", v)} min={5} max={120} step={0.5} fmt={(v) => `${v.toFixed(1)}x`} />
            </>
          )}
          <Slider label="WACC" value={drivers.wacc} onChange={(v) => set("wacc", v)} min={0.05} max={0.25} step={0.0025} fmt={fmtPct} />
          {!isRevMultiple && (
            <Slider label="EBITDA-method blend weight" value={drivers.blend} onChange={(v) => set("blend", v)} min={0} max={1} step={0.05} fmt={(v) => `${(v * 100).toFixed(0)}% / ${((1 - v) * 100).toFixed(0)}%`} />
          )}
        </div>

        <PriceCardAndWalk
          calc={calc}
          ttm={ttm}
          modelBasePrice={modelBasePrice}
          currentPrice={currentPrice}
          currentPS={currentPS}
          isRevMultiple={isRevMultiple}
          drivers={drivers}
        />
      </div>

      {/* Tornado */}
      <TornadoBars tornado={tornado} basePrice={calc.price} />

      {/* Sensitivity heatmap on top-2 drivers from the tornado */}
      <SensitivityHeatmap
        baseDrivers={drivers}
        payload={payload}
        tornado={tornado}
        currentPrice={currentPrice}
      />
    </div>
  );
}

// ─── ScenarioRail: horizontal cards ──────────────────────────────────────

function ScenarioRail({
  activeName, baseDrivers, baseCalc, saved, loading,
  onSelectBase, onSelect, onDelete, onOpenSave,
}: {
  activeName: string;
  baseDrivers: Drivers;
  baseCalc: CalcResult;
  saved: SavedScenario[];
  loading: boolean;
  onSelectBase: () => void;
  onSelect: (s: SavedScenario) => void;
  onDelete: (name: string) => void;
  onOpenSave: () => void;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/30">
      <div className="px-3 py-2 flex items-center justify-between border-b border-neutral-800">
        <div className="text-xs uppercase tracking-wider text-neutral-400">
          Scenarios {loading && <span className="text-neutral-500 normal-case">· loading…</span>}
        </div>
        <button
          onClick={onOpenSave}
          className="text-xs px-2.5 py-1 rounded bg-emerald-700/40 text-emerald-200 border border-emerald-700/60 hover:bg-emerald-700/60"
        >
          Save current as…
        </button>
      </div>
      <div className="px-3 py-3 flex gap-2 overflow-x-auto" style={{ scrollSnapType: "x mandatory" }}>
        <ScenarioCard
          name="Engine base"
          price={baseCalc.price}
          upside={baseCalc.upside_vs_current}
          isActive={activeName === "Engine base"}
          isSystemBase
          onSelect={onSelectBase}
        />
        {saved.map((s) => (
          <ScenarioCard
            key={s.id}
            name={s.scenario_name}
            price={s.computed_price}
            upside={s.upside_vs_current}
            isActive={activeName === s.scenario_name}
            onSelect={() => onSelect(s)}
            onDelete={() => onDelete(s.scenario_name)}
          />
        ))}
        {saved.length === 0 && !loading && (
          <div className="text-xs text-neutral-500 italic self-center pl-2">
            No saved scenarios yet — adjust drivers and click &ldquo;Save current as…&rdquo;
          </div>
        )}
      </div>
    </div>
  );
}

function ScenarioCard({
  name, price, upside, isActive, isSystemBase, onSelect, onDelete,
}: {
  name: string;
  price: number;
  upside: number | null;
  isActive: boolean;
  isSystemBase?: boolean;
  onSelect: () => void;
  onDelete?: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      style={{ flex: "0 0 auto", scrollSnapAlign: "start", cursor: "pointer", minWidth: 180 }}
      className={`rounded-md border p-2 transition-colors ${
        isActive ? "border-emerald-500 bg-emerald-950/40" : "border-neutral-700 bg-neutral-950 hover:border-neutral-500"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-neutral-100 truncate">{name}</div>
        {!isSystemBase && onDelete && (
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="text-[10px] text-neutral-500 hover:text-rose-400"
            title="Delete scenario"
          >×</button>
        )}
      </div>
      <div className="mt-1 font-mono text-base text-neutral-100">{fmtDollar(price)}</div>
      {upside != null && (
        <div className={`text-[10px] font-mono ${upside >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
          {upside >= 0 ? "+" : ""}{(upside * 100).toFixed(0)}% vs current
        </div>
      )}
      {isSystemBase && (
        <div className="text-[9px] uppercase tracking-wider text-neutral-500 mt-0.5">system</div>
      )}
    </div>
  );
}

function SaveDialog({
  name, onChange, onCancel, onSave, error,
}: {
  name: string;
  onChange: (v: string) => void;
  onCancel: () => void;
  onSave: () => void;
  error: string | null;
}) {
  return (
    <div className="rounded-lg border border-emerald-700/60 bg-emerald-950/30 p-3">
      <div className="text-xs text-emerald-200 mb-2">Name this scenario</div>
      <div className="flex gap-2">
        <input
          autoFocus
          value={name}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSave(); if (e.key === "Escape") onCancel(); }}
          maxLength={80}
          placeholder="e.g. Recession, AI capex +50%, Margin compression"
          className="flex-1 bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-sm text-neutral-100 placeholder:text-neutral-500"
        />
        <button onClick={onSave} className="px-3 py-1 rounded bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500">Save</button>
        <button onClick={onCancel} className="px-3 py-1 rounded border border-neutral-700 text-neutral-300 text-xs hover:bg-neutral-800">Cancel</button>
      </div>
      {error && <div className="mt-2 text-xs text-rose-400">{error}</div>}
    </div>
  );
}

function PriceCardAndWalk({
  calc, ttm, modelBasePrice, currentPrice, currentPS, isRevMultiple, drivers,
}: {
  calc: CalcResult;
  ttm: number;
  modelBasePrice: number;
  currentPrice: number;
  currentPS: number;
  isRevMultiple: boolean;
  drivers: Drivers;
}) {
  const termPS = drivers.term_ps ?? 10;
  return (
    <div className="space-y-3">
      <div className={`rounded-lg border p-4 ${
        isRevMultiple ? "border-violet-700 bg-violet-950/30" : "border-blue-700 bg-blue-950/30"
      }`}>
        <div className={`text-xs uppercase tracking-wider mb-1 ${
          isRevMultiple ? "text-violet-300" : "text-blue-300"
        }`}>
          Live recomputed price {isRevMultiple && <span className="normal-case">(P/S method)</span>}
        </div>
        <div className={`text-4xl font-mono font-semibold ${
          isRevMultiple ? "text-violet-100" : "text-blue-100"
        }`}>{fmtDollar(calc.price)}</div>
        <div className="mt-2 flex gap-4 text-xs flex-wrap">
          <div>
            <span className="text-neutral-400">vs current </span>
            <span className={calc.upside_vs_current >= 0 ? "text-emerald-300" : "text-rose-300"}>
              {calc.upside_vs_current >= 0 ? "+" : ""}{fmtPct(calc.upside_vs_current)}
            </span>
          </div>
          <div>
            <span className="text-neutral-400">vs engine base </span>
            <span className={calc.delta_vs_model >= 0 ? "text-emerald-300" : "text-rose-300"}>
              {calc.delta_vs_model >= 0 ? "+" : ""}{fmtPct(calc.delta_vs_model)}
            </span>
          </div>
          <div><span className="text-neutral-400">Engine base </span><span className="font-mono">{fmtDollar(modelBasePrice)}</span></div>
          <div><span className="text-neutral-400">Current </span><span className="font-mono">{fmtDollar(currentPrice)}</span></div>
        </div>
      </div>

      <div className="rounded-lg border border-neutral-800 bg-neutral-900/30 overflow-hidden">
        <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400">
          Live calculation walk {isRevMultiple && <span className="text-violet-400 normal-case">(P/S method)</span>}
        </div>
        <table className="w-full text-sm">
          <tbody>
            <WalkRow label="TTM Revenue" formula="input" value={fmtMM(ttm)} />
            <WalkRow label="Y1 Revenue" formula="= TTM × (1 + g₁)" value={fmtMM(calc.y1)} />
            <WalkRow label="Y2 Revenue" formula="= Y1 × (1 + g_mid)" value={fmtMM(calc.y2)} />
            <WalkRow label="Y3 Revenue" formula="= Y2 × (1 + g_T)" value={fmtMM(calc.y3)} highlight />
            {isRevMultiple ? (
              <>
                <WalkRow label="Current P/S" formula="= Mkt Cap / TTM Rev" value={`${currentPS.toFixed(1)}x`} />
                <WalkRow label="Terminal P/S (Y3)" formula="growth-decay adjusted" value={`${termPS.toFixed(1)}x`} />
                <WalkRow label="Terminal EV" formula={`= Y3_Rev × ${termPS.toFixed(1)}x P/S`} value={fmtMM(calc.term_ev)} highlight />
              </>
            ) : (
              <>
                <WalkRow label="Y3 EBITDA" formula="= Y3_Rev × EBITDA_margin" value={fmtMM(calc.y3_ebitda)} />
                <WalkRow label="Y3 FCF − SBC" formula="= Y3_Rev × FCF_margin" value={fmtMM(calc.y3_fcf)} />
                <WalkRow label="EV via EBITDA" formula="= Y3_EBITDA × EV/EBITDA_mult" value={fmtMM(calc.ev_ebitda)} />
                <WalkRow label="EV via FCF-SBC" formula="= Y3_FCF × EV/FCF_mult" value={fmtMM(calc.ev_fcf)} />
                <WalkRow label="Terminal EV (blend)" formula="= w × EV_EBITDA + (1−w) × EV_FCF" value={fmtMM(calc.term_ev)} />
              </>
            )}
            <WalkRow label="PV of Terminal EV" formula="= Term_EV / (1+WACC)²" value={fmtMM(calc.pv)} />
            <WalkRow label="Equity value" formula="= PV − Net_Debt" value={fmtMM(calc.equity)} />
            <WalkRow label="Price per share" formula="= Equity / Shares" value={fmtDollar(calc.price)} highlight />
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TornadoBars({ tornado, basePrice }: { tornado: TornadoEntry[]; basePrice: number }) {
  if (tornado.length === 0) return null;
  const maxSpread = Math.max(...tornado.map((t) => t.spread), 1);
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/30">
      <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400 flex items-center justify-between">
        <span>Tornado · drivers ranked by ±10% impact</span>
        <span className="normal-case text-neutral-500">
          base: <span className="font-mono text-neutral-300">{fmtDollar(basePrice)}</span>
        </span>
      </div>
      <div className="p-3 space-y-1.5">
        {tornado.map((t) => {
          const lowDelta = t.low_price - t.base_price;
          const highDelta = t.high_price - t.base_price;
          const lowFrac = Math.abs(lowDelta) / maxSpread;
          const highFrac = Math.abs(highDelta) / maxSpread;
          return (
            <div key={String(t.driver)} className="flex items-center gap-3 text-xs">
              <div className="w-44 text-neutral-300 truncate" title={t.label}>{t.label}</div>
              <div className="flex-1 flex items-center" style={{ minHeight: 18 }}>
                <div className="flex-1 flex justify-end pr-px">
                  <div
                    style={{ width: `${lowFrac * 100}%`, background: "var(--sr-neg, #c0392b)", height: 14, opacity: 0.8 }}
                    title={`-10% → ${fmtDollar(t.low_price)} (${fmtDollar(lowDelta)})`}
                  />
                </div>
                <div className="w-px bg-neutral-600" style={{ height: 16 }} />
                <div className="flex-1 flex pl-px">
                  <div
                    style={{ width: `${highFrac * 100}%`, background: "var(--sr-pos, #16a34a)", height: 14, opacity: 0.8 }}
                    title={`+10% → ${fmtDollar(t.high_price)} (${fmtDollar(highDelta)})`}
                  />
                </div>
              </div>
              <div className="w-24 font-mono text-right text-neutral-300">±{fmtDollar(t.spread / 2)}</div>
            </div>
          );
        })}
      </div>
      <div className="px-3 pb-3 text-[10px] text-neutral-500">
        Each bar shows the price change when the driver moves ±10% (others held constant).
        Sort: largest absolute spread first. Ranks <em>your</em> sensitivity to each input.
      </div>
    </div>
  );
}
