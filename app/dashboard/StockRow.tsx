import { useState } from "react";
import type { Stock } from "@/lib/data";
import { cn, scoreColor } from "./helpers";
import Sparkline from "./Sparkline";

// ─── SR Production Watchlist Row ─────────────────────────────────────────
// CSS-grid based (not <table>) to avoid Tailwind v4 preflight quirks.
// Source: docs/wireframes/v2-production/extracted_cf1ed42f_watchlist.jsx
// 14 columns × 28px row, alternating row backgrounds, mono numerics.

const CCY: Record<string, string> = {
  USD: "$", HKD: "HK$", EUR: "€", GBP: "£", JPY: "¥",
};

const fmtMoney = (v: number | null | undefined, ccy = "USD") => {
  if (v == null || !isFinite(v)) return "—";
  const sym = CCY[ccy] || "$";
  const abs = Math.abs(v);
  const f = abs >= 1000 ? abs.toLocaleString(undefined, { maximumFractionDigits: 2 }) : abs.toFixed(2);
  return `${v < 0 ? "−" : ""}${sym}${f}`;
};

const fmtChg = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}`;
const fmtPct = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}%`;

const CONV: Record<string, { fg: string; bg: string }> = {
  HIGH:   { fg: "var(--sr-conv-strong)", bg: "var(--sr-conv-strong-bg)" },
  MEDIUM: { fg: "var(--sr-conv-good)",   bg: "var(--sr-conv-good-bg)"   },
  LOW:    { fg: "var(--sr-conv-watch)",  bg: "var(--sr-conv-watch-bg)"  },
  BROKEN: { fg: "var(--sr-conv-broken)", bg: "var(--sr-conv-broken-bg)" },
};

function ConvictionPill({ tier }: { tier?: string | null }) {
  const t = (tier || "").toUpperCase();
  const sty = CONV[t];
  if (!sty) return <span style={{ color: "var(--sr-ink-3)", fontSize: 10.5 }} className="sr-mono">—</span>;
  return (
    <span className="sr-mono" style={{
      display: "inline-flex", alignItems: "center", height: 17, padding: "0 6px",
      fontSize: 9.5, fontWeight: 600, letterSpacing: "0.06em",
      color: sty.fg, background: sty.bg, border: `1px solid ${sty.fg}`,
      borderRadius: 3, whiteSpace: "nowrap",
    }}>{t}</span>
  );
}

// Grid columns (px). Match SRWatchlistHeader exactly.
export const SR_GRID = "76px 150px 86px 70px 64px 90px 96px 86px 66px 60px 120px 110px 90px 40px";

export function SRWatchlistHeader() {
  const labels: Array<[string, string]> = [
    ["TICKER", "left"], ["NAME", "left"], ["LAST", "right"], ["CHG", "right"], ["%", "right"],
    ["30D", "left"], ["CONVICTION", "left"], ["THESIS", "right"], ["UPSIDE", "right"], ["SCORE", "right"],
    ["DRIFT", "left"], ["SETUP", "left"], ["LAST RUN", "left"], ["", "right"],
  ];
  return (
    <div
      className="sr-mono"
      style={{
        display: "grid", gridTemplateColumns: SR_GRID,
        height: 26, padding: "0 4px",
        background: "var(--sr-paper-1)",
        borderBottom: "1px solid var(--sr-rule-strong)", boxShadow: "inset 0 -1px 0 var(--sr-rule-strong)",
        fontSize: 9.5, fontWeight: 500, letterSpacing: "0.1em",
        color: "var(--sr-ink-3)", textTransform: "uppercase",
      }}
    >
      {labels.map(([l, a], i) => (
        <div key={i} style={{ padding: "0 10px", display: "flex", alignItems: "center", justifyContent: a === "right" ? "flex-end" : "flex-start" }}>
          {l}
        </div>
      ))}
    </div>
  );
}

const relTime = (iso?: string) => {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (!isFinite(ms) || ms < 0) return "—";
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.round(min / 60);
  if (hr < 48) return `${hr}h`;
  return `${Math.round(hr / 24)}d`;
};

const setupSummary = (filters?: Record<string, { pass: boolean }>) => {
  if (!filters) return "—";
  const total = Object.keys(filters).length;
  const passing = Object.values(filters).filter((f) => f?.pass).length;
  return `${passing}/${total} pass`;
};

function RunThesisCell({ ticker }: { ticker: string }) {
  // Three-state button: idle (lightning) → queued (spinner-ish) → done/error.
  // Uses POST /api/thesis/[ticker]/rerun. stopPropagation prevents the parent
  // row's onClick (navigate to /stock/[ticker]) from firing.
  const [phase, setPhase] = useState<"idle" | "queuing" | "queued" | "error">("idle");
  const onClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (phase === "queuing" || phase === "queued") return;
    setPhase("queuing");
    try {
      const res = await fetch(`/api/thesis/${encodeURIComponent(ticker)}/rerun`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trigger_reason: "manual" }),
      });
      if (!res.ok) {
        setPhase("error");
        setTimeout(() => setPhase("idle"), 4000);
        return;
      }
      setPhase("queued");
      setTimeout(() => setPhase("idle"), 6000);
    } catch {
      setPhase("error");
      setTimeout(() => setPhase("idle"), 4000);
    }
  };
  const fg = phase === "queued" ? "var(--sr-conv-strong)"
           : phase === "error"  ? "var(--sr-neg)"
           : phase === "queuing"? "var(--sr-ink-2)"
           : "var(--sr-ink-3)";
  const label = phase === "queued" ? "✓"
              : phase === "error"  ? "!"
              : phase === "queuing"? "…"
              : "⚡";
  const title = phase === "queued" ? `Thesis run queued for ${ticker}`
              : phase === "error"  ? `Failed to queue ${ticker} — click to retry`
              : phase === "queuing"? `Queueing ${ticker}…`
              : `Run thesis for ${ticker} (~$3-5 Opus)`;
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      style={{
        background: "transparent",
        border: "none",
        color: fg,
        fontSize: 13,
        cursor: phase === "queuing" || phase === "queued" ? "default" : "pointer",
        padding: 0,
        width: 22,
        height: 22,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 3,
        fontFamily: "var(--sr-font-mono)",
        lineHeight: 1,
      }}
      onMouseEnter={(e) => { if (phase === "idle") (e.currentTarget as HTMLElement).style.background = "var(--sr-paper-2)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
    >{label}</button>
  );
}


export default function StockRow({
  stock, isSelected, onClick, selectMode = false, isChecked = false, onCheck, rowIndex = 0,
}: {
  stock: Stock; isSelected: boolean; onClick: () => void;
  selectMode?: boolean; isChecked?: boolean; onCheck?: (t: string) => void;
  rowIndex?: number;
}) {
  const t = stock.thesisRun;
  const tgt = t?.thesis_target ?? null;
  const upside = tgt != null && stock.price > 0 ? ((tgt - stock.price) / stock.price) * 100 : null;
  const driftAbove = tgt != null && stock.price > 0 ? tgt > stock.price : null;
  const driftPct = tgt != null && stock.price > 0 ? ((tgt - stock.price) / stock.price) * 100 : null;

  const click = () => {
    if (selectMode) { onCheck?.(stock.ticker); return; }
    if (typeof window !== "undefined") window.location.href = `/stock/${encodeURIComponent(stock.ticker)}`;
    onClick(); // legacy noop — kept for compat
  };

  const rowBg = isSelected
    ? "var(--sr-paper-2)"
    : selectMode && isChecked
    ? "var(--sr-err-bg)"
    : rowIndex % 2 === 1
    ? "var(--sr-paper-2)"
    : "var(--sr-paper)";

  const cellLeft: React.CSSProperties = { padding: "0 10px", display: "flex", alignItems: "center", justifyContent: "flex-start", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 };
  const cellRight: React.CSSProperties = { ...cellLeft, justifyContent: "flex-end" };
  const numStyle: React.CSSProperties = { fontFamily: "var(--sr-font-mono)", fontVariantNumeric: "tabular-nums slashed-zero" };

  const chgColor = stock.change > 0 ? "var(--sr-pos)" : stock.change < 0 ? "var(--sr-neg)" : "var(--sr-neutral)";
  const pctColor = stock.changePct > 0 ? "var(--sr-pos)" : stock.changePct < 0 ? "var(--sr-neg)" : "var(--sr-neutral)";
  const upColor = upside == null ? "var(--sr-ink-3)" : upside > 0 ? "var(--sr-pos)" : "var(--sr-neg)";

  return (
    <div
      onClick={click}
      role="row"
      aria-selected={isSelected}
      className="cursor-pointer"
      style={{
        display: "grid",
        gridTemplateColumns: SR_GRID,
        height: 28,
        background: rowBg,
        borderBottom: "1px solid var(--sr-rule-strong)", boxShadow: "inset 0 -1px 0 var(--sr-rule-strong)",
        borderLeft: isSelected ? "3px solid var(--sr-ink-1)" : "3px solid transparent",
        fontSize: 12,
        color: "var(--sr-ink-1)",
      }}
    >
      {/* TICKER */}
      <div style={{ ...cellLeft, fontFamily: "var(--sr-font-mono)", fontWeight: 600, color: "var(--sr-ink)", letterSpacing: "0.02em", gap: 6 }}>
        {selectMode && (
          <span
            onClick={(e) => { e.stopPropagation(); onCheck?.(stock.ticker); }}
            className={cn(
              "inline-flex items-center justify-center rounded-sm flex-shrink-0",
              isChecked ? "bg-red-500" : "border border-[var(--sr-rule-strong)]"
            )}
            style={{ width: 14, height: 14 }}
          >
            {isChecked && <span className="text-white text-[8px] leading-none">✓</span>}
          </span>
        )}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{stock.ticker}</span>
      </div>
      {/* NAME */}
      <div style={{ ...cellLeft, color: "var(--sr-ink-2)" }}>{stock.name}</div>
      {/* LAST */}
      <div style={{ ...cellRight, ...numStyle, color: "var(--sr-ink)", fontWeight: 500 }}>{fmtMoney(stock.price, stock.currency)}</div>
      {/* CHG */}
      <div style={{ ...cellRight, ...numStyle, color: chgColor }}>{fmtChg(stock.change)}</div>
      {/* % */}
      <div style={{ ...cellRight, ...numStyle, fontSize: 11.5, color: pctColor }}>{fmtPct(stock.changePct)}</div>
      {/* 30D Sparkline */}
      <div style={{ ...cellLeft, padding: "0 8px" }}>
        {stock.scoreHistory && stock.scoreHistory.length >= 2 ? (
          <Sparkline data={stock.scoreHistory} color={stock.scoreDelta >= 0 ? "var(--sr-pos)" : "var(--sr-neg)"} width={74} height={20} />
        ) : (
          <span style={{ color: "var(--sr-ink-4)", fontSize: 10 }}>—</span>
        )}
      </div>
      {/* CONVICTION */}
      <div style={cellLeft}><ConvictionPill tier={t?.conviction} /></div>
      {/* THESIS */}
      <div style={{ ...cellRight, ...numStyle, fontWeight: 600, color: "var(--sr-ink)" }}>
        {tgt != null ? fmtMoney(tgt, stock.currency) : <span style={{ color: "var(--sr-ink-3)" }}>—</span>}
      </div>
      {/* UPSIDE */}
      <div style={{ ...cellRight, ...numStyle, fontSize: 11.5, color: upColor }}>
        {upside == null ? "—" : `${upside > 0 ? "+" : "−"}${Math.abs(upside).toFixed(0)}%`}
      </div>
      {/* SCORE */}
      <div style={{ ...cellRight, ...numStyle, fontWeight: 600 }}>
        <span className={cn("sr-mono", scoreColor(stock.score))}>{stock.score.toFixed(1)}</span>
      </div>
      {/* DRIFT */}
      <div style={{ ...cellLeft, fontSize: 10.5, fontFamily: "var(--sr-font-mono)" }}>
        {driftPct == null || driftAbove == null ? null : (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: driftAbove ? "var(--sr-conv-strong)" : "var(--sr-conv-fade)" }}>
            <span style={{ fontSize: 11 }}>{driftAbove ? "↑" : "↓"}</span>
            {driftAbove ? "above" : "below"} {Math.abs(driftPct).toFixed(0)}%
          </span>
        )}
      </div>
      {/* SETUP */}
      <div style={{ ...cellLeft, fontSize: 11, color: "var(--sr-ink-2)", fontStyle: "italic" }}>{setupSummary(t?.filters)}</div>
      {/* LAST RUN */}
      <div style={{ ...cellLeft, fontSize: 11, color: "var(--sr-ink-3)", fontFamily: "var(--sr-font-mono)" }}>
        {t?.run_at ? `${relTime(t.run_at)} ago` : <span style={{ fontStyle: "italic" }}>never</span>}
      </div>
      {/* Run-Thesis button (replaces former chevron) */}
      <div style={{ ...cellRight, padding: "0 6px" }}>
        <RunThesisCell ticker={stock.ticker} />
      </div>
    </div>
  );
}
