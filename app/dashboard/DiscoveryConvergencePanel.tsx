"use client";

/**
 * DiscoveryConvergencePanel — Module 12 discovery surface.
 *
 * Card-per-candidate layout per design choice DiscoveryB from
 * docs/wireframes/v3-stock-radar-tier1/.../hifi/sr-convergence.jsx
 *
 * Design rules (locked by Hume's design pass):
 * - STRONG = LOUD: white paper bg + 3px conv-strong left border + tier badge fill
 * - Class chips: ALWAYS-ON, wrap when needed
 * - Queue thesis: ONE-CLICK + toast for STRONG/MEDIUM (asymmetric — punishing
 *   the well-aimed click is wrong), TWO-CLICK with cost callout for SINGLE
 * - Responsive: 2-col desktop, 1-col tablet/phone
 * - Token system: --sr-* (all colors with fallbacks)
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import type { ConvergenceRow } from "../api/convergence/route";

interface ApiResponse {
  run_at: string;
  row_count: number;
  total_matched: number;
  tier_counts: { STRONG: number; MEDIUM: number; SINGLE: number };
  rows: ConvergenceRow[];
  error?: string;
}

const CLASS_META: Record<string, { ink: string; bg: string; short: string; label: string }> = {
  smart_money: { ink: "var(--sr-conv-strong, #0f6b3e)", bg: "var(--sr-conv-strong-bg, #d8eadd)", short: "13F", label: "Smart money" },
  insider:     { ink: "var(--sr-info-ink, #2c5e8c)",    bg: "var(--sr-info-bg, #dde6ef)",        short: "INSIDER", label: "Insider" },
  news:        { ink: "var(--sr-conv-watch, #8a6914)",  bg: "var(--sr-conv-watch-bg, #f0e4c2)",  short: "NEWS", label: "News" },
  theme:       { ink: "var(--sr-link, #2c5e8c)",        bg: "var(--sr-paper-2, #ece8d8)",        short: "THEME", label: "Theme" },
  momentum:    { ink: "var(--sr-ink-3, #847e6f)",       bg: "var(--sr-paper-2, #ece8d8)",        short: "MOMENTUM", label: "Momentum" },
  manual:      { ink: "var(--sr-ink-2, #5a544a)",       bg: "var(--sr-paper-2, #ece8d8)",        short: "MANUAL", label: "Manual" },
};

function classMeta(cls: string) {
  if (CLASS_META[cls]) return CLASS_META[cls];
  if (cls.startsWith("other:"))
    return { ink: "var(--sr-err-ink, #7a1f15)", bg: "var(--sr-err-bg, #f1d3cd)", short: "OTHER", label: cls };
  return CLASS_META.manual;
}

const TIER_META = {
  STRONG: { ink: "var(--sr-conv-strong, #0f6b3e)", bg: "var(--sr-conv-strong-bg, #d8eadd)", label: "STRONG" },
  MEDIUM: { ink: "var(--sr-conv-watch, #8a6914)",  bg: "var(--sr-conv-watch-bg, #f0e4c2)",  label: "MEDIUM" },
  SINGLE: { ink: "var(--sr-ink-3, #847e6f)",       bg: "var(--sr-paper-2, #ece8d8)",        label: "SINGLE" },
  EMPTY:  { ink: "var(--sr-ink-4, #a39b87)",       bg: "var(--sr-paper-1, #f6f4ec)",        label: "—" },
};

/**
 * Synthesize a "why" reason for each class from the source tags.
 * Until upstream feeders enrich rows with explanatory text, we infer it
 * from the tag pattern (e.g. "13f_druckenmiller_2025Q4_new_position" →
 * "Druckenmiller new position Q4").
 */
function whyForClass(cls: string, sources: string[]): string {
  const matching = sources.filter((s) => {
    const t = s.toLowerCase();
    if (cls === "smart_money") return t.startsWith("13f_");
    if (cls === "insider") return t.startsWith("insider_");
    if (cls === "news") return t.startsWith("news_");
    if (cls === "theme") return t.startsWith("theme_");
    if (cls === "momentum") return t.startsWith("yahoo_");
    if (cls === "manual") return t === "watchlist_seed";
    return false;
  });
  if (matching.length === 0) return "—";
  if (cls === "smart_money") {
    const managers = matching
      .map((s) => {
        const parts = s.split("_");
        const mgr = parts[1];
        const qtr = parts.slice(2, 4).join(" ");
        return `${mgr} (${qtr})`;
      })
      .join(", ");
    return managers;
  }
  if (cls === "insider") {
    return matching.length > 1
      ? `Recent Form-4 activity (${matching.length} windows)`
      : "Recent Form-4 activity in the last 30 days";
  }
  if (cls === "news") {
    if (matching.includes("news_earnings_beat")) return "Bullish news incl. earnings beat";
    return "Bullish news flow in the last 30 days";
  }
  if (cls === "momentum") {
    return `Yahoo screener: ${matching.map((s) => s.replace("yahoo_", "")).join(", ")}`;
  }
  if (cls === "theme") return matching.map((s) => s.replace("theme_", "")).join(", ");
  if (cls === "manual") return "Hand-added to watchlist";
  return matching.join(", ");
}

interface QueueButtonProps {
  ticker: string;
  pattern: "one-click" | "two-click";
}

function QueueThesisButton({ ticker, pattern }: QueueButtonProps) {
  const [phase, setPhase] = useState<"idle" | "confirming" | "queued">("idle");

  if (phase === "confirming") {
    return (
      <div
        style={{
          display: "inline-flex",
          alignItems: "stretch",
          border: "1px solid var(--sr-ink, #14120f)",
          borderRadius: 4,
          background: "var(--sr-paper, #fcfcfa)",
          boxShadow: "0 1px 0 rgba(20,18,15,0.04), 0 4px 12px rgba(20,18,15,0.08)",
        }}
      >
        <span
          style={{
            padding: "0 10px",
            display: "inline-flex",
            alignItems: "center",
            fontSize: 11,
            color: "var(--sr-ink-2, #5a544a)",
            borderRight: "1px solid var(--sr-rule, #d6cfb6)",
          }}
        >
          ~$3–5 · Opus run
        </span>
        <button
          onClick={() => setPhase("queued")}
          style={{
            ...primaryBtnBase,
            height: 26,
            fontSize: 11,
            borderRadius: 0,
            border: "none",
          }}
        >
          Confirm queue
        </button>
        <button
          onClick={() => setPhase("idle")}
          style={{
            height: 26,
            padding: "0 10px",
            background: "transparent",
            border: "none",
            fontSize: 11,
            color: "var(--sr-ink-3, #847e6f)",
            cursor: "pointer",
          }}
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setPhase(pattern === "two-click" ? "confirming" : "queued")}
      title={`Queue thesis run for ${ticker} (~$3-5 Opus)`}
      style={{
        ...primaryBtnBase,
        height: 26,
        fontSize: 11,
        background: phase === "queued" ? "var(--sr-conv-strong, #0f6b3e)" : "var(--sr-action, #14120f)",
      }}
    >
      <span aria-hidden style={{ fontSize: 10, marginRight: 4 }}>⚡</span>
      {phase === "queued" ? "Queued" : "Queue thesis run"}
    </button>
  );
}

const primaryBtnBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "0 11px",
  background: "var(--sr-action, #14120f)",
  color: "var(--sr-action-ink, #fcfcfa)",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontWeight: 500,
  fontFamily: "inherit",
};

const ghostBtnBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  height: 26,
  padding: "0 9px",
  background: "var(--sr-paper-1, #f6f4ec)",
  border: "1px solid var(--sr-rule, #d6cfb6)",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 11,
  color: "var(--sr-ink-1, #34302a)",
  fontFamily: "inherit",
};

interface DiscoveryConvergencePanelProps {
  statuses?: string;
  top?: number;
}

export default function DiscoveryConvergencePanel({
  statuses = "exploring,promising,qualified",
  top = 25,
}: DiscoveryConvergencePanelProps) {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/convergence?status=${encodeURIComponent(statuses)}&top=${top}`,
        { cache: "no-store" }
      );
      const j = (await res.json()) as ApiResponse;
      if (!res.ok || j.error) setError(j.error || `HTTP ${res.status}`);
      else setData(j);
    } catch (e: any) {
      setError(e.message || "fetch failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [statuses, top]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="sr-discovery-convergence" style={{
      background: "var(--sr-paper, #fcfcfa)",
      border: "1px solid var(--sr-rule, #d6cfb6)",
      borderRadius: 6,
      marginBottom: 16,
      overflow: "hidden",
    }}>
      <header style={chromeStyle}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--sr-ink, #14120f)", margin: 0, letterSpacing: "-0.01em" }}>
            Tier 1 cross-source convergence
          </h2>
          <p style={{ fontSize: 11, color: "var(--sr-ink-3, #847e6f)", margin: "2px 0 0 0", fontFamily: "var(--font-mono, ui-monospace, monospace)" }}>
            {data ? `${data.row_count} candidates · ${data.tier_counts.STRONG} STRONG · ${data.tier_counts.MEDIUM} MEDIUM · ${data.tier_counts.SINGLE} SINGLE` : "loading…"}
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{ ...ghostBtnBase, opacity: loading ? 0.5 : 1, cursor: loading ? "not-allowed" : "pointer" }}>
          {loading ? "refreshing…" : "refresh"}
        </button>
      </header>

      {/* Class legend strip */}
      <div style={legendStripStyle}>
        <span style={{ fontSize: 9.5, color: "var(--sr-ink-3, #847e6f)", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 500, marginRight: 8 }}>
          signal classes
        </span>
        {(["smart_money", "insider", "news", "theme", "momentum"] as const).map((k) => {
          const m = classMeta(k);
          return (
            <span key={k} style={{
              display: "inline-flex", alignItems: "center", height: 16, padding: "0 5px",
              fontSize: 9, fontWeight: 600, letterSpacing: "0.06em",
              color: m.ink, background: m.bg, borderRadius: 2,
              fontFamily: "var(--font-mono, monospace)",
            }}>{m.short}</span>
          );
        })}
      </div>

      {error && (
        <div style={{
          padding: "12px 16px", fontSize: 12, color: "var(--sr-err-ink, #7a1f15)",
          background: "var(--sr-err-bg, #f1d3cd)",
          fontFamily: "var(--font-mono, monospace)",
        }}>
          [error] {error}
          <button onClick={load} style={{ ...ghostBtnBase, marginLeft: 12, height: 22, fontSize: 10 }}>Retry</button>
        </div>
      )}

      {!error && loading && !data && <SkeletonCards />}

      {!error && data && data.rows.length === 0 && (
        <div style={{
          padding: "32px 22px", textAlign: "center",
          color: "var(--sr-ink-2, #5a544a)", fontSize: 13, fontStyle: "italic",
          background: "var(--sr-paper-1, #f6f4ec)",
        }}>
          No candidates yet — run the feeders to populate.
        </div>
      )}

      {!error && data && data.rows.length > 0 && (
        <div className="sr-card-grid" style={{
          padding: 16,
          display: "grid",
          gridTemplateColumns: "repeat(2, 1fr)",
          gap: 10,
        }}>
          {data.rows.map((r) => <CandidateCard key={r.ticker} row={r} />)}
        </div>
      )}

      {/* Responsive: 1-col on tablet & phone */}
      <style jsx>{`
        @media (max-width: 900px) {
          .sr-card-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </section>
  );
}

function CandidateCard({ row: r }: { row: ConvergenceRow }) {
  const tier = TIER_META[r.tier as keyof typeof TIER_META] || TIER_META.EMPTY;
  const isLoud = r.tier === "STRONG";
  const queuePattern: "one-click" | "two-click" =
    r.tier === "STRONG" || r.tier === "MEDIUM" ? "one-click" : "two-click";

  return (
    <article style={{
      background: isLoud ? "var(--sr-paper, #fcfcfa)" : "var(--sr-paper-1, #f6f4ec)",
      border: isLoud ? "1px solid var(--sr-conv-strong, #0f6b3e)" : "1px solid var(--sr-rule, #d6cfb6)",
      borderLeft: isLoud ? "3px solid var(--sr-conv-strong, #0f6b3e)" : "1px solid var(--sr-rule, #d6cfb6)",
      borderRadius: 6,
      padding: 14,
      display: "flex",
      flexDirection: "column",
      gap: 10,
    }}>
      <header style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <Link href={`/stock/${encodeURIComponent(r.ticker)}`} style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: 18, fontWeight: 600,
            color: "var(--sr-ink, #14120f)",
            textDecoration: "none",
          }}>{r.ticker}</Link>
          <span style={{
            display: "inline-flex", alignItems: "center", height: 18, padding: "0 6px",
            fontSize: 9.5, fontWeight: 600, letterSpacing: "0.08em",
            color: tier.ink, background: tier.bg,
            borderRadius: 3, fontFamily: "var(--font-mono, monospace)",
          }}>{tier.label}</span>
          <span style={{
            fontSize: 11, fontFamily: "var(--font-mono, monospace)",
            color: "var(--sr-ink-3, #847e6f)", textTransform: "uppercase", letterSpacing: "0.06em",
          }}>{r.status || "—"}</span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{
            fontFamily: "var(--font-mono, monospace)", fontSize: 14, fontWeight: 600,
            color: r.cheap_score != null && r.cheap_score >= 7
              ? "var(--sr-conv-strong, #0f6b3e)"
              : "var(--sr-ink-1, #34302a)",
          }}>{r.cheap_score == null ? "—" : r.cheap_score.toFixed(1)}</div>
          <div style={{
            fontSize: 9, color: "var(--sr-ink-3, #847e6f)",
            textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 500,
          }}>cheap-score</div>
        </div>
      </header>

      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
        {r.classes.map((cls) => {
          const m = classMeta(cls);
          return (
            <span key={cls} style={{
              display: "inline-flex", alignItems: "center", height: 19, padding: "0 6px",
              fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
              color: m.ink, background: m.bg, borderRadius: 3,
              fontFamily: "var(--font-mono, monospace)",
            }}>{m.short}</span>
          );
        })}
        <span style={{
          fontSize: 10.5, color: "var(--sr-ink-3, #847e6f)",
          fontFamily: "var(--font-mono, monospace)",
          alignSelf: "center", marginLeft: 4,
        }}>
          {r.source_count} tags / {r.class_count} classes
        </span>
      </div>

      <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 4 }}>
        {r.classes.map((cls) => {
          const m = classMeta(cls);
          return (
            <li key={cls} style={{
              display: "flex", gap: 8,
              fontSize: 12, color: "var(--sr-ink-1, #34302a)",
              alignItems: "flex-start",
            }}>
              <span style={{
                flex: "0 0 70px",
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 9.5, color: m.ink,
                textTransform: "uppercase", letterSpacing: "0.06em",
                paddingTop: 3, fontWeight: 600,
              }}>{m.short}</span>
              <span style={{ flex: 1, lineHeight: 1.45 }}>{whyForClass(cls, r.sources)}</span>
            </li>
          );
        })}
      </ul>

      <footer style={{
        display: "flex", gap: 6, justifyContent: "flex-end",
        borderTop: "1px solid var(--sr-rule-soft, #e6dfc8)",
        paddingTop: 10,
        flexWrap: "wrap",
      }}>
        <Link href={`/stock/${encodeURIComponent(r.ticker)}`} style={{ ...ghostBtnBase, textDecoration: "none" }}>
          Open detail
        </Link>
        <button style={ghostBtnBase}>Dismiss</button>
        <QueueThesisButton ticker={r.ticker} pattern={queuePattern} />
      </footer>
    </article>
  );
}

function SkeletonCards() {
  return (
    <div style={{ padding: 16, display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} style={{
          background: "var(--sr-paper-1, #f6f4ec)",
          border: "1px solid var(--sr-rule, #d6cfb6)",
          borderRadius: 6, padding: 14, height: 180,
          display: "flex", flexDirection: "column", gap: 10,
        }}>
          <div style={{ height: 22, width: "40%", background: "var(--sr-paper-2, #ece8d8)", borderRadius: 3 }} />
          <div style={{ height: 16, width: "30%", background: "var(--sr-paper-2, #ece8d8)", borderRadius: 3 }} />
          <div style={{ height: 12, width: "60%", background: "var(--sr-paper-2, #ece8d8)", borderRadius: 3 }} />
          <div style={{ height: 12, width: "55%", background: "var(--sr-paper-2, #ece8d8)", borderRadius: 3 }} />
        </div>
      ))}
    </div>
  );
}

const chromeStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  padding: "14px 16px 12px 16px",
  borderBottom: "1px solid var(--sr-rule, #d6cfb6)",
  background: "var(--sr-paper, #fcfcfa)",
  gap: 12,
};

const legendStripStyle: React.CSSProperties = {
  padding: "6px 16px 8px 16px",
  display: "flex",
  gap: 6,
  alignItems: "center",
  flexWrap: "wrap",
  background: "var(--sr-paper, #fcfcfa)",
  borderBottom: "1px solid var(--sr-rule-soft, #e6dfc8)",
};
