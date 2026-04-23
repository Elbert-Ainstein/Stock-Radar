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
  const appliedEngineRef = useRef<string | null>(null);

  // Fetch engine payload on ticker or horizon change
  useEffect(() => {
    appliedEngineRef.current = null;
    setEnginePayload(null);
    setEngineError(null);
    setEngineLoading(true);
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

    const y3 = eng.forecast_annual?.[2];
    const isPS = valMethodInfo.method === "ps";

    const rev_raw = y3?.revenue ?? base.terminal_revenue ?? eng.ttm_revenue ?? 0;
    const rev_b = rev_raw / 1e9;

    const oi_b = (y3?.operating_income ?? 0) / 1e9;
    const op_mgn = rev_b > 0 && oi_b > 0 ? oi_b / rev_b : defaultOpMargin;
    const tax = eng.drivers?.tax_rate ?? defaultTaxRate;
    const shares_m = (eng.shares_diluted ?? 0) / 1e6;

    if (isPS) {
      const rps = rev_b > 0 && shares_m > 0 ? (rev_b * 1000) / shares_m : 0;
      const ps = rps > 0 ? eng.base / rps : defaultMultiple;

      if (rev_b > 0) setRevenue(Math.round(rev_b * 10) / 10);
      if (shares_m > 0) setSharesM(Math.round(shares_m));
      if (ps > 0 && isFinite(ps)) setMultiple(Math.max(1, Math.round(ps)));
    } else {
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

  return { enginePayload, engineLoading, engineError };
}
