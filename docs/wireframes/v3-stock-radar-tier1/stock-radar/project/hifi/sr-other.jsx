/* hifi/sr-other.jsx — Components sheet + lighter views */

const { useState: oUseState } = React;

/* ============= COMPONENT SHEET ============= */
function ComponentSheet() {
  return (
    <div className="sr sr-artboard" style={{ padding: 28, overflow: 'auto' }}>
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.015em' }}>Components</h1>
        <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 4 }}>Production atoms — every state, every size.</p>
      </div>

      <CSGroup label="ConvictionBadge">
        <Row label="Sizes (md)">
          <ConvictionBadge level="strong"/>
          <ConvictionBadge level="good"/>
          <ConvictionBadge level="watch"/>
          <ConvictionBadge level="fade"/>
          <ConvictionBadge level="broken"/>
        </Row>
        <Row label="xs"><ConvictionBadge level="strong" size="xs"/><ConvictionBadge level="good" size="xs"/><ConvictionBadge level="watch" size="xs"/><ConvictionBadge level="fade" size="xs"/><ConvictionBadge level="broken" size="xs"/></Row>
        <Row label="lg"><ConvictionBadge level="strong" size="lg"/><ConvictionBadge level="watch" size="lg"/><ConvictionBadge level="broken" size="lg"/></Row>
      </CSGroup>

      <CSGroup label="MoneyValue · PctValue">
        <Row label="Money">
          <MoneyValue value={1180} size={22} weight={600}/>
          <MoneyValue value={122.40} size={16} weight={500}/>
          <MoneyValue value={-3.18} size={13} color="var(--neg)"/>
          <MoneyValue value={61234567} size={13} weight={500} prefix="MCAP "/>
        </Row>
        <Row label="Pct">
          <PctValue value={+1.74}/>
          <PctValue value={-2.53}/>
          <PctValue value={+79.7}/>
          <PctValue value={0.0}/>
        </Row>
      </CSGroup>

      <CSGroup label="RunButton · 6 states">
        <Row><RunButton state="idle"/><RunButton state="queued"/><RunButton state="running"/><RunButton state="done" lastRun="4h ago"/><RunButton state="error"/><RunButton state="stale"/></Row>
        <Row label="sm"><RunButton state="idle" size="sm"/><RunButton state="running" size="sm"/><RunButton state="error" size="sm"/></Row>
      </CSGroup>

      <CSGroup label="ViewToggle · StatePill">
        <Row><ViewToggleDemo/></Row>
        <Row label="Pills"><StatePill tone="ok">all synced</StatePill><StatePill tone="info">running</StatePill><StatePill tone="warn">stale</StatePill><StatePill tone="err">failed</StatePill><StatePill tone="mute">12 tickers</StatePill></Row>
      </CSGroup>

      <CSGroup label="Sparkline">
        <Row>
          <Sparkline data={[120,124,128,132,130,135,140,144]} width={100} height={28}/>
          <Sparkline data={[80,78,75,72,73,70,68,65]} width={100} height={28} fill/>
          <Sparkline data={[50,52,49,51,50,52,51,50]} width={100} height={28}/>
        </Row>
      </CSGroup>

      <CSGroup label="DriftChip">
        <Row>
          <DriftChip thesis={220} dcf={165} current={122}/>
          <DriftChip thesis={165} dcf={195} current={138}/>
          <DriftChip thesis={170} dcf={167} current={150}/>
        </Row>
      </CSGroup>

      <CSGroup label="NoteEditor">
        <div style={{ maxWidth: 520, padding: 12, background: 'var(--paper-1)', border: '1px solid var(--rule)', borderRadius: 6 }}>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Add note · CRWD</div>
          <textarea defaultValue="Sized up to 4% — net-new ARR re-acceleration confirmed at fal.con keynote." style={{
            width: '100%', minHeight: 64, padding: 8, border: '1px solid var(--rule)', background: 'var(--paper)',
            borderRadius: 4, fontSize: 12.5, fontFamily: 'inherit', color: 'var(--ink)', resize: 'vertical',
          }}/>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 4 }}>
              <button style={iconBtnSm2}><Icon name="bell" size={12} color="var(--ink-2)"/></button>
              <button style={iconBtnSm2}><Icon name="link" size={12} color="var(--ink-2)"/></button>
              <button style={iconBtnSm2}><Icon name="star" size={12} color="var(--ink-2)"/></button>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button style={ghostBtnO}>Cancel</button>
              <button style={primaryBtnO}>Save note</button>
            </div>
          </div>
        </div>
      </CSGroup>

      <CSGroup label="Icons">
        <Row>
          {['search','plus','star','bolt','list','grid','ladder','chevD','chevR','chevL','arrowUp','arrowDn','dots','bell','edit','refresh','filter','setting','play','note','user','link','zap','target','eye'].map(n =>
            <div key={n} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, width: 50 }}>
              <Icon name={n} size={16} color="var(--ink-1)"/>
              <span style={{ fontSize: 9.5, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{n}</span>
            </div>
          )}
        </Row>
      </CSGroup>
    </div>
  );
}

function ViewToggleDemo() {
  const [v, sv] = oUseState('list');
  return <ViewToggle value={v} onChange={sv} options={[
    { value: 'list', label: 'List', icon: <Icon name="list" size={12}/> },
    { value: 'grid', label: 'Grid', icon: <Icon name="grid" size={12}/> },
    { value: 'ladder', label: 'Ladder', icon: <Icon name="ladder" size={12}/> },
  ]}/>;
}

function CSGroup({ label, children }) {
  return (
    <section style={{ marginBottom: 22, paddingBottom: 18, borderBottom: '1px solid var(--rule-soft)' }}>
      <div className="eyebrow" style={{ marginBottom: 12 }}>{label}</div>
      {children}
    </section>
  );
}
function Row({ label, children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', flexWrap: 'wrap' }}>
      {label && <span style={{ width: 60, fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{label}</span>}
      {children}
    </div>
  );
}
const iconBtnSm2 = { width: 24, height: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'transparent', border: 'none', borderRadius: 4, cursor: 'pointer' };
const ghostBtnO = { display: 'inline-flex', alignItems: 'center', gap: 5, height: 26, padding: '0 10px', background: 'var(--paper-1)', border: '1px solid var(--rule)', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: 'var(--ink-1)' };
const primaryBtnO = { display: 'inline-flex', alignItems: 'center', gap: 5, height: 26, padding: '0 11px', background: 'var(--action)', color: 'var(--action-ink)', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12, fontWeight: 500 };

/* ============= DISCOVERY ============= */
function DiscoveryArtboard() {
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '14px 22px', borderBottom: '1px solid var(--rule)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ fontSize: 18, fontWeight: 600 }}>Discovery</h1>
        <StatePill tone="info" size="sm">14 candidates · last 24h</StatePill>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: 18, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
        {[
          { tk: 'AVGO', why: 'Hyperscaler ASIC TAM up 28% in Q', src: 'transcript scout · 2h ago', conv: 'good' },
          { tk: 'NET',  why: 'Workers AI usage inflecting', src: 'usage data · 4h ago', conv: 'watch' },
          { tk: 'DDOG', why: 'Logging margins compressing', src: 'cohort scout · 6h ago', conv: 'fade' },
          { tk: 'ANET', why: '800G shipments accelerating', src: 'supplier scout · 1d ago', conv: 'good' },
          { tk: 'TEAM', why: 'Cloud ARR mix flips >70%', src: 'transcript scout · 1d ago', conv: 'watch' },
          { tk: 'ZS',   why: 'Rev guidance reset risk', src: 'channel scout · 2d ago', conv: 'fade' },
        ].map(c => (
          <div key={c.tk} style={{ background: 'var(--paper-1)', border: '1px solid var(--rule)', borderRadius: 6, padding: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600 }}>{c.tk}</span>
              <ConvictionBadge level={c.conv} size="xs"/>
            </div>
            <p style={{ fontSize: 13, color: 'var(--ink-1)', marginBottom: 8 }}>{c.why}</p>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{c.src}</span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button style={ghostBtnO}>Dismiss</button>
                <button style={primaryBtnO}>Add to watch</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ============= ASK AI ============= */
function AskArtboard() {
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '14px 22px', borderBottom: '1px solid var(--rule)' }}>
        <h1 style={{ fontSize: 18, fontWeight: 600 }}>Ask</h1>
        <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2 }}>Query your watchlist, theses, memory, and runs.</p>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: 22, display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 820, width: '100%', margin: '0 auto' }}>
        <div style={{ alignSelf: 'flex-end', maxWidth: 540, padding: 12, background: 'var(--paper-2)', borderRadius: 8, fontSize: 13.5 }}>Which of my STRONG conviction tickers has the largest gap between thesis target and DCF base?</div>
        <div style={{ alignSelf: 'flex-start', maxWidth: 620, padding: 14, background: 'var(--paper-1)', border: '1px solid var(--rule-soft)', borderRadius: 8, fontSize: 13.5, lineHeight: 1.55, color: 'var(--ink-1)' }}>
          <p style={{ marginBottom: 8 }}>Of your 2 STRONG positions, <strong>NVDA</strong> has the larger gap.</p>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', marginBottom: 8 }}>
            <thead><tr style={{ color: 'var(--ink-3)' }}><th style={{ textAlign:'left', padding: '4px 8px', borderBottom: '1px solid var(--rule)' }}>Ticker</th><th style={{ textAlign:'right', padding: '4px 8px', borderBottom: '1px solid var(--rule)' }}>Thesis</th><th style={{ textAlign:'right', padding: '4px 8px', borderBottom: '1px solid var(--rule)' }}>DCF</th><th style={{ textAlign:'right', padding: '4px 8px', borderBottom: '1px solid var(--rule)' }}>Drift</th></tr></thead>
            <tbody>
              <tr><td style={{ padding: '4px 8px', fontFamily: 'var(--font-mono)' }}>NVDA</td><td style={{ padding: '4px 8px', textAlign:'right', fontFamily: 'var(--font-mono)' }}>$1,180</td><td style={{ padding: '4px 8px', textAlign:'right', color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontStyle: 'italic' }}>$920</td><td style={{ padding: '4px 8px', textAlign:'right', color: 'var(--pos)', fontFamily: 'var(--font-mono)' }}>+28.3%</td></tr>
              <tr><td style={{ padding: '4px 8px', fontFamily: 'var(--font-mono)' }}>CRWD</td><td style={{ padding: '4px 8px', textAlign:'right', fontFamily: 'var(--font-mono)' }}>$220</td><td style={{ padding: '4px 8px', textAlign:'right', color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontStyle: 'italic' }}>$165</td><td style={{ padding: '4px 8px', textAlign:'right', color: 'var(--pos)', fontFamily: 'var(--font-mono)' }}>+33.3%</td></tr>
            </tbody>
          </table>
          <p style={{ fontSize: 12, color: 'var(--ink-2)' }}>Both gaps are well above the 5% drift threshold; NVDA's thesis assumes data-center capex sustains while DCF prices a normal cycle.</p>
          <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
            <button style={ghostBtnO}>Open NVDA</button>
            <button style={ghostBtnO}>Open CRWD</button>
          </div>
        </div>
        <div style={{ marginTop: 'auto', display: 'flex', gap: 8, padding: 12, background: 'var(--paper-1)', border: '1px solid var(--rule)', borderRadius: 8 }}>
          <input placeholder="Ask anything about your workspace…" style={{ flex: 1, border: 'none', background: 'transparent', fontSize: 13.5, fontFamily: 'inherit', color: 'var(--ink)', outline: 'none' }}/>
          <button style={primaryBtnO}><Icon name="zap" size={12} color="var(--action-ink)"/>Ask</button>
        </div>
      </div>
    </div>
  );
}

/* ============= LOGS ============= */
function LogsArtboard() {
  const rows = [
    { t: '16:42:18', tk: 'CRWD', mod: 'thesis-v3.2', dur: '74s',  st: 'ok' },
    { t: '16:38:02', tk: 'NVDA', mod: 'thesis-v3.2', dur: '62s',  st: 'ok' },
    { t: '16:31:45', tk: 'AMD',  mod: 'thesis-v3.2', dur: '38s',  st: 'err', err: 'urllib3.MaxRetryError on api.polygon.io' },
    { t: '16:14:09', tk: 'PLTR', mod: 'thesis-v3.2', dur: '81s',  st: 'ok' },
    { t: '15:58:33', tk: 'META', mod: 'thesis-v3.2', dur: '69s',  st: 'ok' },
    { t: '15:47:11', tk: 'PYPL', mod: 'thesis-v3.2', dur: '124s', st: 'warn', err: 'partial: hume notes timed out' },
    { t: '15:30:00', tk: 'SHOP', mod: 'thesis-v3.2', dur: '57s',  st: 'ok' },
    { t: '15:12:24', tk: 'ROKU', mod: 'thesis-v3.2', dur: '63s',  st: 'ok' },
    { t: '14:55:48', tk: 'ENPH', mod: 'thesis-v3.2', dur: '0s',   st: 'err', err: 'pre-flight: ticker not in active universe' },
  ];
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '14px 22px', borderBottom: '1px solid var(--rule)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ fontSize: 18, fontWeight: 600 }}>Logs</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <StatePill tone="ok" size="sm">142 ok</StatePill>
          <StatePill tone="warn" size="sm">3 partial</StatePill>
          <StatePill tone="err" size="sm">2 failed</StatePill>
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)' }}>
          <thead>
            <tr style={{ background: 'var(--paper-1)', borderBottom: '1px solid var(--rule)' }}>
              {['TIME','TICKER','MODEL','DUR','STATUS','MESSAGE',''].map(h =>
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: 9.5, letterSpacing: '0.1em', color: 'var(--ink-3)', fontWeight: 500 }}>{h}</th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--rule-soft)', height: 30 }}>
                <td style={{ padding: '0 12px', fontSize: 11.5, color: 'var(--ink-2)' }}>{r.t}</td>
                <td style={{ padding: '0 12px', fontSize: 12, fontWeight: 600, color: 'var(--ink)' }}>{r.tk}</td>
                <td style={{ padding: '0 12px', fontSize: 11.5, color: 'var(--ink-2)' }}>{r.mod}</td>
                <td style={{ padding: '0 12px', fontSize: 11.5, color: 'var(--ink-2)' }}>{r.dur}</td>
                <td style={{ padding: '0 12px' }}>
                  {r.st === 'ok'   && <StatePill tone="ok" size="sm">ok</StatePill>}
                  {r.st === 'warn' && <StatePill tone="warn" size="sm">partial</StatePill>}
                  {r.st === 'err'  && <StatePill tone="err" size="sm">failed</StatePill>}
                </td>
                <td style={{ padding: '0 12px', fontSize: 11.5, color: r.st === 'err' ? 'var(--err-ink)' : 'var(--ink-2)' }}>{r.err || '—'}</td>
                <td style={{ padding: '0 12px', textAlign: 'right' }}><button style={iconBtnSm2}><Icon name="chevR" size={12} color="var(--ink-3)"/></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ============= MODEL PICKER ============= */
function PickerArtboard() {
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '14px 22px', borderBottom: '1px solid var(--rule)' }}>
        <h1 style={{ fontSize: 18, fontWeight: 600 }}>Models</h1>
        <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2 }}>Pick the model used for runs across watchlist + detail.</p>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: 18, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
        {[
          { n: 'equity-thesis-v3.2', d: 'Thesis-first. DCF as floor input only.', cur: true, lat: '74s', acc: '2.1% fail', author: 'core' },
          { n: 'equity-thesis-v3.1', d: 'Previous version. Slightly slower, similar accuracy.', lat: '83s', acc: '2.4% fail', author: 'core' },
          { n: 'small-cap-deep',     d: 'Deeper transcripts; longer runs. For sub-$5B mcap.', lat: '162s', acc: '4.0% fail', author: 'core' },
          { n: 'macro-overlay-v1',   d: 'Adjusts conviction by macro regime detection.', lat: '94s', acc: '3.1% fail', author: 'rmacaulay', beta: true },
        ].map(m => (
          <div key={m.n} style={{
            background: m.cur ? 'var(--paper)' : 'var(--paper-1)',
            border: m.cur ? '2px solid var(--ink)' : '1px solid var(--rule)',
            borderRadius: 6, padding: 16,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13.5, fontWeight: 600 }}>{m.n}</span>
              <div style={{ display: 'flex', gap: 6 }}>
                {m.cur && <StatePill tone="ok" size="sm">active</StatePill>}
                {m.beta && <StatePill tone="info" size="sm">beta</StatePill>}
              </div>
            </div>
            <p style={{ fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 10 }}>{m.d}</p>
            <div style={{ display: 'flex', gap: 14, fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>
              <span>avg {m.lat}</span>
              <span>{m.acc}</span>
              <span>by @{m.author}</span>
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
              {!m.cur && <button style={primaryBtnO}>Set as active</button>}
              <button style={ghostBtnO}>Open</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

window.ComponentSheet = ComponentSheet;
window.DiscoveryArtboard = DiscoveryArtboard;
window.AskArtboard = AskArtboard;
window.LogsArtboard = LogsArtboard;
window.PickerArtboard = PickerArtboard;
