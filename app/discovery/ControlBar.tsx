import React from "react";

interface ControlBarProps {
  running: boolean;
  filter: "all" | "shortlist" | "validated";
  sectorFilter: string;
  sectors: string[];
  shortlistCount: number;
  validatedCount: number;
  totalCandidates: number;
  onStartScan: (quick: boolean) => void;
  onFilterChange: (f: "all" | "shortlist" | "validated") => void;
  onSectorChange: (s: string) => void;
}

export default function ControlBar({
  running,
  filter,
  sectorFilter,
  sectors,
  shortlistCount,
  validatedCount,
  totalCandidates,
  onStartScan,
  onFilterChange,
  onSectorChange,
}: ControlBarProps) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => onStartScan(false)}
          disabled={running}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            running
              ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
              : "bg-gradient-to-r from-amber-500 to-orange-600 text-white hover:shadow-lg hover:shadow-amber-500/20"
          }`}
        >
          {running ? "Scanning..." : "Run Full Scan"}
        </button>
        <button
          onClick={() => onStartScan(true)}
          disabled={running}
          className={`px-4 py-2 rounded-lg text-sm font-medium border transition-all ${
            running
              ? "border-zinc-700 text-zinc-500 cursor-not-allowed"
              : "border-[var(--border)] text-[var(--text)] hover:border-amber-500/50"
          }`}
        >
          Quick Scan (100)
        </button>
      </div>

      <div className="flex items-center gap-3">
        {/* Stage filter */}
        <div className="flex rounded-lg border border-[var(--border)] overflow-hidden text-xs">
          {validatedCount > 0 && (
            <button
              onClick={() => onFilterChange("validated")}
              className={`px-3 py-1.5 transition-colors ${
                filter === "validated" ? "bg-violet-500/20 text-violet-400" : "text-[var(--muted)] hover:text-[var(--text)]"
              }`}
            >
              AI Validated ({validatedCount})
            </button>
          )}
          <button
            onClick={() => onFilterChange("shortlist")}
            className={`px-3 py-1.5 transition-colors ${
              filter === "shortlist" ? "bg-amber-500/20 text-amber-400" : "text-[var(--muted)] hover:text-[var(--text)]"
            }`}
          >
            Shortlist ({shortlistCount})
          </button>
          <button
            onClick={() => onFilterChange("all")}
            className={`px-3 py-1.5 transition-colors ${
              filter === "all" ? "bg-amber-500/20 text-amber-400" : "text-[var(--muted)] hover:text-[var(--text)]"
            }`}
          >
            All ({totalCandidates})
          </button>
        </div>

        {/* Sector filter */}
        <select
          value={sectorFilter}
          onChange={e => onSectorChange(e.target.value)}
          className="bg-[var(--card)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-xs text-[var(--text)]"
        >
          <option value="">All sectors</option>
          {sectors.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
    </div>
  );
}
