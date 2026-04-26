"use client";

import { useState, useEffect, useRef } from "react";
import type { EnginePayload, ValuationMethodInfo } from "../types";

export function useEnginePayload(
  selectedTicker: string,
  priceHorizonMonths: number,
  valMethodInfo: ValuationMethodInfo,
  defaultOpMargin: number,
  defaultTaxRate: number,
  defaultMultiple: number,
  setRevenue: (v: number) => void,
  setOpMargin: (v: number) => void,
  setSharesM: (v: number) => void,
  setMultiple: (v: number) => void,
) {
  const [enginePayload, setEnginePayload] = useState<EnginePayload | null>(null);
  const [engineLoading, setEngineLoading] = useState(false);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [usedAnalystFallback, setUsedAnalystFallback] = useState(false);
  const appliedEngineRef = useRef<string | null>(null);

  // Fetch engine payload on ticker or horizon change
  useEffect(() => {
    appliedEngineRef.current = null;
    setEnginePayload(null);
    setEngineError(null);
    setEngineLoading(true);
    setUsedAnalystFallback(false);
    let cancelled = false;
    fetch(`/api/model/${selectedTicker}?horizon=${priceHorizonMonths}`)
      .then(r => r.json())
      .then((d: EnginePayload) => {
        if (cancelled) return;
        if (d.error) {
          setEngineError(d.error);
          setEnginePayload(null);
        } else {
          setEnginePayload(d);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setEngineError(e.message);
      })
      .finally(() => {
        if (!cancelled) setEngineLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedTicker, priceHorizonMonths]);

  // Apply engine values to sliders once per ticker
  useEffect(() => {
    if (!enginePayload) return;
    if (appliedEngineRef.current === enginePayload.ticker) return;
    const eng = enginePayload.target;
    const base = eng.scenarios?.base;
    if (!base) return;

    const currentPrice = eng.current_price ?? 0;
    const engineBase = eng.base ?? 0;
    const analystBase = (enginePayload as any).analyst_scenarios?.base?.price ?? 0;
    const analystDefaults = (enginePayload as any).analyst_model_defaults;

    // Detect if engine price is garbage: < 10% of current price AND analyst has a
    // much better answer. This catches cyclical-at-trough, negative-EBITDA EV/EBITDA,
    // and other cases where the engine's auto-routing produces nonsense.
    const engineIsGarbage = currentPrice > 0 && engineBase > 0 &&
      engineBase < currentPrice * 0.1 &&
      analystBase > engineBase * 3;

    if (engineIsGarbage && analystDefaults) {
      // Use analyst model_defaults to populate sliders instead
      console.log(
        `[useEnginePayload] ${enginePayload.ticker}: engine base $${engineBase.toFixed(0)} is garbage ` +
        `(< 10% of current $${currentPrice.toFixed(0)}). Using analyst defaults: base $${analystBase}`
      );
      const ad = analystDefaults;
      const vm = ad.valuation_method || valMethodInfo.method;

      if (ad.revenue_b && ad.revenue_b > 0) setRevenue(Math.round(ad.revenue_b * 10) / 10);
      if (ad.shares_m && ad.shares_m > 0) setSharesM(Math.round(ad.shares_m));

      if (vm === "ps") {
        if (ad.ps_multiple && ad.ps_multiple > 0) setMultiple(Math.round(ad.ps_multiple));
      } else {
        if (ad.op_margin && ad.op_margin > 0) setOpMargin(Math.round(ad.op_margin * 1000) / 1000);
        if (ad.pe_multiple && ad.pe_multiple > 0) setMultiple(Math.round(ad.pe_multiple));
      }

      setUsedAnalystFallback(true);
      appliedEngineRef.current = enginePayload.ticker;
      return;
    }

    const isCyclical = eng.valuation_method === "cyclical";
    const y3 = eng.forecast_annual?.[2];
    const isPS = valMethodInfo.method === "ps";

    const rev_raw = y3?.revenue ?? base.terminal_revenue ?? eng.ttm_revenue ?? 0;
    const rev_b = rev_raw / 1e9;

    const shares_m = (eng.shares_diluted ?? 0) / 1e6;

    if (isCyclical) {
      // Cyclical mode: populate normalized EBIT margin and EV/EBIT from drivers
      const normMargin = eng.drivers?.ebit_margin_normalized ?? defaultOpMargin;
      const evEbit = eng.drivers?.ev_ebit_multiple ?? 12;

      if (rev_b > 0) setRevenue(Math.round(rev_b * 10) / 10);
      if (normMargin > 0) setOpMargin(Math.round(normMargin * 1000) / 1000);
      if (shares_m > 0) setSharesM(Math.round(shares_m));
      if (evEbit > 0 && isFinite(evEbit)) setMultiple(Math.round(evEbit));
    } else if (isPS) {
      const rps = rev_b > 0 && shares_m > 0 ? (rev_b * 1000) / shares_m : 0;
      const ps = rps > 0 ? eng.base / rps : defaultMultiple;

      if (rev_b > 0) setRevenue(Math.round(rev_b * 10) / 10);
      if (shares_m > 0) setSharesM(Math.round(shares_m));
      if (ps > 0 && isFinite(ps)) setMultiple(Math.max(1, Math.round(ps)));
    } else {
      const oi_b = (y3?.operating_income ?? 0) / 1e9;
      const op_mgn = rev_b > 0 && oi_b > 0 ? oi_b / rev_b : defaultOpMargin;
      const tax = eng.drivers?.tax_rate ?? defaultTaxRate;
      const netIncB = rev_b * op_mgn * (1 - tax);
      const eps = netIncB > 0 && shares_m > 0 ? (netIncB * 1000) / shares_m : 0;
      const pe = eps > 0 ? eng.base / eps : defaultMultiple;

      if (rev_b > 0) setRevenue(Math.round(rev_b * 10) / 10);
      if (op_mgn > 0) setOpMargin(Math.round(op_mgn * 1000) / 1000);
      if (shares_m > 0) setSharesM(Math.round(shares_m));
      if (pe > 0 && isFinite(pe)) setMultiple(Math.max(5, Math.round(pe)));
    }

    appliedEngineRef.current = enginePayload.ticker;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enginePayload]);

  return { enginePayload, engineLoading, engineError, usedAnalystFallback };
}
