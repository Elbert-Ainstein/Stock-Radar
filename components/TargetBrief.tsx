"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

/**
 * TargetBrief — the brief slider view.
 *
 * Fetches /api/model/[ticker], renders the configured sliders, and re-fetches
 * on every slider change (debounced) so the price range + deduction chain
 * update live. The slider list is DRIVEN BY THE API RESPONSE (not hardcoded in
 * this component) — so the engine can swap out sliders per-ticker without
 * touching the frontend.
 */

type SliderDef = {
  key: string;
  label?: string;
  format?: "pct" | "mult" | string;
  min?: number;
  max?: number;
  step?: number;
  value: number;
  default: number;
};

type DeductionStep = {
  label: string;
  formula: string;
  value: number;
  unit: string;
};

type Payload = {
  ticker: string;
  name: string;
  sector: string;
  target: {
    current_price: number;
    low: number;
    base: number;
    high: number;
    upside_base_pct: number;
    upside_low_pct: number;
    upside_high_pct: number;
    steps: DeductionStep[];
    warnings?: string[];
  };
  sliders: SliderDef[];
  capitalization: {
    price: number;
    market_cap: number;
    shares_diluted: number;
    net_debt: number;
  };
  warnings?: string[];
  error?: string;
};

export default function TargetBrief({ ticker }: { ticker: string }) {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPayload = useCallback(
    async (over: Record<string, number>) => {
      setLoading(true);
      setError(null);
      try {
        const q = new URLSearchParams();
        for (const [k, v] of Object.entries(over)) {
          q.set(k, String(v));
        }
        const res = await fetch(`/api/model/${ticker}?${q.toString()}`, {
          cache: "no-store",
        });
        const data = await res.json();
        if (data.error) {
          setError(data.error);
        } else {
          setPayload(data);
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [ticker]
  );

  // Initial fetch
  useEffect(() => {
    fetchPayload({});
  }, [fetchPayload]);

  // Debounced re-fetch whenever overrides change
  useEffect(() => {
    if (Object.keys(overrides).length === 0) return;
    const t = setTimeout(() => fetchPayload(overrides), 180);
    return () => clearTimeout(t);
  }, [overrides, fetchPayload]);

  const onSlide = (key: string, value: number) => {
    setOverrides((o) => ({ ...o, [key]: value }));
  };

  const resetAll = () => {
    setOverrides({});
    fetchPayload({});
  };

  const sliders = payload?.sliders ?? [];
  const target = payload?.target;

  const fmtDollar = (n: number) =>
    n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  const fmtPct = (n: number) =>
    (n * 100).toLocaleString("en-US", { maximumFractionDigits: 1 }) + "%";

  const rangeColor = useMemo(() => {
    if (!target || !target.current_price) return "text-neutral-300";
    return target.upside_base_pct > 0 ? "text-emerald-400" : "text-rose-400";
  }, [target]);

  if (error) {
    return (
      <div className="rounded-lg border border-rose-700 bg-rose-950/40 p-4 text-rose-200">
        <div className="font-semibold">Cannot build model for {ticker}</div>
        <div className="text-sm mt-1 opacity-80">{error}</div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-neutral-400">
            Brief target
          </div>
          <div className="text-2xl font-semibold text-neutral-100">
            {payload?.ticker ?? ticker}
            {payload?.name && (
              <span className="ml-2 text-neutral-400 text-base font-normal">
                {payload.name}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={resetAll}
            className="text-xs text-neutral-400 hover:text-neutral-100 border border-neutral-700 rounded px-2 py-1"
          >
            Reset sliders
          </button>
          <a
            href={`/api/model/${ticker}/excel`}
            className="text-xs text-neutral-100 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded px-2 py-1"
          >
            ↓ Excel
          </a>
          <a
            href={`/model/${ticker}/detailed`}
            className="text-xs text-neutral-100 bg-blue-700 hover:bg-blue-600 rounded px-2 py-1"
          >
            Detailed view →
          </a>
        </div>
      </div>

      {/* Price range row */}
      {target && (
        <div className="grid grid-cols-4 gap-3 mb-5">
          <Stat label="Current" value={fmtDollar(target.current_price)} />
          <Stat
            label="Low"
            value={fmtDollar(target.low)}
            sub={fmtPct(target.upside_low_pct)}
            color="text-neutral-300"
          />
          <Stat
            label="Base"
            value={fmtDollar(target.base)}
            sub={fmtPct(target.upside_base_pct)}
            color={rangeColor}
            emphasize
          />
          <Stat
            label="High"
            value={fmtDollar(target.high)}
            sub={fmtPct(target.upside_high_pct)}
            color="text-neutral-300"
          />
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        {/* Sliders */}
        <div>
          <div className="text-xs uppercase tracking-wider text-neutral-400 mb-2">
            Drivers {loading && <span className="opacity-60">(updating…)</span>}
          </div>
          <div className="space-y-3">
            {sliders.map((s) => (
              <SliderRow
                key={s.key}
                slider={s}
                onChange={(v) => onSlide(s.key, v)}
                overridden={s.key in overrides}
              />
            ))}
          </div>
        </div>

        {/* Deduction chain */}
        <div>
          <div className="text-xs uppercase tracking-wider text-neutral-400 mb-2">
            Deduction chain
          </div>
          <div className="border border-neutral-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <tbody>
                {(target?.steps ?? []).map((step, i) => (
                  <tr
                    key={i}
                    className={`border-b border-neutral-800 last:border-b-0 ${
                      i % 2 === 0 ? "bg-neutral-950" : "bg-neutral-900/40"
                    }`}
                  >
                    <td className="px-3 py-2 text-neutral-300 whitespace-nowrap">
                      {step.label}
                    </td>
                    <td className="px-3 py-2 text-neutral-500 text-xs font-mono">
                      {step.formula}
                    </td>
                    <td className="px-3 py-2 text-right text-neutral-100 font-mono whitespace-nowrap">
                      {formatStep(step)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {payload?.warnings && payload.warnings.length > 0 && (
        <div className="mt-4 rounded border border-amber-800 bg-amber-950/30 text-amber-200 text-xs p-2">
          <div className="font-semibold mb-1">Warnings</div>
          <ul className="list-disc pl-4 space-y-0.5">
            {payload.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  color,
  emphasize,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
  emphasize?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border ${
        emphasize ? "border-blue-700 bg-blue-950/40" : "border-neutral-800 bg-neutral-900/40"
      } p-3`}
    >
      <div className="text-[10px] uppercase tracking-wider text-neutral-400">
        {label}
      </div>
      <div
        className={`text-lg font-semibold ${color ?? "text-neutral-100"}`}
      >
        {value}
      </div>
      {sub && (
        <div className={`text-xs ${color ?? "text-neutral-400"}`}>{sub}</div>
      )}
    </div>
  );
}

function SliderRow({
  slider,
  onChange,
  overridden,
}: {
  slider: SliderDef;
  onChange: (v: number) => void;
  overridden: boolean;
}) {
  const min = slider.min ?? 0;
  const max = slider.max ?? 1;
  const step = slider.step ?? 0.01;
  const display =
    slider.format === "pct"
      ? (slider.value * 100).toLocaleString("en-US", { maximumFractionDigits: 1 }) + "%"
      : slider.format === "mult"
      ? slider.value.toFixed(1) + "x"
      : slider.value.toFixed(2);

  return (
    <div>
      <div className="flex justify-between items-baseline mb-1">
        <label className="text-xs text-neutral-400">
          {slider.label ?? slider.key}
          {overridden && (
            <span className="ml-2 text-[10px] text-amber-400">(custom)</span>
          )}
        </label>
        <span className="text-sm font-mono text-neutral-100">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={slider.value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-blue-500"
      />
    </div>
  );
}

function formatStep(s: DeductionStep): string {
  if (s.unit === "$") {
    return s.value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    });
  }
  if (s.unit === "$B") {
    return `$${s.value.toLocaleString("en-US", { maximumFractionDigits: 2 })}B`;
  }
  if (s.unit === "%") {
    return `${s.value.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
  }
  if (s.unit === "x") {
    return `${s.value.toFixed(1)}x`;
  }
  return `${s.value.toLocaleString("en-US", { maximumFractionDigits: 2 })}${s.unit}`;
}
