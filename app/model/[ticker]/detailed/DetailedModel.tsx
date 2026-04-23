"use client";

import { useEffect, useState } from "react";
import type { Payload, Tab, HorizonMonths } from "./types";
import { fmtDollar, fmtPct, tabLabel } from "./helpers";
import { Summary } from "./components/TableHelpers";
import SummaryTab from "./components/SummaryTab";
import IncomeTab from "./components/IncomeTab";
import CashTab from "./components/CashTab";
import ValuationTab from "./components/ValuationTab";
import FormulasTab from "./components/FormulasTab";
import WhatIfTab from "./components/WhatIfTab";

export default function DetailedModel({ ticker }: { ticker: string }) {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [horizon, setHorizon] = useState<HorizonMonths>(12);

  useEffect(() => {
    setPayload(null);
    setErr(null);
    fetch(`/api/model/${ticker}?horizon=${horizon}`)
      .then((r) => r.json())
      .then((d) => (d.error ? setErr(d.error) : setPayload(d)))
      .catch((e: Error) => setErr(e.message));
  }, [ticker, horizon]);

  if (err) {
    return (
      <div className="p-8 min-h-screen bg-neutral-950 text-rose-200">
        <div className="max-w-4xl mx-auto rounded-lg border border-rose-700 bg-rose-950/40 p-6">
          <div className="text-xl font-semibold">Cannot build model for {ticker}</div>
          <div className="mt-2 opacity-80">{err}</div>
          <a href={`/model?ticker=${ticker}`} className="inline-block mt-4 text-blue-300 hover:underline">
            ← Back
          </a>
        </div>
      </div>
    );
  }

  if (!payload) {
    return (
      <div className="p-8 min-h-screen bg-neutral-950 text-neutral-400">
        Loading {ticker} …
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-start justify-between mb-4">
          <div>
            <a href={`/model?ticker=${ticker}`} className="text-sm text-blue-400 hover:underline">
              ← Back to model picker
            </a>
            <h1 className="text-2xl font-semibold mt-1">
              {payload.ticker} — {payload.name}
            </h1>
            <div className="text-sm text-neutral-400">
              {payload.sector} · Source: yfinance (SEC filings)
            </div>
            <div className="text-xs text-neutral-400 mt-1 space-y-0.5">
              <div>
                <span className="text-neutral-500">Exit fundamentals: </span>
                <span className="text-neutral-200">
                  {payload.target.exit_fiscal_year || "Y3"} (Year 3)
                </span>
              </div>
              <div>
                <span className="text-neutral-500">Price target: </span>
                <span className="text-blue-300 font-medium">
                  {payload.target.price_horizon_months ?? horizon} months forward
                </span>
                {payload.target.price_target_date && (
                  <span className="text-neutral-400"> (≈ {payload.target.price_target_date})</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex flex-col items-end gap-1">
              <div className="text-[10px] uppercase tracking-wider text-neutral-500">
                Target horizon
              </div>
              <div className="inline-flex rounded border border-neutral-700 overflow-hidden">
                {([12, 24, 36] as HorizonMonths[]).map((h) => (
                  <button
                    key={h}
                    onClick={() => setHorizon(h)}
                    className={`px-3 py-1 text-xs transition-colors ${
                      horizon === h
                        ? "bg-blue-600 text-white"
                        : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                    }`}
                  >
                    {h}mo
                  </button>
                ))}
              </div>
            </div>
            <a
              href={`/api/model/${ticker}/excel?horizon=${horizon}`}
              className="text-sm bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded px-3 py-2"
            >
              ↓ Download Excel (live formulas)
            </a>
          </div>
        </div>

        {/* Valuation method badge */}
        {payload.target.valuation_method === "revenue_multiple" && (
          <div className="mb-3 rounded-lg border border-violet-700/50 bg-violet-950/30 text-violet-300 text-xs px-3 py-2 flex items-center gap-2">
            <span className="font-semibold">P/S Revenue-Multiple Method</span>
            <span className="text-violet-400/70">—</span>
            <span className="text-violet-400/70">Pre-profit or extreme P/S detected. Using revenue-based valuation instead of EV/EBITDA.</span>
          </div>
        )}

        {/* Target summary */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          <Summary label="Current" value={fmtDollar(payload.target.current_price)} />
          <Summary
            label="Downside"
            value={fmtDollar(payload.target.low)}
            sub={fmtPct(payload.target.upside_low_pct)}
          />
          <Summary
            label={payload.target.valuation_method === "revenue_multiple" ? "Base target (P/S)" : "Base target"}
            value={fmtDollar(payload.target.base)}
            sub={fmtPct(payload.target.upside_base_pct)}
            emphasize
          />
          <Summary
            label="Upside"
            value={fmtDollar(payload.target.high)}
            sub={fmtPct(payload.target.upside_high_pct)}
          />
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-4 border-b border-neutral-800">
          {(["summary", "income", "cashflow", "valuation", "formulas", "whatif"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm transition-colors ${
                tab === t
                  ? "border-b-2 border-blue-500 text-neutral-100"
                  : "text-neutral-400 hover:text-neutral-100"
              }`}
            >
              {tabLabel(t)}
            </button>
          ))}
        </div>

        {tab === "summary" && <SummaryTab payload={payload} />}
        {tab === "income" && <IncomeTab payload={payload} />}
        {tab === "cashflow" && <CashTab payload={payload} />}
        {tab === "valuation" && <ValuationTab payload={payload} />}
        {tab === "formulas" && <FormulasTab payload={payload} />}
        {tab === "whatif" && <WhatIfTab payload={payload} />}

        {payload.warnings && payload.warnings.length > 0 && (
          <div className="mt-6 rounded border border-amber-800 bg-amber-950/30 text-amber-200 text-xs p-3">
            <div className="font-semibold mb-1">Warnings</div>
            <ul className="list-disc pl-4 space-y-0.5">
              {payload.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
