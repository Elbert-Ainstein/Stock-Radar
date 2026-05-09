"use client";

import { useEffect, useState } from "react";
import type { Payload, Tab, HorizonMonths, ThesisData } from "./types";
import { fmtDollar, fmtPct, tabLabel } from "./helpers";
import { Summary } from "./components/TableHelpers";
import ThesisTab from "./components/ThesisTab";
import SetupTab from "./components/SetupTab";
import RisksCatalystsTab from "./components/RisksCatalystsTab";
import FloorTab from "./components/FloorTab";
import IncomeTab from "./components/IncomeTab";
import CashTab from "./components/CashTab";
import FormulasTab from "./components/FormulasTab";
import WhatIfTab from "./components/WhatIfTab";

// ─── SR Production Detailed Model — 8-tab workbook with sr- tokens ──────
// Source: docs/wireframes/v2-production/extracted_e04a3059_detail.jsx → ModelDetailArtboard.

export default function DetailedModel({ ticker }: { ticker: string }) {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("thesis");
  const [horizon, setHorizon] = useState<HorizonMonths>(12);
  const [thesis, setThesis] = useState<ThesisData | null>(null);
  const [, setThesisLoading] = useState(true);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  // Read persisted theme on mount (matches Dashboard + StockDetailPage)
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = localStorage.getItem("sr-theme");
    if (saved === "light") {
      setTheme("light");
      document.documentElement.setAttribute("data-theme", "light");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    if (typeof window === "undefined") return;
    if (next === "light") document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    localStorage.setItem("sr-theme", next);
  };

  useEffect(() => {
    setPayload(null);
    setErr(null);
    fetch(`/api/model/${ticker}?horizon=${horizon}`)
      .then((r) => r.json())
      .then((d) => (d.error ? setErr(d.error) : setPayload(d)))
      .catch((e: Error) => setErr(e.message));
  }, [ticker, horizon]);

  useEffect(() => {
    let cancelled = false;
    setThesis(null);
    setThesisLoading(true);
    fetch(`/api/thesis/${encodeURIComponent(ticker)}`)
      .then((r) => r.json())
      .then((d: ThesisData) => { if (!cancelled) { setThesis(d); setThesisLoading(false); } })
      .catch(() => { if (!cancelled) setThesisLoading(false); });
    return () => { cancelled = true; };
  }, [ticker]);

  if (err) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--sr-paper)", color: "var(--sr-ink)", padding: 32 }}>
        <div style={{ maxWidth: 720, margin: "0 auto", border: "1px solid var(--sr-conv-broken)", background: "var(--sr-err-bg)", color: "var(--sr-err-ink)", borderRadius: 6, padding: 20 }}>
          <div style={{ fontSize: 18, fontWeight: 600 }}>Cannot build model for {ticker}</div>
          <div style={{ marginTop: 8, opacity: 0.85 }}>{err}</div>
          <a href={`/model?ticker=${ticker}`} style={{ display: "inline-block", marginTop: 14, color: "var(--sr-link)", textDecoration: "none" }}>← Back</a>
        </div>
      </div>
    );
  }

  if (!payload) return <div style={{ padding: 32, minHeight: "100vh", background: "var(--sr-paper)", color: "var(--sr-ink-3)" }}>Loading {ticker}…</div>;

  const showThesisStrip = !!thesis?.exists && thesis.thesis_target != null && Number.isFinite(thesis.thesis_target);
  const thesisTarget = thesis?.thesis_target ?? null;
  const cur = payload.target.current_price;
  const upside = thesisTarget != null && cur > 0 ? (thesisTarget - cur) / cur : null;
  const conviction = (thesis?.conviction || "").toUpperCase();
  const convStyle: Record<string, { fg: string; bg: string }> = {
    HIGH:   { fg: "var(--sr-conv-strong)", bg: "var(--sr-conv-strong-bg)" },
    MEDIUM: { fg: "var(--sr-conv-good)",   bg: "var(--sr-conv-good-bg)"   },
    LOW:    { fg: "var(--sr-conv-watch)",  bg: "var(--sr-conv-watch-bg)"  },
    BROKEN: { fg: "var(--sr-conv-broken)", bg: "var(--sr-conv-broken-bg)" },
  };
  const conv = convStyle[conviction] || convStyle.BROKEN;

  return (
    <div style={{ minHeight: "100vh", background: "var(--sr-paper)", color: "var(--sr-ink)" }}>

      <main className="max-w-[1400px] mx-auto" style={{ padding: "16px 18px" }}>
        {payload.target.valuation_method === "revenue_multiple" && (
          <div style={{
            marginBottom: 12, padding: "8px 12px", fontSize: 11.5,
            border: "1px solid var(--sr-info-ink)", background: "var(--sr-info-bg)",
            color: "var(--sr-info-ink)", borderRadius: 5,
            display: "flex", alignItems: "center", gap: 8,
          }}>
            <span style={{ fontWeight: 600 }}>P/S Revenue-Multiple Method</span>
            <span style={{ opacity: 0.7 }}>—</span>
            <span style={{ opacity: 0.85 }}>Pre-profit or extreme P/S detected. Using revenue-based valuation.</span>
          </div>
        )}

        {/* Thesis headline strip — V3 thesis dominates the DCF grid */}
        {showThesisStrip && (
          <div style={{
            marginBottom: 10, padding: "12px 16px",
            border: `1.5px solid ${conv.fg}`, background: conv.bg, borderRadius: 6,
            display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap",
          }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span className="sr-eyebrow" style={{ color: conv.fg }}>Thesis target</span>
              <span className="sr-mono" style={{ fontSize: 22, fontWeight: 600, color: conv.fg, lineHeight: 1.1 }}>{fmtDollar(thesisTarget)}</span>
              {upside != null && <span className="sr-mono" style={{ fontSize: 11, color: conv.fg, opacity: 0.8 }}>{fmtPct(upside)} upside</span>}
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span className="sr-eyebrow" style={{ color: conv.fg }}>Conviction</span>
              <span className="sr-mono" style={{ fontSize: 13, fontWeight: 700, color: conv.fg, padding: "2px 7px", border: `1px solid ${conv.fg}`, borderRadius: 3, marginTop: 2, alignSelf: "flex-start" }}>
                {conviction}{thesis?.position_size_pct != null ? ` · ${thesis.position_size_pct}%` : ""}
              </span>
            </div>
            {thesis?.breakout_price != null && (
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span className="sr-eyebrow">Breakout</span>
                <span className="sr-mono" style={{ fontSize: 14, color: conv.fg, opacity: 0.85 }}>{fmtDollar(thesis.breakout_price)}</span>
              </div>
            )}
            <div style={{ flex: 1, minWidth: 12 }} />
            <span style={{ fontSize: 11, fontStyle: "italic", color: "var(--sr-ink-3)" }}>
              Headline: V3 thesis. The DCF grid below is the conservative floor.
            </span>
          </div>
        )}

        {/* DCF summary — 4 tiles, secondary to thesis */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 14 }}>
          <Summary label="Current" value={fmtDollar(payload.target.current_price)} />
          <Summary label="Downside" value={fmtDollar(payload.target.low)} sub={fmtPct(payload.target.upside_low_pct)} />
          <Summary label={payload.target.valuation_method === "revenue_multiple" ? "Floor base (P/S)" : "Floor base (DCF)"} value={fmtDollar(payload.target.base)} sub={fmtPct(payload.target.upside_base_pct)} emphasize />
          <Summary label="Upside" value={fmtDollar(payload.target.high)} sub={fmtPct(payload.target.upside_high_pct)} />
        </div>

        {/* Tab strip — scroll-snap on mobile */}
        <div
          style={{
            display: "flex", gap: 0, marginBottom: 14,
            borderBottom: "1px solid var(--sr-rule-strong)",
            overflowX: "auto", marginLeft: -8, paddingLeft: 8,
            scrollSnapType: "x mandatory", WebkitOverflowScrolling: "touch",
          }}
        >
          {(["thesis", "setup", "risks", "floor", "income", "cashflow", "formulas", "whatif"] as Tab[]).map((id) => {
            const active = tab === id;
            return (
              <button
                key={id}
                onClick={() => setTab(id)}
                style={{
                  padding: "9px 14px", fontSize: 12.5,
                  background: "transparent", border: "none", cursor: "pointer",
                  color: active ? "var(--sr-ink)" : "var(--sr-ink-2)",
                  fontWeight: active ? 600 : 500,
                  borderBottom: active ? "2px solid var(--sr-ink)" : "2px solid transparent",
                  flexShrink: 0, whiteSpace: "nowrap",
                  scrollSnapAlign: "start",
                  fontFamily: "var(--font-sans)",
                }}
              >
                {tabLabel(id)}
              </button>
            );
          })}
        </div>

        {tab === "thesis" && <ThesisTab thesis={thesis} loading={false} />}
        {tab === "setup" && <SetupTab thesis={thesis} loading={false} />}
        {tab === "risks" && <RisksCatalystsTab thesis={thesis} loading={false} />}
        {tab === "floor" && <FloorTab payload={payload} thesis={thesis} />}
        {tab === "income" && <IncomeTab payload={payload} />}
        {tab === "cashflow" && <CashTab payload={payload} />}
        {tab === "formulas" && <FormulasTab payload={payload} />}
        {tab === "whatif" && <WhatIfTab payload={payload} />}

        {payload.warnings && payload.warnings.length > 0 && (
          <div style={{
            marginTop: 18, padding: "10px 14px",
            border: "1px solid var(--sr-warn-ink)", background: "var(--sr-warn-bg)",
            color: "var(--sr-warn-ink)", borderRadius: 5,
            fontSize: 11.5,
          }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Warnings</div>
            <ul style={{ margin: 0, paddingLeft: 18, listStyle: "disc" }}>
              {payload.warnings.map((w, i) => <li key={i} style={{ marginBottom: 2 }}>{w}</li>)}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
