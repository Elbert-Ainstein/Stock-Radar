"use client";

import { cn, gordonPE } from "../helpers";

export default function GordonModel({
  reqReturn,
  termGrowth,
  onChangeR,
  onChangeG,
  onApply,
}: {
  reqReturn: number;
  termGrowth: number;
  onChangeR: (v: number) => void;
  onChangeG: (v: number) => void;
  onApply: (pe: number) => void;
}) {
  const pe = gordonPE(reqReturn, termGrowth);
  const valid = reqReturn > termGrowth;

  return (
    <div className="p-5 rounded-lg bg-[var(--bg)] border border-[var(--border)]">
      <div className="text-xs text-[var(--muted)] mb-4">Gordon Growth Model — P/E derivation: P/E = 1 / (r − g)</div>
      <div className="text-center mb-5">
        <span className="text-sm font-mono text-[var(--secondary)]">
          1 / ({(reqReturn * 100).toFixed(1)}% − {(termGrowth * 100).toFixed(1)}%) ={" "}
        </span>
        <span className={cn("text-2xl font-mono font-bold", valid ? "text-[var(--accent-muted)]" : "text-rose-400")}>
          {valid ? `${pe.toFixed(1)}\u00D7` : "invalid"}
        </span>
      </div>
      <div className="space-y-3">
        <div className="flex items-center gap-4">
          <span className="text-sm text-[var(--secondary)] min-w-[160px]">Required return (r)</span>
          <input type="range" min={0.05} max={0.20} step={0.005} value={reqReturn}
            onChange={e => onChangeR(parseFloat(e.target.value))}
            className="flex-1 h-[6px] rounded-full appearance-none cursor-pointer"
            style={{ background: `linear-gradient(to right, var(--muted) 0%, var(--secondary) ${((reqReturn - 0.05) / 0.15) * 100}%, var(--border) ${((reqReturn - 0.05) / 0.15) * 100}%)` }}
          />
          <span className="text-sm font-mono text-[var(--text)] min-w-[50px] text-right">{(reqReturn * 100).toFixed(1)}%</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-[var(--secondary)] min-w-[160px]">Terminal growth (g)</span>
          <input type="range" min={0.01} max={0.09} step={0.005} value={termGrowth}
            onChange={e => onChangeG(parseFloat(e.target.value))}
            className="flex-1 h-[6px] rounded-full appearance-none cursor-pointer"
            style={{ background: `linear-gradient(to right, var(--muted) 0%, var(--secondary) ${((termGrowth - 0.01) / 0.08) * 100}%, var(--border) ${((termGrowth - 0.01) / 0.08) * 100}%)` }}
          />
          <span className="text-sm font-mono text-[var(--text)] min-w-[50px] text-right">{(termGrowth * 100).toFixed(1)}%</span>
        </div>
      </div>
      {valid && (
        <button
          onClick={() => onApply(Math.round(pe * 10) / 10)}
          className="mt-4 text-xs px-4 py-2 rounded-lg bg-[var(--hover)] border border-[var(--border)] text-[var(--accent-muted)] hover:bg-[var(--hover)] transition-all"
        >
          Apply {pe.toFixed(1)}\u00D7 P/E to model
        </button>
      )}
    </div>
  );
}
