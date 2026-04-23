"use client";

import { useState, useEffect } from "react";
import { cn } from "./helpers";

interface ProviderStatus {
  name: string;
  available: boolean;
  keySet: boolean;
}

interface TestResult {
  passed: number;
  failed: number;
  total: number;
  lastRun: string;
  details: string;
}

interface PipelineHealth {
  lastRunId: string | null;
  lastRunAt: string | null;
  lastRunSuccess: boolean | null;
  scoutSuccessRate: number | null;
  scoutDetails: Record<string, any>;
  modelGenMeta: Record<string, any>;
}

interface HealthData {
  providers: ProviderStatus[];
  tests: TestResult;
  pipeline: PipelineHealth;
  timestamp: string;
}

export default function HealthPanel({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then(res => res.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) {
    return (
      <div className="border-b border-[var(--border)] bg-[var(--card)] px-6 py-4">
        <div className="max-w-[1400px] mx-auto">
          <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M6 1v2M6 9v2M1 6h2M9 6h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="animate-spin origin-center" style={{ transformBox: "fill-box" }}/>
            </svg>
            Loading health status...
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="border-b border-[var(--border)] bg-[var(--card)] px-6 py-3">
        <div className="max-w-[1400px] mx-auto flex items-center justify-between">
          <span className="text-xs text-[var(--danger)]">Failed to load health: {error}</span>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--text)] text-xs">Close</button>
        </div>
      </div>
    );
  }

  const { providers, tests, pipeline } = data;

  return (
    <div className="border-b border-[var(--border)] bg-[var(--card)]">
      <div className="max-w-[1400px] mx-auto px-6 py-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-[var(--text)]">System Health</span>
            <span className="text-[9px] text-[var(--faint)] font-mono">
              {new Date(data.timestamp).toLocaleTimeString()}
            </span>
          </div>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--text)] text-xs px-2">
            Close
          </button>
        </div>

        <div className="grid grid-cols-3 gap-6">
          {/* Data Providers */}
          <div>
            <h3 className="text-[10px] font-semibold text-[var(--muted)] uppercase tracking-wider mb-2">Data Providers</h3>
            <div className="space-y-1">
              {providers.map(p => (
                <div key={p.name} className="flex items-center justify-between text-xs">
                  <span className="text-[var(--secondary)]">{p.name}</span>
                  <span className={cn(
                    "flex items-center gap-1",
                    p.keySet ? "text-[var(--success)]" : "text-[var(--muted)]"
                  )}>
                    <span className={cn("w-1.5 h-1.5 rounded-full", p.keySet ? "bg-[var(--success)]" : "bg-[var(--muted)]")} />
                    {p.keySet ? "Active" : "No key"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Test Status */}
          <div>
            <h3 className="text-[10px] font-semibold text-[var(--muted)] uppercase tracking-wider mb-2">Regression Tests</h3>
            {tests.total > 0 ? (
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <div className={cn(
                    "text-2xl font-bold",
                    tests.failed === 0 ? "text-[var(--success)]" : "text-[var(--danger)]"
                  )}>
                    {tests.failed === 0 ? "PASS" : "FAIL"}
                  </div>
                  <div className="text-xs text-[var(--muted)]">
                    <div>{tests.passed} passed, {tests.failed} failed</div>
                    <div className="text-[9px] text-[var(--faint)]">{tests.total} total tests</div>
                  </div>
                </div>
                {/* Mini progress bar */}
                <div className="w-full h-1.5 bg-[var(--bg)] rounded-full overflow-hidden">
                  <div
                    className={cn("h-full rounded-full transition-all", tests.failed === 0 ? "bg-[var(--success)]" : "bg-[var(--danger)]")}
                    style={{ width: `${tests.total > 0 ? (tests.passed / tests.total) * 100 : 0}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="text-xs text-[var(--muted)]">No tests found</div>
            )}
          </div>

          {/* Pipeline Health */}
          <div>
            <h3 className="text-[10px] font-semibold text-[var(--muted)] uppercase tracking-wider mb-2">Last Pipeline Run</h3>
            {pipeline.lastRunAt ? (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "w-2 h-2 rounded-full",
                    pipeline.lastRunSuccess === true ? "bg-[var(--success)]" :
                    pipeline.lastRunSuccess === false ? "bg-[var(--danger)]" : "bg-[var(--muted)]"
                  )} />
                  <span className="text-xs text-[var(--secondary)]">
                    {pipeline.lastRunSuccess === true ? "Succeeded" :
                     pipeline.lastRunSuccess === false ? "Failed" : "Unknown"}
                  </span>
                  <span className="text-[9px] text-[var(--faint)] font-mono ml-auto">
                    {new Date(pipeline.lastRunAt).toLocaleString()}
                  </span>
                </div>
                {pipeline.scoutSuccessRate !== null && (
                  <div className="text-xs text-[var(--muted)]">
                    Scout success: <span className={cn(
                      "font-medium",
                      pipeline.scoutSuccessRate >= 0.8 ? "text-[var(--success)]" :
                      pipeline.scoutSuccessRate >= 0.5 ? "text-amber-500" : "text-[var(--danger)]"
                    )}>
                      {(pipeline.scoutSuccessRate * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
                {pipeline.lastRunId && (
                  <div className="text-[9px] text-[var(--faint)] font-mono truncate">
                    Run: {pipeline.lastRunId}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-[var(--muted)]">No pipeline runs recorded</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
