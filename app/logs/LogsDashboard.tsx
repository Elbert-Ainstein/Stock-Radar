"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";

// ─── Types ───

interface LogEntry {
  id: number;
  created_at: string;
  category: string;
  level: "info" | "warn" | "error";
  ticker: string | null;
  source: string;
  title: string;
  message: string;
  run_id: string | null;
  metadata: Record<string, any>;
  duration_ms: number | null;
}

interface LogsResponse {
  logs: LogEntry[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Constants ───

const CATEGORIES = [
  { value: "", label: "All Categories" },
  { value: "pipeline", label: "Pipeline" },
  { value: "scout", label: "Scouts" },
  { value: "analyst", label: "Analyst" },
  { value: "engine", label: "Engine" },
  { value: "model", label: "Model Gen" },
  { value: "circuit_breaker", label: "Circuit Breakers" },
  { value: "kill_condition", label: "Kill Conditions" },
  { value: "error", label: "Errors" },
];

const LEVELS = [
  { value: "", label: "All Levels" },
  { value: "info", label: "Info" },
  { value: "warn", label: "Warnings" },
  { value: "error", label: "Errors" },
];

const CATEGORY_ICONS: Record<string, string> = {
  pipeline: "⚡",
  scout: "🔍",
  analyst: "📊",
  engine: "⚙️",
  model: "🧮",
  circuit_breaker: "🛑",
  kill_condition: "💀",
  error: "❌",
};

const LEVEL_COLORS: Record<string, string> = {
  info: "text-[var(--muted)]",
  warn: "text-amber-400",
  error: "text-red-400",
};

const LEVEL_BG: Record<string, string> = {
  info: "bg-[var(--border)]",
  warn: "bg-amber-400/10 border-amber-400/20",
  error: "bg-red-400/10 border-red-400/20",
};

// ─── Helpers ───

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatTimeFull(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

// ─── Components ───

function LogEntryCard({ entry, isExpanded, onToggle }: { entry: LogEntry; isExpanded: boolean; onToggle: () => void }) {
  const hasMeta = entry.metadata && Object.keys(entry.metadata).length > 0;
  const hasMessage = entry.message && entry.message.length > 0;
  const isExpandable = hasMeta || (hasMessage && hasMessage);

  return (
    <div
      className={`border rounded-lg p-3 mb-1.5 transition-colors ${LEVEL_BG[entry.level]} ${
        isExpandable ? "cursor-pointer hover:bg-[var(--card)]" : ""
      }`}
      onClick={isExpandable ? onToggle : undefined}
    >
      {/* Header row */}
      <div className="flex items-start gap-3">
        {/* Icon */}
        <span className="text-base mt-0.5 select-none">
          {CATEGORY_ICONS[entry.category] || "📋"}
        </span>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Title */}
            <span className={`font-medium text-sm ${LEVEL_COLORS[entry.level]}`}>
              {entry.title}
            </span>

            {/* Ticker badge */}
            {entry.ticker && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--accent-muted)]/20 text-[var(--accent)]">
                {entry.ticker}
              </span>
            )}

            {/* Category badge */}
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--muted)]">
              {entry.category}
            </span>

            {/* Duration */}
            {entry.duration_ms !== null && (
              <span className="text-[10px] font-mono text-[var(--faint)]">
                {formatDuration(entry.duration_ms)}
              </span>
            )}
          </div>

          {/* Message preview (single line when collapsed) */}
          {hasMessage && !isExpanded && (
            <p className="text-xs text-[var(--muted)] mt-1 truncate">{entry.message}</p>
          )}
        </div>

        {/* Time + source */}
        <div className="text-right shrink-0">
          <div className="text-[10px] text-[var(--faint)]" title={formatTimeFull(entry.created_at)}>
            {formatTime(entry.created_at)}
          </div>
          <div className="text-[10px] font-mono text-[var(--faint)] mt-0.5">{entry.source}</div>
        </div>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="mt-3 ml-8 space-y-2">
          {/* Full message */}
          {hasMessage && (
            <div className="text-xs text-[var(--secondary)] bg-[var(--bg)] rounded p-2 whitespace-pre-wrap">
              {entry.message}
            </div>
          )}

          {/* Metadata */}
          {hasMeta && (
            <div className="text-xs font-mono bg-[var(--bg)] rounded p-2 overflow-x-auto">
              <div className="text-[10px] text-[var(--faint)] mb-1 uppercase tracking-wider">Metadata</div>
              {Object.entries(entry.metadata).map(([key, value]) => (
                <div key={key} className="flex gap-2 py-0.5">
                  <span className="text-[var(--muted)] shrink-0">{key}:</span>
                  <span className="text-[var(--secondary)]">
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Full timestamp + run ID */}
          <div className="flex gap-4 text-[10px] text-[var(--faint)]">
            <span>{formatTimeFull(entry.created_at)}</span>
            {entry.run_id && <span>Run: {entry.run_id}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Dashboard ───

export default function LogsDashboard() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [category, setCategory] = useState("");
  const [level, setLevel] = useState("");
  const [ticker, setTicker] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  // Expanded entries
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  // Stats
  const [stats, setStats] = useState({ info: 0, warn: 0, error: 0 });

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (level) params.set("level", level);
      if (ticker) params.set("ticker", ticker.toUpperCase());
      params.set("limit", String(limit));
      params.set("offset", String(offset));

      const res = await fetch(`/api/logs?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: LogsResponse = await res.json();
      setLogs(data.logs);
      setTotal(data.total);

      // Count levels for stats bar
      const s = { info: 0, warn: 0, error: 0 };
      for (const l of data.logs) {
        if (l.level in s) s[l.level as keyof typeof s]++;
      }
      setStats(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load logs");
    }
    setLoading(false);
  }, [category, level, ticker, offset]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Auto-refresh every 15s
  useEffect(() => {
    const interval = setInterval(fetchLogs, 15000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  const toggleExpanded = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--fg)]">
      {/* Header */}
      <header className="border-b border-[var(--border)] bg-[var(--bg-elevated)]">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-[var(--muted)] hover:text-[var(--fg)] text-sm">
              ← Dashboard
            </Link>
            <h1 className="text-lg font-semibold">Activity Log</h1>
            <span className="text-xs text-[var(--muted)]">{total} entries</span>
          </div>

          {/* Quick stats */}
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="text-[var(--muted)]">{stats.info} info</span>
            <span className="text-amber-400">{stats.warn} warn</span>
            <span className="text-red-400">{stats.error} error</span>
            <button
              onClick={fetchLogs}
              className="ml-2 px-2 py-1 rounded border border-[var(--border)] hover:bg-[var(--card)] text-[var(--muted)]"
            >
              ↻ Refresh
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-4">
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <select
            value={category}
            onChange={(e) => { setCategory(e.target.value); setOffset(0); }}
            className="text-sm bg-[var(--bg-elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-[var(--fg)]"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>

          <select
            value={level}
            onChange={(e) => { setLevel(e.target.value); setOffset(0); }}
            className="text-sm bg-[var(--bg-elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-[var(--fg)]"
          >
            {LEVELS.map((l) => (
              <option key={l.value} value={l.value}>{l.label}</option>
            ))}
          </select>

          <input
            type="text"
            value={ticker}
            onChange={(e) => { setTicker(e.target.value); setOffset(0); }}
            placeholder="Filter by ticker..."
            className="text-sm bg-[var(--bg-elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-[var(--fg)] placeholder-[var(--muted)] w-36"
          />

          {(category || level || ticker) && (
            <button
              onClick={() => { setCategory(""); setLevel(""); setTicker(""); setOffset(0); }}
              className="text-xs text-[var(--muted)] hover:text-[var(--fg)] underline"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Content */}
        {loading && logs.length === 0 ? (
          <div className="text-center text-[var(--muted)] py-16">Loading activity log...</div>
        ) : error ? (
          <div className="text-center py-16">
            <div className="text-red-400 mb-2">Failed to load logs</div>
            <div className="text-xs text-[var(--muted)]">{error}</div>
            <div className="text-xs text-[var(--muted)] mt-4">
              If the activity_log table doesn&apos;t exist yet, run the SQL migration:
              <code className="block mt-1 bg-[var(--bg-elevated)] rounded p-2 font-mono">
                supabase/activity_log.sql
              </code>
            </div>
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center text-[var(--muted)] py-16">
            <div className="text-4xl mb-4">📋</div>
            <div className="text-lg mb-2">No activity logs yet</div>
            <div className="text-sm">
              Logs will appear here after the next pipeline run.
              <br />
              Make sure the <code className="font-mono bg-[var(--bg-elevated)] px-1 rounded">activity_log</code> table
              has been created in Supabase.
            </div>
          </div>
        ) : (
          <>
            {/* Log entries */}
            <div className="space-y-0">
              {logs.map((entry) => (
                <LogEntryCard
                  key={entry.id}
                  entry={entry}
                  isExpanded={expandedIds.has(entry.id)}
                  onToggle={() => toggleExpanded(entry.id)}
                />
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6 text-sm">
                <button
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={offset === 0}
                  className="px-3 py-1.5 rounded border border-[var(--border)] hover:bg-[var(--card)] disabled:opacity-30 disabled:cursor-not-allowed text-[var(--muted)]"
                >
                  ← Previous
                </button>
                <span className="text-[var(--muted)] text-xs">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => setOffset(offset + limit)}
                  disabled={offset + limit >= total}
                  className="px-3 py-1.5 rounded border border-[var(--border)] hover:bg-[var(--card)] disabled:opacity-30 disabled:cursor-not-allowed text-[var(--muted)]"
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
