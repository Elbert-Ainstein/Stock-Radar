import type { Stock } from "@/lib/data";
import { cn, signalBg, signalColor, signalIcon, aiColor } from "./helpers";
import { ThesisHeaderPanel } from "./ThesisHeader";
import SetupAndRisks from "./SetupAndRisks";
import HumeNotesEditor from "./HumeNotesEditor";
import MemoryPanel from "./MemoryPanel";

// ─── SR Production Stock Detail (inline expansion) ──────────────────────
// 2-column layout: main thesis surface (left) + memory/notes/scouts side rail.
// Source: docs/wireframes/v2-production/extracted_7ea0afe1_detail.jsx → DetailDesktop.

const surfaceStyle: React.CSSProperties = {
  background: "var(--sr-paper)",
  border: "1px solid var(--sr-rule-strong)",
  borderRadius: 6,
  overflow: "hidden",
};

function SectionHeader({ eyebrow, children, right }: { eyebrow: string; children?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "10px 16px", borderBottom: "1px solid var(--sr-rule-soft)",
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span className="sr-mono" style={{
          fontSize: 9.5, fontWeight: 500, letterSpacing: "0.1em",
          textTransform: "uppercase", color: "var(--sr-ink-3)",
        }}>{eyebrow}</span>
        {children && <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--sr-ink)" }}>{children}</span>}
      </div>
      {right}
    </div>
  );
}

export default function StockDetail({ stock, onDelete }: { stock: Stock; onDelete: () => void }) {
  const t = stock.thesisRun;
  const kEval = stock.killConditionEval;

  return (
    <div style={{ background: "var(--sr-paper)", borderTop: "1px solid var(--sr-rule-strong)" }}>
    <div style={{
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr) 360px",
    }}>
      {/* ─── MAIN COLUMN ──────────────────────────────────────────────── */}
      <div style={{
        padding: "18px 22px",
        display: "flex", flexDirection: "column", gap: 14,
        borderRight: "1px solid var(--sr-rule-soft)",
        minWidth: 0,
      }}>
        {/* Header: ticker · name · tags · delete */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
              <h2 className="sr-mono" style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-0.02em", color: "var(--sr-ink)" }}>{stock.ticker}</h2>
              <span style={{ fontSize: 14, color: "var(--sr-ink-2)" }}>{stock.name}</span>
            </div>
            {stock.tags.length > 0 && (
              <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                {stock.tags.map(tag => (
                  <span key={tag} className="sr-mono" style={{
                    fontSize: 9.5, padding: "2px 6px", borderRadius: 3,
                    color: "var(--sr-ink-3)", background: "var(--sr-paper-2)",
                    border: "1px solid var(--sr-rule)", letterSpacing: "0.04em",
                  }}>{tag}</span>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={onDelete}
            title={`Remove ${stock.ticker} from watchlist`}
            style={{
              width: 28, height: 28, display: "inline-flex", alignItems: "center", justifyContent: "center",
              border: "1px solid var(--sr-rule)", borderRadius: 4,
              background: "var(--sr-paper-1)", color: "var(--sr-ink-3)", cursor: "pointer",
            }}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M3 4h10M6.5 4V3a1 1 0 011-1h1a1 1 0 011 1v1M5.5 7v4.5M8 7v4.5M10.5 7v4.5M4.5 4l.5 8.5a1 1 0 001 1h4a1 1 0 001-1L11.5 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>

        {/* Watchlist thesis (one-liner) */}
        {stock.watchlistThesis && (
          <section style={surfaceStyle}>
            <SectionHeader eyebrow="10x Thesis · operator note">{null}</SectionHeader>
            <p style={{ padding: "12px 16px 14px", fontSize: 13, lineHeight: 1.55, color: "var(--sr-ink-1)" }}>
              {stock.watchlistThesis}
            </p>
          </section>
        )}

        {/* Kill condition (when set) */}
        {stock.killCondition && (() => {
          const kStatus = kEval?.status || "unchecked";
          const tone = kStatus === "triggered" ? { fg: "var(--sr-conv-broken)", bg: "var(--sr-err-bg)", label: "THESIS BREAK" }
            : kStatus === "warning" ? { fg: "var(--sr-conv-watch)", bg: "var(--sr-warn-bg)", label: "WATCH" }
            : kStatus === "safe" ? { fg: "var(--sr-conv-strong)", bg: "var(--sr-ok-bg)", label: "SAFE" }
            : null;
          return (
            <section style={{ ...surfaceStyle, borderColor: tone?.fg ?? "var(--sr-rule-strong)" }}>
              <SectionHeader
                eyebrow="Kill condition"
                right={tone && (
                  <span className="sr-mono" style={{
                    fontSize: 9, fontWeight: 600, padding: "2px 6px", borderRadius: 3,
                    color: tone.fg, background: tone.bg, border: `1px solid ${tone.fg}`,
                    letterSpacing: "0.06em",
                  }}>{tone.label}</span>
                )}
              >{null}</SectionHeader>
              <div style={{ padding: "12px 16px 14px" }}>
                <p style={{ fontSize: 13, color: "var(--sr-ink-1)" }}>{stock.killCondition}</p>
                {kEval?.reasoning && kStatus !== "safe" && (
                  <p style={{ fontSize: 11.5, color: "var(--sr-ink-3)", marginTop: 6, fontStyle: "italic" }}>{kEval.reasoning}</p>
                )}
              </div>
            </section>
          );
        })()}

        {/* Thesis headline panel (existing component, wrapped in surface) */}
        <ThesisHeaderPanel
          thesis={stock.thesisRun}
          currency={stock.currency}
          spotPrice={stock.price}
          ticker={stock.ticker}
          onRerunComplete={() => { if (typeof window !== "undefined") window.location.reload(); }}
        />

        {/* Setup + Risks + Catalysts */}
        {t && <SetupAndRisks thesis={t} currency={stock.currency} />}

        {/* Scout signals (compact 2-col grid) */}
        {stock.signals.length > 0 && (
          <section style={surfaceStyle}>
            <SectionHeader eyebrow={`Scout signals · ${stock.signals.length} active`}>{null}</SectionHeader>
            <div style={{
              padding: 12,
              display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 8,
            }}>
              {stock.signals.map((sig, i) => (
                <div key={i} className={cn("rounded border p-2.5", signalBg(sig.signal))} style={{
                  borderColor: "var(--sr-rule-soft)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span className={cn("text-xs font-bold", signalColor(sig.signal))}>{signalIcon(sig.signal)}</span>
                      <span style={{ fontSize: 11.5, fontWeight: 600, color: aiColor(sig.ai) }}>{sig.scout}</span>
                      <span style={{ fontSize: 10, color: "var(--sr-ink-3)" }}>via {sig.ai}</span>
                    </div>
                    <span className={cn("text-[9px] font-mono uppercase font-semibold", signalColor(sig.signal))}>{sig.signal}</span>
                  </div>
                  <p style={{ fontSize: 11.5, lineHeight: 1.45, color: "var(--sr-ink-2)" }}>{sig.summary}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Upcoming catalysts (chip list) */}
        {stock.catalysts.length > 0 && (
          <section style={surfaceStyle}>
            <SectionHeader eyebrow="Upcoming catalysts">{null}</SectionHeader>
            <div style={{ padding: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
              {stock.catalysts.map((c, i) => (
                <span key={i} style={{
                  fontSize: 11, padding: "4px 9px", borderRadius: 4,
                  color: "var(--sr-ink-2)", background: "var(--sr-paper-1)",
                  border: "1px solid var(--sr-rule)",
                }}>{c}</span>
              ))}
            </div>
          </section>
        )}

        {/* Workbook links */}
        <div style={{
          display: "flex", gap: 8, flexWrap: "wrap",
          paddingTop: 6, borderTop: "1px dashed var(--sr-rule-soft)",
        }}>
          <a href={`/model?ticker=${stock.ticker}`} style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "8px 14px", borderRadius: 5,
            background: "var(--sr-paper-1)", color: "var(--sr-ink-1)",
            border: "1px solid var(--sr-rule)", fontSize: 12, fontWeight: 500,
            textDecoration: "none",
          }}>
            <span>📐</span> What-If Sandbox <span className="sr-mono" style={{ fontSize: 10, color: "var(--sr-ink-3)" }}>→ Sliders</span>
          </a>
          <a href={`/model/${stock.ticker}/detailed`} style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "8px 14px", borderRadius: 5,
            background: "var(--sr-conv-strong-bg)", color: "var(--sr-conv-strong)",
            border: "1px solid var(--sr-conv-strong)", fontSize: 12, fontWeight: 500,
            textDecoration: "none",
          }}>
            <span>📊</span> Full Workbook <span className="sr-mono" style={{ fontSize: 10, opacity: 0.7 }}>→ DCF · Income · Cash</span>
          </a>
        </div>
      </div>

      {/* ─── SIDE RAIL ─────────────────────────────────────────────────── */}
      <div style={{
        padding: "18px 18px",
        background: "var(--sr-paper-1)",
        display: "flex", flexDirection: "column", gap: 14,
        minWidth: 0,
      }}>
        <HumeNotesEditor ticker={stock.ticker} />
      </div>
    </div>
    {/* Full-width memory section (spans the full detail panel width) */}
    <div style={{ padding: "18px 22px", borderTop: "1px solid var(--sr-rule-soft)" }}>
      <MemoryPanel ticker={stock.ticker} />
    </div>
    </div>
  );
}
