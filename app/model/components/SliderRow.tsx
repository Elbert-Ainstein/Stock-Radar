"use client";

import { useState } from "react";
import { clamp } from "../helpers";

export default function SliderRow({
  label,
  value,
  onChange,
  min,
  max,
  step,
  format,
  parseInput,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  parseInput?: (raw: string) => number;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const pctPos = clamp(((value - min) / (max - min)) * 100, 0, 100);

  const handleEditSubmit = () => {
    const raw = editValue.replace(/[$%×xBM,\s]/gi, "");
    let parsed = parseInput ? parseInput(editValue) : parseFloat(raw);
    if (!isNaN(parsed)) {
      // Allow values outside slider range when typed manually
      onChange(parsed);
    }
    setEditing(false);
  };

  return (
    <div className="flex items-center gap-4 py-3 border-b border-[var(--border)] last:border-b-0">
      <span className="text-[13px] text-[var(--secondary)] min-w-[150px]">{label}</span>
      <div className="flex-1 relative">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={clamp(value, min, max)}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="w-full"
          style={{
            background: `linear-gradient(to right, var(--muted) 0%, var(--secondary) ${pctPos}%, var(--border) ${pctPos}%)`,
          }}
        />
      </div>
      {editing ? (
        <input
          autoFocus
          type="text"
          value={editValue}
          onChange={e => setEditValue(e.target.value)}
          onBlur={handleEditSubmit}
          onKeyDown={e => { if (e.key === "Enter") handleEditSubmit(); if (e.key === "Escape") setEditing(false); }}
          className="w-[80px] text-right text-[13px] font-mono font-medium px-2 py-1 rounded bg-[var(--bg)] border border-[var(--border-hover)] text-[var(--text)] outline-none"
        />
      ) : (
        <button
          onClick={() => { setEditValue(format(value)); setEditing(true); }}
          className="text-[13px] font-mono font-medium text-[var(--text)] min-w-[80px] text-right hover:text-[var(--accent-muted)] transition-colors cursor-text"
          title="Click to type a value"
        >
          {format(value)}
        </button>
      )}
    </div>
  );
}
