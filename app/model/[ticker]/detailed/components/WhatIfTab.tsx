"use client";

import { useMemo, useState } from "react";
import type { Payload } from "../types";
import { fmtDollar, fmtMM, fmtPct } from "../helpers";
import { Slider, WalkRow } from "./TableHelpers";

export default function WhatIfTab({ payload }: { payload: Payload }) {
  const base = payload.target.scenarios.base;
  const ttm = payload.target.ttm_revenue;
  const netDebt = payload.target.net_debt;
  const shares = payload.target.shares_diluted;
  const currentPrice = payload.target.current_price;
  const modelBasePrice = base.price;
  const isRevMultiple = payload.target.valuation_method === "revenue_multiple";
  const mcap = currentPrice * shares;
  const currentPS = ttm > 0 ? mcap / ttm : 10;

  // Editable drivers seeded from base scenario.
  const [g1, setG1] = useState(base.rev_growth_y1);
  const [gT, setGT] = useState(base.rev_growth_terminal);
  const [emb, setEmb] = useState(base.ebitda_margin_target);
  const [fmar, setFmar] = useState(base.fcf_sbc_margin_target);
  const [mEv, setMEv] = useState(base.ev_ebitda_multiple);
  const [mFcf, setMFcf] = useState(base.ev_fcf_sbc_multiple);
  const [wacc, setWacc] = useState(base.discount_rate);
  const [blend, setBlend] = useState(0.5); // EBITDA-method weight (0..1)
  // Revenue-multiple mode drivers
  const [termPS, setTermPS] = useState(Math.min(currentPS * 0.6, 25));

  const calc = useMemo(() => {
    const gMid = (g1 + gT) / 2;
    const y1 = ttm * (1 + g1);
    const y2 = y1 * (1 + gMid);
    const y3 = y2 * (1 + gT);

    if (isRevMultiple) {
      // Revenue-multiple path: Terminal EV = Y3 Revenue x terminal P/S
      const term_ev = y3 * termPS;
      const pv = term_ev / Math.pow(1 + wacc, 2);
      const equity = pv - netDebt;
      const price = shares > 0 ? Math.max(0, equity / shares) : 0;
      return {
        y1, y2, y3,
        y3_ebitda: y3 * emb,
        y3_fcf: y3 * fmar,
        ev_ebitda: 0,
        ev_fcf: 0,
        term_ev,
        pv,
        equity,
        price,
        upside_vs_current: currentPrice > 0 ? price / currentPrice - 1 : 0,
        delta_vs_model: modelBasePrice > 0 ? price / modelBasePrice - 1 : 0,
      };
    }

    // Standard EV/EBITDA path
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
  }, [g1, gT, emb, fmar, mEv, mFcf, wacc, blend, termPS, isRevMultiple, ttm, netDebt, shares, currentPrice, modelBasePrice]);

  const reset = () => {
    setG1(base.rev_growth_y1);
    setGT(base.rev_growth_terminal);
    setEmb(base.ebitda_margin_target);
    setFmar(base.fcf_sbc_margin_target);
    setMEv(base.ev_ebitda_multiple);
    setMFcf(base.ev_fcf_sbc_multiple);
    setWacc(base.discount_rate);
    setBlend(0.5);
    setTermPS(Math.min(currentPS * 0.6, 25));
  };

  return (
    <div className="space-y-4">
      <div className={`rounded-lg border text-xs p-3 ${
        isRevMultiple
          ? "border-violet-800 bg-violet-950/30 text-violet-200"
          : "border-amber-800 bg-amber-950/30 text-amber-200"
      }`}>
        {isRevMultiple ? (
          <>
            <span className="font-semibold">Revenue-Multiple mode.</span> This company is pre-profit or has
            extreme P/S — the engine uses P/S-based valuation instead of EV/EBITDA. Adjust the terminal P/S
            multiple and growth sliders to explore scenarios. Current P/S: {currentPS.toFixed(1)}x.
          </>
        ) : (
          <>
            <span className="font-semibold">What-if mode.</span> These sliders let you explore how the
            price responds to each driver. The engine&apos;s base scenario is preserved elsewhere — this
            tab is computed client-side only and does not overwrite the saved model.
          </>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/30 p-4 space-y-3">
          <div className="text-xs uppercase tracking-wider text-neutral-400 mb-1">Drivers</div>
          <Slider label="Rev growth Y1" value={g1} onChange={setG1} min={-0.5} max={3.0} step={0.005} fmt={fmtPct} />
          <Slider label="Rev growth terminal" value={gT} onChange={setGT} min={-0.1} max={1.0} step={0.005} fmt={fmtPct} />
          {isRevMultiple ? (
            <Slider label="Terminal P/S multiple (Y3)" value={termPS} onChange={setTermPS} min={1} max={50} step={0.5} fmt={(v) => `${v.toFixed(1)}x`} />
          ) : (
            <>
              <Slider label="EBITDA margin target" value={emb} onChange={setEmb} min={0} max={0.7} step={0.005} fmt={fmtPct} />
              <Slider label="FCF \u2212 SBC margin target" value={fmar} onChange={setFmar} min={-0.1} max={0.6} step={0.005} fmt={fmtPct} />
              <Slider label="EV / EBITDA multiple" value={mEv} onChange={setMEv} min={2} max={80} step={0.5} fmt={(v) => `${v.toFixed(1)}x`} />
              <Slider label="EV / (FCF \u2212 SBC) multiple" value={mFcf} onChange={setMFcf} min={5} max={120} step={0.5} fmt={(v) => `${v.toFixed(1)}x`} />
            </>
          )}
          <Slider label="WACC (discount rate)" value={wacc} onChange={setWacc} min={0.05} max={0.25} step={0.0025} fmt={fmtPct} />
          {!isRevMultiple && (
            <Slider label="EBITDA-method blend weight" value={blend} onChange={setBlend} min={0} max={1} step={0.05} fmt={(v) => `${(v * 100).toFixed(0)}% / ${((1 - v) * 100).toFixed(0)}%`} />
          )}
          <div className="pt-2">
            <button
              onClick={reset}
              className="text-xs bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded px-3 py-1.5"
            >
              Reset to engine base
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <div className={`rounded-lg border p-4 ${
            isRevMultiple
              ? "border-violet-700 bg-violet-950/30"
              : "border-blue-700 bg-blue-950/30"
          }`}>
            <div className={`text-xs uppercase tracking-wider mb-1 ${
              isRevMultiple ? "text-violet-300" : "text-blue-300"
            }`}>
              Live recomputed price {isRevMultiple && <span className="normal-case">(P/S method)</span>}
            </div>
            <div className={`text-4xl font-mono font-semibold ${
              isRevMultiple ? "text-violet-100" : "text-blue-100"
            }`}>
              {fmtDollar(calc.price)}
            </div>
            <div className="mt-2 flex gap-4 text-xs">
              <div>
                <span className="text-neutral-400">vs current </span>
                <span className={calc.upside_vs_current >= 0 ? "text-emerald-300" : "text-rose-300"}>
                  {calc.upside_vs_current >= 0 ? "+" : ""}
                  {fmtPct(calc.upside_vs_current)}
                </span>
              </div>
              <div>
                <span className="text-neutral-400">vs engine base </span>
                <span className={calc.delta_vs_model >= 0 ? "text-emerald-300" : "text-rose-300"}>
                  {calc.delta_vs_model >= 0 ? "+" : ""}
                  {fmtPct(calc.delta_vs_model)}
                </span>
              </div>
              <div>
                <span className="text-neutral-400">Engine base </span>
                <span className="font-mono">{fmtDollar(modelBasePrice)}</span>
              </div>
              <div>
                <span className="text-neutral-400">Current </span>
                <span className="font-mono">{fmtDollar(currentPrice)}</span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-neutral-800 bg-neutral-900/30 overflow-hidden">
            <div className="px-3 py-2 bg-neutral-900 text-xs uppercase tracking-wider text-neutral-400">
              Live calculation walk {isRevMultiple && <span className="text-violet-400 normal-case">(P/S method)</span>}
            </div>
            <table className="w-full text-sm">
              <tbody>
                <WalkRow label="TTM Revenue" formula="input" value={fmtMM(ttm)} />
                <WalkRow label="Y1 Revenue" formula="= TTM \u00d7 (1 + g\u2081)" value={fmtMM(calc.y1)} />
                <WalkRow label="Y2 Revenue" formula="= Y1 \u00d7 (1 + g_mid)" value={fmtMM(calc.y2)} />
                <WalkRow label="Y3 Revenue" formula="= Y2 \u00d7 (1 + g_T)" value={fmtMM(calc.y3)} highlight />
                {isRevMultiple ? (
                  <>
                    <WalkRow label="Current P/S" formula="= Mkt Cap / TTM Rev" value={`${currentPS.toFixed(1)}x`} />
                    <WalkRow label="Terminal P/S (Y3)" formula="growth-decay adjusted" value={`${termPS.toFixed(1)}x`} />
                    <WalkRow label="Terminal EV" formula={`= Y3_Rev \u00d7 ${termPS.toFixed(1)}x P/S`} value={fmtMM(calc.term_ev)} highlight />
                  </>
                ) : (
                  <>
                    <WalkRow label="Y3 EBITDA" formula="= Y3_Rev \u00d7 EBITDA_margin" value={fmtMM(calc.y3_ebitda)} />
                    <WalkRow label="Y3 FCF \u2212 SBC" formula="= Y3_Rev \u00d7 FCF_margin" value={fmtMM(calc.y3_fcf)} />
                    <WalkRow label="EV via EBITDA" formula="= Y3_EBITDA \u00d7 EV/EBITDA_mult" value={fmtMM(calc.ev_ebitda)} />
                    <WalkRow label="EV via FCF-SBC" formula="= Y3_FCF \u00d7 EV/FCF_mult" value={fmtMM(calc.ev_fcf)} />
                    <WalkRow label="Terminal EV (blend)" formula="= w \u00d7 EV_EBITDA + (1\u2212w) \u00d7 EV_FCF" value={fmtMM(calc.term_ev)} />
                  </>
                )}
                <WalkRow label="PV of Terminal EV" formula="= Term_EV / (1+WACC)\u00b2" value={fmtMM(calc.pv)} />
                <WalkRow label="Equity value" formula="= PV \u2212 Net_Debt" value={fmtMM(calc.equity)} />
                <WalkRow label="Price per share" formula="= Equity / Shares" value={fmtDollar(calc.price)} highlight />
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
