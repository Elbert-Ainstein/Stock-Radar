"use client";

import { useEffect, useState } from "react";

interface Section { title: string; body: string }

function parseSections(md: string): Section[] {
  if (!md) return [];
  const fmEnd = md.indexOf("---\n", 4);
  const body = fmEnd > 0 ? md.slice(fmEnd + 4) : md;
  const parts = body.split(/\n## /);
  const result: Section[] = [];
  for (let i = 0; i < parts.length; i++) {
    const chunk = parts[i].trim();
    if (!chunk) continue;
    const newlineIdx = chunk.indexOf("\n");
    if (newlineIdx === -1) {
      const heading = chunk.replace(/^## /, "").trim();
      if (heading) result.push({ title: heading, body: "" });
      continue;
    }
    const heading = chunk.slice(0, newlineIdx).replace(/^## /, "").trim();
    const sectionBody = chunk.slice(newlineIdx + 1).trim();
    if (heading && !heading.toLowerCase().includes("hume notes")) {
      result.push({ title: heading, body: sectionBody });
    }
  }
  return result;
}

// ─── Minimal markdown renderer (pipe tables, ---, bullets, **bold**, *italic*, `code`) ───

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/;
  while (remaining) {
    const m = remaining.match(re);
    if (!m || m.index === undefined) { parts.push(remaining); break; }
    if (m.index > 0) parts.push(remaining.slice(0, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) parts.push(<strong key={key++} style={{ color: "var(--sr-ink)" }}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) parts.push(<code key={key++} style={{ fontFamily: "var(--sr-font-mono)", padding: "1px 4px", borderRadius: 3, background: "var(--sr-paper-2)", color: "var(--sr-ink-1)", fontSize: 11.5 }}>{tok.slice(1, -1)}</code>);
    else parts.push(<em key={key++} style={{ fontStyle: "italic" }}>{tok.slice(1, -1)}</em>);
    remaining = remaining.slice(m.index + tok.length);
  }
  return parts;
}

function renderBlock(md: string): React.ReactNode {
  if (!md.trim()) return null;
  const lines = md.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|[\s|:-]+\|\s*$/.test(lines[i + 1])) {
      const headerCells = line.split("|").slice(1, -1).map(c => c.trim());
      const tableRows: string[][] = [];
      let j = i + 2;
      while (j < lines.length && lines[j].trim().startsWith("|")) {
        tableRows.push(lines[j].split("|").slice(1, -1).map(c => c.trim()));
        j++;
      }
      blocks.push(
        <div key={key++} style={{ overflowX: "auto", margin: "8px 0", border: "1px solid var(--sr-rule-soft)", borderRadius: 4 }}>
          <table style={{ borderCollapse: "collapse", fontSize: 11.5, fontFamily: "var(--sr-font-mono)", width: "100%" }}>
            <thead>
              <tr style={{ background: "var(--sr-paper-2)" }}>{headerCells.map((c, k) => (
                <th key={k} style={{ textAlign: "left", padding: "5px 10px", borderBottom: "1px solid var(--sr-rule-strong)", color: "var(--sr-ink-3)", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase", fontSize: 9.5, whiteSpace: "nowrap" }}>{c}</th>
              ))}</tr>
            </thead>
            <tbody>
              {tableRows.map((row, ri) => (
                <tr key={ri} style={{ borderBottom: ri === tableRows.length - 1 ? "none" : "1px solid var(--sr-rule-soft)", background: ri % 2 === 1 ? "var(--sr-paper-1)" : "transparent" }}>
                  {row.map((c, ci) => (
                    <td key={ci} style={{ padding: "4px 10px", color: "var(--sr-ink-1)", whiteSpace: "nowrap" }}>{renderInline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      i = j;
      continue;
    }
    if (/^---+\s*$/.test(line.trim())) {
      blocks.push(<hr key={key++} style={{ border: "none", borderTop: "1px dashed var(--sr-rule-soft)", margin: "12px 0" }} />);
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={key++} style={{ margin: "8px 0", paddingLeft: 22, listStyle: "disc", color: "var(--sr-ink-1)" }}>
          {items.map((it, k) => <li key={k} style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 3 }}>{renderInline(it)}</li>)}
        </ul>
      );
      continue;
    }
    if (!line.trim()) { i++; continue; }
    const paraLines: string[] = [];
    while (i < lines.length && lines[i].trim() && !lines[i].trim().startsWith("|") && !/^\s*[-*]\s+/.test(lines[i]) && !/^---+\s*$/.test(lines[i].trim())) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length) {
      blocks.push(
        <p key={key++} style={{ fontSize: 12, lineHeight: 1.6, color: "var(--sr-ink-1)", margin: "8px 0" }}>
          {renderInline(paraLines.join(" "))}
        </p>
      );
    }
  }
  return <>{blocks}</>;
}

// Map section title to a tone — colors persistent risks red, catalysts green, etc.
function sectionTone(title: string): { fg: string; bg: string; eyebrow: string } {
  const t = title.toLowerCase();
  if (t.includes("risk")) return { fg: "var(--sr-conv-broken)", bg: "var(--sr-paper)", eyebrow: "var(--sr-conv-broken)" };
  if (t.includes("catalyst")) return { fg: "var(--sr-conv-strong)", bg: "var(--sr-paper)", eyebrow: "var(--sr-conv-strong)" };
  if (t.includes("resolved")) return { fg: "var(--sr-ink-3)", bg: "var(--sr-paper)", eyebrow: "var(--sr-ink-3)" };
  if (t.includes("stale")) return { fg: "var(--sr-ink-3)", bg: "var(--sr-paper)", eyebrow: "var(--sr-ink-3)" };
  return { fg: "var(--sr-rule-strong)", bg: "var(--sr-paper)", eyebrow: "var(--sr-ink-3)" };
}

export default function MemoryPanel({ ticker }: { ticker: string }) {
  const [md, setMd] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [exists, setExists] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    fetch(`/api/thesis/${encodeURIComponent(ticker)}/memory`)
      .then(async (r) => {
        const d = await r.json().catch(() => ({}));
        if (cancelled) return;
        if (!r.ok || d.error) {
          setLoadError(d.error || `HTTP ${r.status}`);
          setExists(false);
          setMd("");
        } else {
          setMd(typeof d.markdown === "string" ? d.markdown : "");
          setExists(!!d.exists);
        }
        setLoading(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setLoadError(e.message || "network error");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [ticker]);

  if (loading) return <div style={{ fontSize: 11, color: "var(--sr-ink-3)", fontStyle: "italic" }}>Loading memory…</div>;

  if (loadError) return (
    <section style={{ padding: 12, borderRadius: 6, border: "1px solid var(--sr-warn-ink)", background: "var(--sr-warn-bg)" }}>
      <div className="sr-eyebrow" style={{ color: "var(--sr-warn-ink)", marginBottom: 4 }}>Memory · failed to load</div>
      <p style={{ fontSize: 12, color: "var(--sr-warn-ink)" }}>
        Could not read memory for {ticker}: <code style={{ fontFamily: "var(--sr-font-mono)", padding: "1px 4px", borderRadius: 3, background: "rgba(0,0,0,0.1)" }}>{loadError}</code>
      </p>
    </section>
  );

  if (!exists) return (
    <section style={{ padding: 16, borderRadius: 6, border: "1px dashed var(--sr-rule-strong)", background: "var(--sr-paper)" }}>
      <div className="sr-eyebrow" style={{ marginBottom: 6 }}>Memory · accumulated context</div>
      <p style={{ fontSize: 12, color: "var(--sr-ink-3)" }}>
        No memory document yet for {ticker}. The first thesis run will create one;
        subsequent runs accumulate trajectory and persistent catalysts/risks here.
      </p>
    </section>
  );

  const sections = parseSections(md);
  if (sections.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.01em", color: "var(--sr-ink)" }}>Memory · accumulated context for {ticker}</h2>
        <span className="sr-eyebrow">Maintained by post-run memory pass</span>
      </div>
      {sections.map((s) => {
        const tone = sectionTone(s.title);
        return (
          <section
            key={s.title}
            style={{
              background: tone.bg,
              border: `1px solid ${tone.fg}`,
              borderRadius: 6,
              overflow: "hidden",
            }}
          >
            <header style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "10px 16px",
              borderBottom: "1px solid var(--sr-rule-soft)",
              background: "var(--sr-paper-1)",
            }}>
              <span className="sr-mono" style={{
                fontSize: 9.5, fontWeight: 600, letterSpacing: "0.1em",
                textTransform: "uppercase", color: tone.eyebrow,
              }}>{s.title}</span>
            </header>
            <div style={{ padding: "10px 16px 14px" }}>
              {renderBlock(s.body)}
            </div>
          </section>
        );
      })}
    </div>
  );
}
