/* Components sheet + lighter views (Discovery, Ask AI, Logs, Model picker) */

// ────────────────────────────────────────────────────────────
// Component sheet — ConvictionBadge / MoneyValue / RunButton / NoteEditor
// ────────────────────────────────────────────────────────────
const ComponentSheet = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760, padding: 24 }}>
    <div className="wf-h1" style={{ marginBottom: 18 }}>Cross-cutting components</div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>

      {/* ConvictionBadge */}
      <div className="wf-rough-soft" style={{ padding: 16 }}>
        <div className="wf-eyebrow">CONVICTION BADGE · all tiers · 2 sizes · both themes</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, alignItems: 'center' }}>
          <Conv tier="HIGH" /><Conv tier="MEDIUM" /><Conv tier="LOW" /><Conv tier="BROKEN" />
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 10, alignItems: 'center' }}>
          <Conv tier="HIGH" size="lg" /><Conv tier="MEDIUM" size="lg" /><Conv tier="LOW" size="lg" /><Conv tier="BROKEN" size="lg" />
        </div>
        <div className="wf-tiny" style={{ marginTop: 10, lineHeight: 1.6 }}>
          load-bearing colors, never decorative<br/>
          mono caps · 1px border · solid bg · ≥4.5:1 contrast both themes
        </div>
      </div>

      {/* MoneyValue */}
      <div className="wf-rough-soft" style={{ padding: 16 }}>
        <div className="wf-eyebrow">MONEY VALUE · USD · HKD · EUR · signed</div>
        <div style={{ display: 'flex', gap: 16, marginTop: 12, flexWrap: 'wrap' }}>
          <Money v={949.93} ccy="USD" big />
          <Money v={67.50} ccy="HKD" big />
          <Money v={932.10} ccy="EUR" big />
        </div>
        <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
          <Money v={47.61} ccy="USD" signed />
          <Money v={-1.20} ccy="HKD" signed />
          <Pct v={5.28} /><Pct v={-1.75} />
        </div>
        <div className="wf-tiny" style={{ marginTop: 10 }}>
          tabular figures · decimal align · sign char + color (never color alone)
        </div>
      </div>

      {/* RunButton */}
      <div className="wf-rough-soft" style={{ padding: 16 }}>
        <div className="wf-eyebrow">RUN BUTTON · idle / starting / running / done / partial / error</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
          <button className="wf-btn wf-btn-primary" style={{ width: 220 }}>▶ Run all theses</button>
          <button className="wf-btn" style={{ width: 220, color: 'var(--ink-3)' }}>◐ starting…</button>
          <button className="wf-btn" style={{ width: 220, background: 'var(--paper-2)' }}>
            ◉ running 7/12 · est 4m
          </button>
          <button className="wf-btn" style={{ width: 220, color: 'var(--pos)' }}>✓ done · 12/12 · 6m 40s</button>
          <button className="wf-btn" style={{ width: 220, color: 'var(--conv-med)', background: 'var(--conv-med-bg)', borderColor: 'var(--conv-med)' }}>⚠ partial · 9/12 · retry?</button>
          <button className="wf-btn" style={{ width: 220, color: 'var(--neg)', background: 'var(--conv-broken-bg)', borderColor: 'var(--neg)' }}>✕ error · view logs</button>
        </div>
      </div>

      {/* NoteEditor */}
      <div className="wf-rough-soft" style={{ padding: 16 }}>
        <div className="wf-eyebrow">NOTE EDITOR · monospace · Hume Notes · auto-save</div>
        <div style={{
          marginTop: 12, padding: 10, border: '1.5px solid var(--rule)', borderRadius: 3,
          background: 'var(--paper)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span className="wf-eyebrow">HUME NOTES · verbatim</span>
            <span className="wf-tiny wf-pos">● saved 12s ago · 412ch</span>
          </div>
          <div className="wf-mono" style={{ fontSize: 11, lineHeight: 1.6, minHeight: 80, color: 'var(--ink-2)' }}>
            spoke w/ K — channel checks confirm Q3 ramp.<br/>
            core thesis intact, breakout $340 valid.<br/>
            <span style={{ color: 'var(--ink-3)' }}>cursor▍</span>
          </div>
        </div>
        <div className="wf-tiny" style={{ marginTop: 8 }}>
          monospace = "this is a logbook, not chat" · explicit "preserved verbatim" framing
        </div>
      </div>

    </div>

    {/* Other atoms */}
    <div className="wf-h2" style={{ marginTop: 24, marginBottom: 12 }}>Other atoms</div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 16 }}>
      <div className="wf-rough-soft" style={{ padding: 12 }}>
        <div className="wf-eyebrow" style={{ marginBottom: 8 }}>SPARKLINE</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Spark dir="up" w={80} h={28} />
          <Spark dir="down" w={80} h={28} data={[12,11,10,8,9,7,6,5,4,5,3,4]} />
        </div>
      </div>
      <div className="wf-rough-soft" style={{ padding: 12 }}>
        <div className="wf-eyebrow" style={{ marginBottom: 8 }}>FILTER DOTS · 5</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Dots n={5} /><Dots n={4} /><Dots n={3} /><Dots n={1} />
        </div>
      </div>
      <div className="wf-rough-soft" style={{ padding: 12 }}>
        <div className="wf-eyebrow" style={{ marginBottom: 8 }}>HORIZON PICKER</div>
        <div style={{ display: 'flex', gap: 4 }}>
          <Chip>12mo</Chip><Chip active>24mo</Chip><Chip>36mo</Chip>
        </div>
      </div>
      <div className="wf-rough-soft" style={{ padding: 12 }}>
        <div className="wf-eyebrow" style={{ marginBottom: 8 }}>EMPTY · LOAD-FAIL</div>
        <div className="wf-dashed" style={{ padding: 8 }}>
          <div className="wf-tiny">no thesis run yet</div>
        </div>
        <div style={{ padding: 8, marginTop: 6, border: '1.25px solid var(--conv-med)', background: 'var(--conv-med-bg)', borderRadius: 3 }}>
          <div className="wf-tiny" style={{ color: 'var(--conv-med)' }}>load failed · retry?</div>
        </div>
      </div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// Discovery feed
// ────────────────────────────────────────────────────────────
const DiscoveryA = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <div style={{ padding: 16 }}>
      <div className="wf-h2" style={{ marginBottom: 12 }}>Discovery feed</div>
      {[
        ['CRDO', 'Credo Technology', 'Photonics', 'fund scout flagged 3× rev acceleration; AEC ramp matches LITE thesis pattern', 'Fund · News'],
        ['ALAB', 'Astera Labs', 'Networking', 'insider scout: CFO bought 12k @ $84; quant scout: momentum percentile 96', 'Insider · Quant'],
        ['SOXL', 'Direxion Semis 3×', 'Sector ETF', 'macro scout: cycle-aware basket pattern triggered against current watchlist', 'Macro'],
        ['1810.HK', 'Xiaomi', 'Consumer Tech', 'discovery scout: EV ramp + handset gross margin inflection visible in latest filing', 'Discovery · Filings'],
      ].map(([t, n, s, why, src]) => (
        <div key={t} className="wf-rough-soft" style={{ padding: 12, marginBottom: 8, display: 'grid', gridTemplateColumns: '120px 1fr 220px 140px', gap: 12, alignItems: 'center' }}>
          <div>
            <div className="wf-mono" style={{ fontSize: 18, fontWeight: 600 }}>{t}</div>
            <div className="wf-tiny">{n}</div>
          </div>
          <div className="wf-tiny" style={{ lineHeight: 1.5 }}>
            <span className="wf-anno-tag" style={{ background: 'var(--paper-2)', color: 'var(--ink-3)' }}>why now</span> {why}
          </div>
          <div className="wf-tiny wf-mono" style={{ color: 'var(--ink-3)' }}>{src} · {s}</div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="wf-btn">dismiss</button>
            <button className="wf-btn wf-btn-primary">+ watchlist</button>
          </div>
        </div>
      ))}
    </div>
    <div style={{ position: 'absolute', right: 24, top: 80, width: 200 }}>
      <div className="wf-postit">discovery — no scoring theatre. each card is "why this came up" + 1-click adopt.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// Ask AI
// ────────────────────────────────────────────────────────────
const AskA = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <div style={{ padding: '40px 80px', maxWidth: 900 }}>
      <div className="wf-h2" style={{ marginBottom: 14 }}>Ask AI · across all watchlist data</div>
      <div style={{ border: '1.5px solid var(--rule)', borderRadius: 3, padding: 12, background: 'var(--paper)' }}>
        <div className="wf-mono" style={{ fontSize: 13, color: 'var(--ink-2)', minHeight: 50 }}>
          which tickers in watchlist have a thesis target above DCF high but conviction MEDIUM or worse?<span style={{ color: 'var(--ink-3)' }}>▍</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, alignItems: 'center' }}>
          <span className="wf-tiny wf-mono" style={{ color: 'var(--ink-3)' }}>scope: 12 watchlist · all theses · ⌘↩</span>
          <button className="wf-btn wf-btn-primary">ask</button>
        </div>
      </div>
      <div style={{ marginTop: 20 }}>
        <div className="wf-eyebrow" style={{ marginBottom: 8 }}>ANSWER · 2 matches</div>
        <div className="wf-rough-soft" style={{ padding: 14, background: 'var(--paper-2)' }}>
          <div className="wf-tiny" style={{ lineHeight: 1.7 }}>
            two tickers fit: <span className="wf-mono" style={{ fontWeight: 600 }}>ASML</span> (thesis $1100 vs DCF high $980 · MEDIUM) and <span className="wf-mono" style={{ fontWeight: 600 }}>AMAT</span> (thesis $245 vs DCF high $228 · MEDIUM).
            both signal "thesis above floor" — engine sees less upside than the V3 thesis. consider downgrading position size or revisiting setup quality.
          </div>
        </div>
      </div>
      <div style={{ marginTop: 18 }}>
        <div className="wf-eyebrow" style={{ marginBottom: 6 }}>RECENT QUERIES</div>
        <div className="wf-tiny" style={{ lineHeight: 1.8, color: 'var(--ink-3)' }}>
          → which tickers have kill triggers about to fire?<br/>
          → compare CRWV and NBIS scout signals<br/>
          → summarize hume notes mentioning "channel checks"
        </div>
      </div>
    </div>
    <div style={{ position: 'absolute', right: 24, top: 80, width: 200 }}>
      <div className="wf-postit">stripped to essentials. one box. no chat history theatre — just last 3 queries.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// Logs
// ────────────────────────────────────────────────────────────
const LogsA = () => {
  const runs = [
    ['2026-05-03 14:23:11', 'theses', '6m 40s', 'ok',      '12/12'],
    ['2026-05-03 11:00:02', 'full',   '14m 02s','ok',      '12/12'],
    ['2026-05-03 09:00:01', 'scouts', '3m 18s', 'partial', '11/12'],
    ['2026-05-03 06:00:00', 'rebuild','22m 40s','ok',      '12/12'],
    ['2026-05-02 22:00:00', 'theses', '7m 11s', 'ok',      '12/12'],
    ['2026-05-02 18:30:33', 'full',   '13m 51s','failed',  '4/12'],
    ['2026-05-02 14:00:00', 'theses', '6m 50s', 'ok',      '12/12'],
  ];
  return (
    <div className="wf" style={{ width: 1180, minHeight: 760 }}>
      <TopChrome />
      <div style={{ padding: 16 }}>
        <div className="wf-h2" style={{ marginBottom: 12 }}>Pipeline logs</div>
        <div style={{ padding: '6px 12px', borderBottom: '1px solid var(--rule-faint)' }}>
          <div className="wf-eyebrow" style={{ display: 'grid', gridTemplateColumns: '180px 100px 100px 100px 100px 1fr', gap: 12 }}>
            <span>TIMESTAMP</span><span>MODE</span><span>DURATION</span><span>STATUS</span><span>RESULT</span><span>STAGES</span>
          </div>
        </div>
        {runs.map((r, i) => (
          <div key={i} style={{
            padding: '8px 12px', borderBottom: '1px solid var(--rule-faint)',
            display: 'grid', gridTemplateColumns: '180px 100px 100px 100px 100px 1fr', gap: 12,
            fontSize: 11, fontFamily: 'var(--mono)', alignItems: 'center'
          }}>
            <span>{r[0]}</span>
            <span><Chip>{r[1]}</Chip></span>
            <span>{r[2]}</span>
            <span style={{
              color: r[3] === 'ok' ? 'var(--pos)' : r[3] === 'partial' ? 'var(--conv-med)' : 'var(--neg)'
            }}>● {r[3]}</span>
            <span>{r[4]}</span>
            <span style={{ display: 'flex', gap: 2 }}>
              {['fund','news','file','ins','cat','quant','soc','disc','moat'].map((s, j) => {
                const ok = !(r[3] !== 'ok' && j > 4);
                return <span key={s} className="wf-tiny" style={{
                  padding: '1px 4px', background: ok ? 'var(--conv-high-bg)' : 'var(--conv-broken-bg)',
                  color: ok ? 'var(--conv-high)' : 'var(--conv-broken)',
                  border: `1px solid ${ok ? 'var(--conv-high)' : 'var(--conv-broken)'}`,
                  borderRadius: 2, fontSize: 9
                }}>{s}</span>;
              })}
            </span>
          </div>
        ))}
      </div>
      <div style={{ position: 'absolute', right: 24, top: 80, width: 200 }}>
        <div className="wf-postit">logs — chronological. per-stage status as inline pills, not a separate drilldown.</div>
      </div>
    </div>
  );
};

// ────────────────────────────────────────────────────────────
// Model picker
// ────────────────────────────────────────────────────────────
const ModelPickerA = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <div style={{ padding: 16 }}>
      <div className="wf-h2" style={{ marginBottom: 12 }}>Models · workbook picker</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {TICKERS.slice(0, 12).map(row => (
          <div key={row.t} className="wf-rough-soft" style={{ padding: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className="wf-mono" style={{ fontSize: 16, fontWeight: 600 }}>{row.t}</span>
              <Conv tier={row.conv} />
            </div>
            <div className="wf-tiny" style={{ marginTop: 2 }}>{row.n}</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 10 }}>
              <div>
                <div className="wf-eyebrow">CURRENT</div>
                <div className="wf-mono" style={{ fontSize: 13 }}><Money v={row.px} ccy={row.ccy} /></div>
              </div>
              <div>
                <div className="wf-eyebrow">DCF BASE</div>
                <div className="wf-mono" style={{ fontSize: 13, color: 'var(--ink-2)' }}>
                  <Money v={row.tgt * 0.7} ccy={row.ccy} />
                </div>
              </div>
            </div>
            <button className="wf-btn" style={{ width: '100%', marginTop: 10 }}>open workbook →</button>
          </div>
        ))}
      </div>
    </div>
    <div style={{ position: 'absolute', right: 24, top: 80, width: 200 }}>
      <div className="wf-postit">picker — light grid, just enough to launch. card lists DCF base only (thesis lives in detail).</div>
    </div>
  </div>
);

Object.assign(window, { ComponentSheet, DiscoveryA, AskA, LogsA, ModelPickerA });
