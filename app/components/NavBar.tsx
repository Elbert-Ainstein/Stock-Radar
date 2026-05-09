"use client";

/**
 * NavBar — shared application chrome.
 *
 * Drop-in component used by ALL pages (Watchlist, Discovery, Models, Ask, Logs).
 * Manages its own state:
 *   - theme toggle (reads/writes localStorage `sr-theme`, sets data-theme on <html>)
 *   - pipeline status polling (every 3s from /api/pipeline) so Run Pipeline /
 *     Stop / Free only / Rebuild buttons reflect server state regardless of
 *     which page initiated the run
 *   - watchlist tickers (lazy-fetched from /api/stocks for Run-All-Theses)
 *
 * Page-specific state (selected ticker, sort, filter, bulk select) stays on
 * each page. NavBar only owns the nav-level chrome.
 *
 * Solves the bug where each page had its own custom header, so theme/run/last-scan
 * controls vanished when switching between Watchlist and Discovery.
 */
import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface PipelineStatus {
  running: boolean;
  progress?: { stage: string; message: string; percent: number } | null;
  lastRunAt?: string | null;
  scoutsActive?: number;
  scoutsTotal?: number;
}

const NAV_ITEMS: Array<{ href: string; label: string }> = [
  { href: "/", label: "Watchlist" },
  { href: "/discovery", label: "Discovery" },
  { href: "/model", label: "Models" },
  { href: "/ask", label: "Ask AI" },
  { href: "/logs", label: "Logs" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname === "/dashboard";
  return pathname === href || pathname.startsWith(href + "/");
}

function timeAgo(iso?: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return "just now";
  const m = Math.floor(ms / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export default function NavBar() {
  const pathname = usePathname();

  // ── Theme ──
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    const t = (typeof window !== "undefined" && localStorage.getItem("sr-theme")) || "dark";
    setTheme(t === "light" ? "light" : "dark");
  }, []);
  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      localStorage.setItem("sr-theme", next);
      if (next === "light") document.documentElement.setAttribute("data-theme", "light");
      else document.documentElement.removeAttribute("data-theme");
      return next;
    });
  }, []);

  // ── Pipeline status (polled every 3s) ──
  const [pipeline, setPipeline] = useState<PipelineStatus>({ running: false });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/pipeline", { cache: "no-store" });
      if (!res.ok) return;
      const j = await res.json();
      setPipeline({
        running: !!j.running,
        progress: j.progress || null,
        lastRunAt: j.lastRunAt || j.last_run_at || null,
        scoutsActive: j.scoutsActive ?? j.scouts_active,
        scoutsTotal: j.scoutsTotal ?? j.scouts_total,
      });
    } catch { /* swallow — non-fatal */ }
  }, []);

  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchStatus]);

  // ── Pipeline actions ──
  const [pipBusy, setPipBusy] = useState(false);
  const runPipeline = async (freeOnly = false) => {
    if (pipeline.running || pipBusy) return;
    setPipBusy(true);
    try {
      await fetch("/api/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ freeOnly }),
      });
      await fetchStatus();
    } finally { setPipBusy(false); }
  };
  const stopPipeline = async () => {
    if (!pipeline.running) return;
    setPipBusy(true);
    try {
      await fetch("/api/pipeline", { method: "DELETE" });
      await fetchStatus();
    } finally { setPipBusy(false); }
  };
  const rebuild = async () => {
    if (pipBusy) return;
    setPipBusy(true);
    try {
      await fetch("/api/rebuild", { method: "POST" });
      await fetchStatus();
    } finally { setPipBusy(false); }
  };

  // ── Run All Theses (fetch watchlist on demand) ──
  const [thesesBusy, setThesesBusy] = useState(false);
  const [thesesQueued, setThesesQueued] = useState(0);
  const runAllTheses = async () => {
    if (thesesBusy) return;
    setThesesBusy(true);
    setThesesQueued(0);
    try {
      // Get watchlist tickers
      const stocksRes = await fetch("/api/stocks", { cache: "no-store" });
      const stocksJson = await stocksRes.json();
      const tickers: string[] = (stocksJson.stocks || stocksJson.data || []).map((s: any) => s.ticker).filter(Boolean);
      // Queue thesis runs in parallel (each is fire-and-forget; the script handles its own throttling)
      const results = await Promise.allSettled(
        tickers.map((t) =>
          fetch(`/api/thesis/${encodeURIComponent(t)}/rerun`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ trigger_reason: "manual_bulk" }),
          })
        )
      );
      setThesesQueued(results.filter((r) => r.status === "fulfilled").length);
      setTimeout(() => setThesesQueued(0), 8000);
    } finally { setThesesBusy(false); }
  };

  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 50,
      background: "var(--sr-paper, #fcfcfa)",
      borderBottom: "1px solid var(--sr-rule-strong, #b8ae8e)",
    }}>
      <div style={{
        maxWidth: 1400, margin: "0 auto",
        display: "flex", alignItems: "center", gap: 14,
        padding: "10px 18px",
      }}>
        {/* Brand */}
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
          <span aria-hidden style={{
            width: 24, height: 24, borderRadius: 4,
            background: "var(--sr-action, #14120f)",
            color: "var(--sr-action-ink, #fcfcfa)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            fontSize: 11, fontWeight: 700, letterSpacing: "0.05em",
            fontFamily: "var(--sr-font-mono, ui-monospace, monospace)",
          }}>SR</span>
          <span style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--sr-ink, #14120f)", letterSpacing: "-0.01em" }}>
              Stock Radar
            </span>
            <span style={{ fontSize: 9.5, color: "var(--sr-ink-3, #847e6f)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              Multi-AI Agent System
            </span>
          </span>
        </Link>

        {/* Nav */}
        <nav style={{ display: "flex", gap: 2, marginLeft: 14 }} aria-label="Primary">
          {NAV_ITEMS.map(({ href, label }) => {
            const active = isActive(pathname, href);
            return (
              <Link key={href} href={href} style={{
                padding: "6px 10px",
                borderRadius: 4,
                fontSize: 12.5,
                color: active ? "var(--sr-ink, #14120f)" : "var(--sr-ink-2, #5a544a)",
                fontWeight: active ? 600 : 500,
                background: active ? "var(--sr-paper-2, #ece8d8)" : "transparent",
                textDecoration: "none",
                transition: "background 100ms",
              }}>
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Right cluster: status + actions + theme */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {/* Pipeline status indicator */}
          {pipeline.running ? (
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "4px 8px",
              fontSize: 10.5, color: "var(--sr-info-ink, #2c5e8c)",
              background: "var(--sr-info-bg, #dde6ef)",
              border: "1px solid var(--sr-info-ink, #2c5e8c)",
              borderRadius: 3,
              fontFamily: "var(--sr-font-mono, monospace)",
            }} title={pipeline.progress?.message || "Pipeline running"}>
              <span aria-hidden style={{ fontSize: 8 }}>●</span>
              {pipeline.progress?.percent != null
                ? `Pipeline ${Math.round(pipeline.progress.percent)}%`
                : "Pipeline running"}
            </span>
          ) : (
            <span style={{ fontSize: 11, color: "var(--sr-ink-3, #847e6f)", fontFamily: "var(--sr-font-mono, monospace)" }}>
              Last scan: {timeAgo(pipeline.lastRunAt)}
            </span>
          )}

          {/* Run / Stop pipeline */}
          {pipeline.running ? (
            <button onClick={stopPipeline} disabled={pipBusy} style={btnDanger(pipBusy)}>
              <span aria-hidden style={{ marginRight: 4 }}>■</span>Stop
            </button>
          ) : (
            <button onClick={() => runPipeline(false)} disabled={pipBusy} style={btnPrimary(pipBusy)}>
              Run Pipeline
            </button>
          )}
          <button onClick={() => runPipeline(true)} disabled={pipBusy || pipeline.running} style={btnGhost(pipBusy || pipeline.running)} title="Run only free scouts">
            Free only
          </button>
          <button onClick={rebuild} disabled={pipBusy} style={btnGhost(pipBusy)} title="Rebuild analysis from existing scout signals (no new scouts)">
            Rebuild
          </button>

          {/* Run All Theses */}
          <button onClick={runAllTheses} disabled={thesesBusy} style={btnAccent(thesesBusy)} title="Queue thesis runs for every ticker on the watchlist (~$3-5 each)">
            {thesesQueued > 0
              ? <><span aria-hidden style={{ marginRight: 4 }}>✓</span>Queued {thesesQueued}</>
              : thesesBusy
                ? "Queuing…"
                : <><span aria-hidden style={{ marginRight: 4 }}>⚡</span>Run All Theses</>}
          </button>

          {/* Theme toggle */}
          <button onClick={toggleTheme} style={btnIcon} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} aria-label="Toggle theme">
            {theme === "dark" ? "☾" : "☀"}
          </button>
        </div>
      </div>
    </header>
  );
}

const btnBase: React.CSSProperties = {
  display: "inline-flex", alignItems: "center",
  height: 28, padding: "0 11px",
  fontSize: 11.5, fontWeight: 500,
  borderRadius: 4,
  fontFamily: "inherit",
  cursor: "pointer",
};

function btnPrimary(disabled: boolean): React.CSSProperties {
  return {
    ...btnBase,
    background: "var(--sr-action, #14120f)",
    color: "var(--sr-action-ink, #fcfcfa)",
    border: "1px solid var(--sr-action, #14120f)",
    opacity: disabled ? 0.5 : 1,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

function btnGhost(disabled: boolean): React.CSSProperties {
  return {
    ...btnBase,
    background: "var(--sr-paper-1, #f6f4ec)",
    color: "var(--sr-ink-2, #5a544a)",
    border: "1px solid var(--sr-rule, #d6cfb6)",
    opacity: disabled ? 0.5 : 1,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

function btnDanger(disabled: boolean): React.CSSProperties {
  return {
    ...btnBase,
    background: "var(--sr-err-bg, #f1d3cd)",
    color: "var(--sr-err-ink, #7a1f15)",
    border: "1px solid var(--sr-err-ink, #7a1f15)",
    opacity: disabled ? 0.5 : 1,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

function btnAccent(disabled: boolean): React.CSSProperties {
  return {
    ...btnBase,
    background: disabled ? "var(--sr-paper-2, #ece8d8)" : "var(--sr-conv-strong, #0f6b3e)",
    color: disabled ? "var(--sr-ink-3, #847e6f)" : "var(--sr-action-ink, #fcfcfa)",
    border: `1px solid ${disabled ? "var(--sr-rule, #d6cfb6)" : "var(--sr-conv-strong, #0f6b3e)"}`,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

const btnIcon: React.CSSProperties = {
  ...btnBase,
  width: 28, padding: 0,
  background: "var(--sr-paper-1, #f6f4ec)",
  border: "1px solid var(--sr-rule, #d6cfb6)",
  color: "var(--sr-ink-2, #5a544a)",
  fontSize: 14,
  justifyContent: "center",
};
