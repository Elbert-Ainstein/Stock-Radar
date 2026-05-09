"use client";

/**
 * WatchlistRefreshPanel — Module 12 watchlist refresh surface.
 *
 * Inline horizontal strip per design choice ConvergenceRefreshA from
 * docs/wireframes/v3-stock-radar-tier1/.../hifi/sr-convergence.jsx
 *
 * Shows tickers ALREADY on the watchlist with fresh cross-source signal
 * in the last 30 days. Different semantic from Discovery: these are
 * tracked names with NEW evidence, surfaced as scrollable cards above
 * the watchlist table.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import type { ConvergenceRow } from "../api/convergence/route";

interface ApiResponse {
  rows: ConvergenceRow[];
  total_matched: number;
  error?: string;
}

const CLASS_META: Record<string, { ink: string; bg: string; short: string }> = {
  smart_money: { ink: "var(--sr-conv-strong, #0f6b3e)", bg: "var(--sr-conv-strong-bg, #d8eadd)", short: "13F" },
  insider:     { ink: "var(--sr-info-ink, #2c5e8c)",    bg: "var(--sr-info-bg, #dde6ef)",        short: "INSIDER" },
  news:        { ink: "var(--sr-conv-watch, #8a6914)",  bg: "var(--sr-conv-watch-bg, #f0e4c2)",  short: "NEWS" },
  theme:       { ink: "var(--sr-link, #2c5e8c)",        bg: "var(--sr-paper-2, #ece8d8)",        short: "THEME" },
  momentum:    { ink: "var(--sr-ink-3, #847e6f)",       bg: "var(--sr-paper-2, #ece8d8)",        short: "MOMENTUM" },
  manual:      { ink: "var(--sr-ink-2, #5a544a)",       bg: "var(--sr-paper-2, #ece8d8)",        short: "MANUAL" },
};

function classMeta(cls: string) {
  if (CLASS_META[cls]) return CLASS_META[cls];
  if (cls.startsWith("other:"))
    return { ink: "var(--sr-err-ink, #7a1f15)", bg: "var(--sr-err-bg, #f1d3cd)", short: "OTHER" };
  return CLASS_META.manual;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return "just now";
  const m = Math.floor(ms / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function diffText(row: ConvergenceRow): string {
  const parts: string[] = [];
  const has = (cls: string) => row.classes.includes(cls);
  if (has("smart_money")) {
    const mgrs = row.sources.filter((s) => s.startsWith("13f_")).length;
    parts.push(mgrs > 1 ? `+${mgrs} 13F managers` : "+1 new 13F manager");
  }
  if (has("insider")) parts.push("insider Form-4 activity");
  if (has("news")) {
    if (row.sources.some((s) => s === "news_earnings_beat")) parts.push("earnings beat in news");
    else parts.push("bullish news");
  }
  if (has("theme")) parts.push("theme scan re-flagged");
  if (has("momentum") && parts.length === 0) parts.push("yahoo screener");
  return parts.join(" · ") || "fresh signal";
}

const ghostBtn: React.CSSProperties = {
  display: "inline-flex", alignItems: "center",
  height: 24, padding: "0 9px",
  background: "var(--sr-paper-1, #f6f4ec)",
  border: "1px solid var(--sr-rule, #d6cfb6)",
  borderRadius: 4, cursor: "pointer",
  fontSize: 10.5, color: "var(--sr-ink-1, #34302a)",
  fontFamily: "inherit", textDecoration: "none",
};

const primaryBtn: React.CSSProperties = {
  display: "inline-flex", alignItems: "center",
  height: 24, padding: "0 11px",
  background: "var(--sr-action, #14120f)",
  color: "var(--sr-action-ink, #fcfcfa)",
  border: "none", borderRadius: 4, cursor: "pointer",
  fontWeight: 500, fontSize: 11, fontFamily: "inherit", textDecoration: "none",
};

interface WatchlistRefreshPanelProps {
  /** Top N rows (cards in the strip). Default 8. */
  top?: number;
  /** Minimum class count to show. Default 2 — single-class watchlist names are noise here. */
  minClasses?: number;
}

export default function WatchlistRefreshPanel({
  top = 8,
  minClasses = 2,
}: WatchlistRefreshPanelProps) {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/convergence?status=watchlisted&top=${top * 2}`, { cache: "no-store" });
      const j = await res.json();
      if (!res.ok || j.error) setError(j.error || `HTTP ${res.status}`);
      else setData(j);
    } catch (e: any) {
      setError(e.message || "fetch failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [top]); // eslint-disable-line react-hooks/exhaustive-deps

  // Only show watchlist names with cross-source signal beyond the manual seed.
  // A name with class_count=1 (just `manual`) isn't fresh signal — it's just
  // the watchlist seed. We require at least minClasses (default 2) to surface here.
  const filtered = data
    ? data.rows.filter((r) => r.class_count >= minClasses).slice(0, top)
    : [];

  if (error) {
    return (
      <section style={{
        background: "var(--sr-err-bg, #f1d3cd)",
        borderBottom: "1px solid var(--sr-rule, #d6cfb6)",
        padding: "10px 16px", fontSize: 12,
        color: "var(--sr-err-ink, #7a1f15)",
        fontFamily: "var(--font-mono, monospace)",
      }}>
        [watchlist-refresh error] {error}
        <button onClick={load} style={{ ...ghostBtn, marginLeft: 12, height: 20 }}>Retry</button>
      </section>
    );
  }

  if (!loading && data && filtered.length === 0) {
    return (
      <section style={{
        background: "var(--sr-paper-1, #f6f4ec)",
        border: "1px solid var(--sr-rule-soft, #e6dfc8)",
        borderRadius: 6, marginBottom: 16,
        padding: "14px 16px",
        display: "flex", alignItems: "center", gap: 10,
        color: "var(--sr-ink-2, #5a544a)",
        fontStyle: "italic", fontSize: 12.5,
      }}>
        <span aria-hidden style={{ fontSize: 14 }}>🔔</span>
        Watchlist quiet — no fresh cross-source signal in the last 30 days.
      </section>
    );
  }

  return (
    <section style={{
      background: "var(--sr-paper-1, #f6f4ec)",
      border: "1px solid var(--sr-rule, #d6cfb6)",
      borderRadius: 6, marginBottom: 16,
      padding: "12px 16px 14px 16px",
    }}>
      <header style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <span style={{
            fontSize: 9.5, color: "var(--sr-ink-3, #847e6f)",
            textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 500,
          }}>Fresh signal · last 30d</span>
          <span style={{
            fontSize: 11, color: "var(--sr-ink-3, #847e6f)",
            fontFamily: "var(--font-mono, monospace)",
          }}>{filtered.length} on watchlist</span>
        </div>
        <button onClick={load} disabled={loading} style={{ ...ghostBtn, opacity: loading ? 0.5 : 1, cursor: loading ? "not-allowed" : "pointer" }}>
          {loading ? "refreshing…" : "refresh"}
        </button>
      </header>

      <div style={{
        display: "flex", gap: 8,
        overflowX: "auto",
        scrollSnapType: "x mandatory",
        paddingBottom: 4,
        WebkitOverflowScrolling: "touch",
      }}>
        {filtered.map((r) => (
          <article key={r.ticker} className="sr-refresh-card" style={{
            flex: "0 0 auto",
            width: 280,
            scrollSnapAlign: "start",
            background: "var(--sr-paper, #fcfcfa)",
            border: "1px solid var(--sr-rule, #d6cfb6)",
            borderRadius: 6,
            padding: 10,
            display: "flex", flexDirection: "column", gap: 6,
          }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
              <Link href={`/stock/${encodeURIComponent(r.ticker)}`} style={{
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 14, fontWeight: 600,
                color: "var(--sr-ink, #14120f)",
                textDecoration: "none",
              }}>{r.ticker}</Link>
              <span style={{
                fontSize: 10, color: "var(--sr-ink-3, #847e6f)",
                fontFamily: "var(--font-mono, monospace)",
              }}>{timeAgo(r.last_scanned)}</span>
            </div>
            <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
              {r.classes.filter((c) => c !== "manual").map((cls) => {
                const m = classMeta(cls);
                return (
                  <span key={cls} style={{
                    display: "inline-flex", alignItems: "center",
                    height: 16, padding: "0 5px",
                    fontSize: 9, fontWeight: 600, letterSpacing: "0.06em",
                    color: m.ink, background: m.bg, borderRadius: 2,
                    fontFamily: "var(--font-mono, monospace)",
                  }}>{m.short}</span>
                );
              })}
            </div>
            <p style={{
              fontSize: 11.5, color: "var(--sr-ink-1, #34302a)",
              lineHeight: 1.4, margin: 0,
            }}>{diffText(r)}</p>
            <div style={{ display: "flex", gap: 4, marginTop: 2 }}>
              <Link href={`/stock/${encodeURIComponent(r.ticker)}`} style={primaryBtn}>Open</Link>
            </div>
          </article>
        ))}
        {loading && filtered.length === 0 && Array.from({ length: 4 }).map((_, i) => (
          <div key={i} style={{
            flex: "0 0 auto", width: 280,
            background: "var(--sr-paper-2, #ece8d8)",
            border: "1px solid var(--sr-rule-soft, #e6dfc8)",
            borderRadius: 6, height: 110,
          }} />
        ))}
      </div>
    </section>
  );
}
