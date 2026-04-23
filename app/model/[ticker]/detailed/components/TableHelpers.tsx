"use client";

import type { ScenarioResult } from "../types";

export function Summary({
  label,
  value,
  sub,
  emphasize,
}: {
  label: string;
  value: string;
  sub?: string;
  emphasize?: boolean;
}) {
  return (
    <div
      className={`rounded border p-3 ${
        emphasize
          ? "border-blue-700 bg-blue-950/30"
          : "border-neutral-800 bg-neutral-900/30"
      }`}
    >
      <div className="text-[10px] uppercase tracking-wider text-neutral-400">{label}</div>
      <div className="text-xl font-semibold">{value}</div>
      {sub && <div className="text-xs text-neutral-400">{sub}</div>}
    </div>
  );
}

export function Row({ label, cells, bold }: { label: string; cells: string[]; bold?: boolean }) {
  return (
    <tr className="border-t border-neutral-800">
      <td className={`px-3 py-1.5 ${bold ? "font-semibold" : "text-neutral-300"}`}>
        {label}
      </td>
      {cells.map((c, i) => (
        <td key={i} className="px-3 py-1.5 text-right font-mono">
          {c}
        </td>
      ))}
    </tr>
  );
}

export function ScenarioRow({
  label,
  order,
  scenarios,
  get,
  bold,
}: {
  label: string;
  order: Array<keyof Record<string, ScenarioResult>>;
  scenarios: Record<string, ScenarioResult>;
  get: (s: ScenarioResult) => string;
  bold?: boolean;
}) {
  return (
    <tr className="border-t border-neutral-800">
      <td className={`px-3 py-1.5 ${bold ? "font-semibold" : "text-neutral-300"}`}>
        {label}
      </td>
      {order.map((k) => (
        <td
          key={String(k)}
          className={`px-3 py-1.5 text-right font-mono ${
            k === "base" ? "bg-blue-950/20" : ""
          }`}
        >
          {get(scenarios[k as string])}
        </td>
      ))}
    </tr>
  );
}

export function DriverRow({
  label,
  order,
  scenarios,
  get,
}: {
  label: string;
  order: Array<"downside" | "base" | "upside">;
  scenarios: Record<string, ScenarioResult>;
  get: (s: ScenarioResult) => string;
}) {
  return (
    <tr className="border-t border-neutral-800">
      <td className="px-3 py-1.5 text-neutral-300 font-mono text-xs">{label}</td>
      {order.map((k) => (
        <td
          key={k}
          className={`px-3 py-1.5 text-right font-mono ${
            k === "base" ? "bg-blue-950/20 text-blue-200" : "text-neutral-300"
          }`}
        >
          {get(scenarios[k])}
        </td>
      ))}
    </tr>
  );
}

export function WalkRow({
  label,
  formula,
  value,
  highlight,
}: {
  label: string;
  formula: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <tr className={`border-t border-neutral-800 ${highlight ? "bg-neutral-900 font-semibold" : ""}`}>
      <td className="px-3 py-1 text-neutral-300 w-40">{label}</td>
      <td className="px-3 py-1 text-neutral-500 text-xs font-mono">{formula}</td>
      <td className="px-3 py-1 text-right font-mono">{value}</td>
    </tr>
  );
}

export function Slider({
  label,
  value,
  onChange,
  min,
  max,
  step,
  fmt,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  fmt: (v: number) => string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-neutral-300">{label}</span>
        <span className="font-mono text-blue-300">{fmt(value)}</span>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="flex-1 accent-blue-500"
        />
        <input
          type="number"
          value={Number(value.toFixed(4))}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (!isNaN(v)) onChange(v);
          }}
          step={step}
          className="w-20 bg-neutral-950 border border-neutral-700 rounded px-2 py-0.5 text-xs font-mono text-right"
        />
      </div>
    </div>
  );
}
