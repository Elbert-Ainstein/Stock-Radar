/* hifi/sr-detail.jsx — Stock detail page (full-page route)
   Responsive: desktop, tablet, phone
   States: happy, empty (no thesis run), loading, error, stale */

const { useState: dtUseState } = React;

function StockDetailArtboard({ breakpoint = 'desktop', state = 'happy', ticker = 'CRWD' }) {
  const t = SR_TICKERS.find(x => x.ticker === ticker) || SR_TICKERS[1];
  if (breakpoint === 'phone') return <DetailPhone t={t} state={state} />;
  if (breakpoint === 'tablet') return <DetailTablet t={t} state={state} />;
  return <DetailDesktop t={t} state={state} />;
}

/* ===================== DESKTOP ===================== */
function DetailDesktop({ t, state }) {
  const upside = ((t.thesis - t.price) / t.price) * 100;
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DetailHeader t={t} state={state} />
      <div style={{ flex: 1, overflow: 'auto', display: 'grid', gridTemplateColumns: '1fr 360px', gap: 0, minHeight: 0 }}>
        {/* Main column */}
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16, borderRight: '1px solid var(--rule-soft)' }}>
          {state === 'empty' ? <ThesisEmpty t={t} />
            : state === 'loading' ? <ThesisLoading t={t} />
            : state === 'error' ? <ThesisError t={t} />
            : <ThesisCard t={t} stale={state === 'stale'} />}
          {state !== 'empty' && state !== 'loading' && state !== 'error' && <PriceLadder t={t} />}
          {state !== 'empty' && state !== 'loading' && state !== 'error' && <SetupRisksCatalysts t={t} />}
        </div>
        {/* Side column */}
        <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14, background: 'var(--paper-1)' }}>
          {state !== 'empty' && state !== 'loading' && state !== 'error' && <FloorTile t={t} />}
          <MemoryNotes t={t} state={state} />
          <ScoutsList t={t} />
        </div>
      </div>
    </div>
  );
}

function DetailHeader({ t, state }) {
  const upside = ((t.thesis - t.price) / t.price) * 100;
  return (
    <div style={{ borderBottom: '1px solid var(--rule)', background: 'var(--paper)', padding: '12px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: 'var(--ink-3)' }}>
          <a style={{ color: 'var(--ink-3)', textDecoration: 'none', cursor: 'pointer' }}>← Watchlist</a>
          <span>/</span>
          <span style={{ color: 'var(--ink-2)' }}>{t.ticker}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button style={ghostBtn2}><Icon name="star" size={12} color="var(--ink-2)"/></button>
          <button style={ghostBtn2}><Icon name="link" size={12} color="var(--ink-2)"/>Share</button>
          <RunButton state={state === 'loading' ? 'running' : state === 'error' ? 'error' : state === 'stale' ? 'stale' : 'done'} size="md" lastRun={state === 'stale' ? '3d ago' : state === 'happy' ? '4h ago' : null} />
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 10, gap: 24 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
              <h1 style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', fontFamily: 'var(--font-mono)' }}>{t.ticker}</h1>
              <span style={{ fontSize: 14, color: 'var(--ink-2)' }}>{t.name}</span>
              <ConvictionBadge level={t.conv} size="sm" />
            </div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', marginTop: 6 }}>
              <MoneyValue value={t.price} size={28} weight={600} />
              <span className="num mono" style={{ fontSize: 14, color: t.chg > 0 ? 'var(--pos)' : 'var(--neg)' }}>{t.chg > 0 ? '+' : '−'}{Math.abs(t.chg).toFixed(2)}</span>
              <PctValue value={t.chgPct} size={14} weight={500} />
              <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', marginLeft: 4 }}>NASDAQ · 16:00 ET</span>
            </div>
          </div>
        </div>
        {/* Tab strip */}
        <nav style={{ display: 'flex', gap: 0, borderBottom: 'none', alignSelf: 'flex-end' }}>
          {['Overview','Thesis','Floor','Memory','Scouts','Activity'].map((n,i) => (
            <a key={n} style={{
              padding: '8px 14px', fontSize: 12.5,
              color: i===0 ? 'var(--ink)' : 'var(--ink-2)',
              fontWeight: i===0 ? 600 : 500,
              borderBottom: i===0 ? '2px solid var(--ink)' : '2px solid transparent',
              cursor: 'pointer',
            }}>{n}</a>
          ))}
        </nav>
      </div>
    </div>
  );
}

/* ----- Thesis card (happy) ----- */
function ThesisCard({ t, stale }) {
  const upside = ((t.thesis - t.price) / t.price) * 100;
  return (
    <section style={surfaceStyle}>
      <SectionHeader eyebrow="Thesis · headline" right={stale ? <StatePill tone="warn" size="sm">last run 3d ago</StatePill> : <StatePill tone="ok" size="sm">fresh · 4h</StatePill>}>
        Demand-led re-rating into FY26 guide
      </SectionHeader>
      <div style={{ padding: '14px 18px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <p style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--ink-1)', maxWidth: 640 }}>
          Endpoint+identity attach is accelerating; module count per customer continues to compound (4.7 → 5.4 LTM). Net-new ARR re-accelerates if Q3 lands; comps reset post-July outage; valuation reflects fear, not numbers.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          <KV label="Thesis target" value={<MoneyValue value={t.thesis} size={18} weight={600} />} sub={<PctValue value={upside} size={12} />} hi />
          <KV label="Conviction" value={<ConvictionBadge level={t.conv} size="md" />} sub={<span style={{fontSize: 11, color: 'var(--ink-3)'}}>up from GOOD · 8d ago</span>} />
          <KV label="Horizon" value={<span className="num mono" style={{ fontSize: 18, fontWeight: 600 }}>9–14 mo</span>} sub={<span style={{fontSize: 11, color: 'var(--ink-3)'}}>through Q2 FY26</span>} />
          <KV label="Kill level" value={<MoneyValue value={88} size={18} weight={600} color="var(--conv-broken)" />} sub={<span style={{fontSize: 11, color: 'var(--conv-broken)'}}>−28% from current</span>} />
        </div>
      </div>
    </section>
  );
}

function ThesisEmpty({ t }) {
  return (
    <section style={{ ...surfaceStyle, borderStyle: 'dashed', borderColor: 'var(--rule-strong)' }}>
      <div style={{ padding: '32px 20px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
        <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--paper-2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon name="target" size={22} color="var(--ink-3)"/>
        </div>
        <div>
          <h3 style={{ fontSize: 16, marginBottom: 4 }}>No thesis run yet for {t.ticker}</h3>
          <p style={{ fontSize: 13, color: 'var(--ink-3)', maxWidth: 380 }}>Run the model to generate a thesis, conviction level, kill level, and floor. Typically takes 60–120 seconds.</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <RunButton state="idle" size="md" />
          <button style={ghostBtn2}>Choose model</button>
        </div>
      </div>
    </section>
  );
}

function ThesisLoading({ t }) {
  return (
    <section style={surfaceStyle}>
      <SectionHeader eyebrow="Thesis · running" right={<StatePill tone="info" size="sm"><span style={{display:'inline-flex', gap:4, alignItems:'center'}}><span style={{width:5,height:5,borderRadius:'50%',background:'currentColor',animation:'sr-pulse 1.2s infinite'}}/>47s elapsed</span></StatePill>}>
        <span className="sr-skel" style={{ height: 18, width: 320 }}/>
      </SectionHeader>
      <div style={{ padding: '14px 18px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="sr-skel" style={{ height: 11, width: '95%' }}/>
          <span className="sr-skel" style={{ height: 11, width: '88%' }}/>
          <span className="sr-skel" style={{ height: 11, width: '72%' }}/>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {[0,1,2,3].map(i => (
            <div key={i} style={{ padding: 12, background: 'var(--paper-2)', borderRadius: 5 }}>
              <span className="sr-skel" style={{ height: 9, width: 60, marginBottom: 8 }}/>
              <br/>
              <span className="sr-skel" style={{ height: 18, width: 80 }}/>
            </div>
          ))}
        </div>
        <div style={{ background: 'var(--paper-2)', border: '1px solid var(--rule-soft)', borderRadius: 4, padding: 10, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-2)', maxHeight: 84, overflow: 'hidden' }}>
          <div style={{ color: 'var(--ink-3)' }}>[00:00] queueing thesis run · model: equity-thesis-v3.2</div>
          <div>[00:08] fetched 12mo fundamentals · 247 datapoints</div>
          <div>[00:23] running comparable cohort · 8 peers</div>
          <div>[00:34] DCF base case · WACC 9.2% · g 3.0%</div>
          <div style={{ color: 'var(--ink-1)' }}>[00:47] reasoning over recent transcripts<span style={{ animation: 'sr-pulse 1s infinite' }}>…</span></div>
        </div>
      </div>
    </section>
  );
}

function ThesisError({ t }) {
  return (
    <section style={{ ...surfaceStyle, borderColor: 'var(--err-ink)' }}>
      <SectionHeader eyebrow="Thesis · failed" right={<StatePill tone="err" size="sm">subprocess exit 1</StatePill>}>
        Run failed at fundamentals fetch
      </SectionHeader>
      <div style={{ padding: '14px 18px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <p style={{ fontSize: 13, color: 'var(--ink-1)' }}>
          The Python subprocess exited with code 1 after 38s. The model couldn't be loaded; everything else (memory, scouts, prior thesis) is unaffected.
        </p>
        <div style={{ background: 'var(--paper-2)', border: '1px solid var(--rule-soft)', borderRadius: 4, padding: 10, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-1)' }}>
          <div style={{ color: 'var(--ink-3)' }}>$ python -m radar.thesis run CRWD</div>
          <div>[00:00] queueing thesis run</div>
          <div>[00:08] fetching fundamentals from polygon…</div>
          <div style={{ color: 'var(--err-ink)' }}>[00:38] urllib3.exceptions.MaxRetryError: HTTPSConnectionPool(host='api.polygon.io', port=443)</div>
          <div style={{ color: 'var(--err-ink)' }}>      Caused by: ConnectTimeoutError(&lt;urllib3.connection.HTTPSConnection&gt;)</div>
          <div style={{ color: 'var(--ink-3)' }}>process exited with code 1</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <RunButton state="error" size="md" label="Retry" />
          <button style={ghostBtn2}>Open full log</button>
          <button style={ghostBtn2}>Use last good thesis (4h ago)</button>
        </div>
      </div>
    </section>
  );
}

/* ----- Price ladder ----- */
function PriceLadder({ t }) {
  const upside = ((t.thesis - t.price) / t.price) * 100;
  return (
    <section style={surfaceStyle}>
      <SectionHeader eyebrow="Price ladder · USD" right={<span className="num mono" style={{ fontSize: 11, color: 'var(--pos)', fontWeight: 600 }}>conviction band · +{upside.toFixed(1)}%</span>}>
        Where price sits in the thesis
      </SectionHeader>
      <div style={{ padding: '20px 24px 24px' }}>
        <div style={{ position: 'relative', height: 90, padding: '0 8px' }}>
          <div style={{ position: 'absolute', left: 8, right: 8, top: 44, borderTop: '1.5px solid var(--rule-strong)' }} />
          {(() => {
            const min = 70, max = 260;
            const x = v => `calc(8px + ${((v-min)/(max-min)) * 100}% - ${((v-min)/(max-min)) * 16}px)`;
            const marks = [
              { v: 88,    lbl: 'KILL',     col: 'var(--conv-broken)', side: 'b', big: false, row: 0 },
              { v: 100,   lbl: 'BUY',      col: 'var(--ink-2)',       side: 't', big: false, row: 0 },
              { v: t.price, lbl: 'CURRENT', col: 'var(--ink)',        side: 'b', big: true,  row: 0 },
              { v: t.dcf, lbl: 'DCF BASE', col: 'var(--ink-3)',       side: 't', big: false, row: 0 },
              { v: 195,   lbl: 'RISK-ADJ', col: 'var(--ink-3)',       side: 'b', big: false, row: 1 },
              { v: t.thesis, lbl: 'THESIS', col: 'var(--conv-strong)', side: 't', big: true,  row: 0 },
              { v: 245,   lbl: 'TRIM',     col: 'var(--ink-2)',       side: 'b', big: false, row: 0 },
            ];
            return (
              <>
                <div style={{ position: 'absolute', left: x(t.price), right: `calc(100% - ${x(t.thesis)})`, top: 38, height: 12, background: 'var(--conv-strong-bg)', border: '1px solid var(--conv-strong)', opacity: 0.7 }}/>
                {marks.map((m, i) => {
                  const tickTop = m.big ? 32 : 38;
                  const tickH = m.big ? 24 : 12;
                  const offset = m.row === 1 ? 18 : 0;
                  const labelTop = m.side === 't' ? -8 - offset : 58 + offset;
                  return (
                    <React.Fragment key={i}>
                      <div style={{ position: 'absolute', left: x(m.v), top: tickTop, height: tickH, borderLeft: `${m.big ? 2 : 1.25}px solid ${m.col}` }}/>
                      {m.row === 1 && (
                        <div style={{ position: 'absolute', left: x(m.v), top: m.side === 't' ? labelTop + 18 : tickTop + tickH, height: m.side === 't' ? tickTop - (labelTop + 18) : labelTop - (tickTop + tickH), borderLeft: '1px dashed var(--rule)' }}/>
                      )}
                      <div style={{ position: 'absolute', left: x(m.v), top: labelTop, transform: 'translateX(calc(-50% + 8px))', textAlign: 'center', whiteSpace: 'nowrap' }}>
                        <div className="eyebrow" style={{ color: m.col, fontSize: m.big ? 9.5 : 8.5, fontWeight: m.big ? 700 : 500, marginBottom: 1 }}>{m.lbl}</div>
                        <div className="num mono" style={{ fontSize: m.big ? 13 : 10.5, fontWeight: m.big ? 700 : 500, color: m.col, lineHeight: 1.05 }}>${m.v.toFixed(0)}</div>
                      </div>
                    </React.Fragment>
                  );
                })}
              </>
            );
          })()}
        </div>
      </div>
    </section>
  );
}

/* ----- Setup / Risks / Catalysts ----- */
function SetupRisksCatalysts({ t }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
      <SRCBox eyebrow="Setup" items={[
        'Module attach: 4.7 → 5.4 LTM',
        'Net-new ARR re-accelerating (est. Q3)',
        'Identity becoming primary entry SKU',
      ]}/>
      <SRCBox eyebrow="Risks" tone="warn" items={[
        'July outage residual brand impact',
        'SentinelOne pricing aggression',
        'Macro: SMB consolidation',
      ]}/>
      <SRCBox eyebrow="Catalysts" tone="ok" items={[
        'Q3 print · Dec 2',
        'fal.con keynote · Sep 16',
        'Q2 net-new ARR re-accel watch',
      ]}/>
    </div>
  );
}

function SRCBox({ eyebrow, items, tone = 'mute' }) {
  const dot = tone === 'warn' ? 'var(--conv-fade)' : tone === 'ok' ? 'var(--conv-strong)' : 'var(--ink-3)';
  return (
    <div style={{ ...surfaceStyle, padding: '12px 14px' }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>{eyebrow}</div>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map((it, i) => (
          <li key={i} style={{ display: 'flex', gap: 8, fontSize: 12.5, color: 'var(--ink-1)', lineHeight: 1.45 }}>
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: dot, marginTop: 7, flex: '0 0 auto' }}/>
            {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ----- Floor (DCF) tile in side column — visibly secondary ----- */
function FloorTile({ t }) {
  return (
    <section style={{ ...surfaceStyle, borderStyle: 'dashed', background: 'var(--paper)', opacity: 0.92 }}>
      <SectionHeader eyebrow="Floor · DCF · secondary" small>
        <span style={{ color: 'var(--ink-2)' }}>Mechanical estimate</span>
      </SectionHeader>
      <div style={{ padding: '12px 16px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Base</span>
          <MoneyValue value={t.dcf} size={16} weight={500} color="var(--ink-2)" />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Bull</span>
          <span className="num mono" style={{ fontSize: 12, color: 'var(--ink-3)' }}>${(t.dcf * 1.18).toFixed(0)}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Bear</span>
          <span className="num mono" style={{ fontSize: 12, color: 'var(--ink-3)' }}>${(t.dcf * 0.78).toFixed(0)}</span>
        </div>
        <div style={{ paddingTop: 8, borderTop: '1px solid var(--rule-soft)' }}>
          <DriftChip thesis={t.thesis} dcf={t.dcf} current={t.price} size="sm" />
        </div>
        <a style={{ fontSize: 11.5, color: 'var(--link)', cursor: 'pointer' }}>Open full DCF →</a>
      </div>
    </section>
  );
}

/* ----- Memory / notes ----- */
function MemoryNotes({ t, state }) {
  return (
    <section style={surfaceStyle}>
      <SectionHeader eyebrow="Memory" small right={<button style={iconBtnSm}><Icon name="edit" size={11} color="var(--ink-3)"/></button>}>
        Notes & past decisions
      </SectionHeader>
      <div style={{ padding: '10px 14px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[
          { d: 'Apr 14', h: 'Sized up to 4%', b: 'Conviction moved STRONG after Q1 attach numbers; trim above $245.' },
          { d: 'Mar 02', h: 'Initial thesis', b: 'Demand-led re-rate setup; horizon Q2 FY26.' },
          { d: 'Feb 11', h: 'Watch added', b: 'Triggered on identity SKU expansion in 10-K.' },
        ].map((n, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12 }}>
            <span style={{ flex: '0 0 50px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-3)', paddingTop: 2 }}>{n.d}</span>
            <div>
              <div style={{ fontWeight: 600, color: 'var(--ink-1)', marginBottom: 1 }}>{n.h}</div>
              <div style={{ color: 'var(--ink-2)', lineHeight: 1.4 }}>{n.b}</div>
            </div>
          </div>
        ))}
        <div style={{ paddingTop: 8, borderTop: '1px solid var(--rule-soft)', display: 'flex', gap: 6 }}>
          <input placeholder="Add a note…" style={{
            flex: 1, padding: '6px 8px', border: '1px solid var(--rule)', background: 'var(--paper)',
            borderRadius: 4, fontSize: 12, fontFamily: 'inherit', color: 'var(--ink)',
          }}/>
          <button style={{ ...ghostBtn2, height: 28 }}>Save</button>
        </div>
      </div>
    </section>
  );
}

/* ----- Scouts list ----- */
function ScoutsList({ t }) {
  const scouts = [
    { name: 'Q3 print',         st: 'armed',    when: 'Dec 2',  ic: 'target' },
    { name: 'Net-new ARR',      st: 'armed',    when: 'Q2',     ic: 'target' },
    { name: 'Comp dilution',    st: 'flagged',  when: '2 days', ic: 'bell' },
    { name: 'Insider sell ≥$5M', st: 'armed',   when: 'rolling', ic: 'eye' },
    { name: 'Module attach',    st: 'fulfilled', when: '8d ago', ic: 'star' },
  ];
  return (
    <section style={surfaceStyle}>
      <SectionHeader eyebrow="Scouts" small right={<span className="eyebrow">{t.scouts} active</span>}>
        Watching for
      </SectionHeader>
      <div style={{ padding: '6px 4px' }}>
        {scouts.map((s, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '8px 12px', borderTop: i ? '1px solid var(--rule-soft)' : 'none' }}>
            <Icon name={s.ic} size={13} color={s.st === 'flagged' ? 'var(--conv-fade)' : s.st === 'fulfilled' ? 'var(--conv-strong)' : 'var(--ink-3)'} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, color: 'var(--ink-1)', fontWeight: 500 }}>{s.name}</div>
              <div style={{ fontSize: 10.5, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{s.st} · {s.when}</div>
            </div>
            <button style={iconBtnSm}><Icon name="dots" size={12} color="var(--ink-3)"/></button>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ===================== TABLET ===================== */
function DetailTablet({ t, state }) {
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DetailHeader t={t} state={state} />
      <div style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {state === 'empty' ? <ThesisEmpty t={t} />
          : state === 'loading' ? <ThesisLoading t={t} />
          : state === 'error' ? <ThesisError t={t} />
          : <ThesisCard t={t} stale={state === 'stale'} />}
        {state !== 'empty' && state !== 'loading' && state !== 'error' && <PriceLadder t={t} />}
        {state !== 'empty' && state !== 'loading' && state !== 'error' && <SetupRisksCatalysts t={t} />}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {state !== 'empty' && state !== 'loading' && state !== 'error' && <FloorTile t={t} />}
          <ScoutsList t={t} />
        </div>
        <MemoryNotes t={t} state={state} />
      </div>
    </div>
  );
}

/* ===================== PHONE ===================== */
function DetailPhone({ t, state }) {
  const upside = ((t.thesis - t.price) / t.price) * 100;
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      {/* Compact header */}
      <div style={{ padding: 12, borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', gap: 10 }}>
        <button style={iconBtnSm}><Icon name="chevL" size={14} color="var(--ink-2)"/></button>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600 }}>{t.ticker}</span>
            <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{t.name}</span>
          </div>
        </div>
        <ConvictionBadge level={t.conv} size="xs" />
        <button style={iconBtnSm}><Icon name="dots" size={14} color="var(--ink-2)"/></button>
      </div>
      {/* Price */}
      <div style={{ padding: '14px 14px 10px', borderBottom: '1px solid var(--rule-soft)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
          <div>
            <MoneyValue value={t.price} size={26} weight={600} />
            <div style={{ marginTop: 2 }}>
              <span className="num mono" style={{ fontSize: 13, color: t.chg > 0 ? 'var(--pos)' : 'var(--neg)' }}>{t.chg > 0 ? '+' : '−'}{Math.abs(t.chg).toFixed(2)}</span>
              <span style={{ marginLeft: 6 }}><PctValue value={t.chgPct} size={12} /></span>
            </div>
          </div>
          <Sparkline data={t.spark} width={90} height={36} fill />
        </div>
      </div>
      {/* Tab strip */}
      <div style={{ display: 'flex', overflowX: 'auto', borderBottom: '1px solid var(--rule)', background: 'var(--paper)' }}>
        {['Thesis','Floor','Memory','Scouts','Activity'].map((n,i) => (
          <a key={n} style={{ padding: '10px 14px', fontSize: 12.5, color: i===0 ? 'var(--ink)' : 'var(--ink-2)', fontWeight: i===0 ? 600 : 500, borderBottom: i===0 ? '2px solid var(--ink)' : '2px solid transparent', whiteSpace: 'nowrap' }}>{n}</a>
        ))}
      </div>
      {/* Body */}
      <div style={{ flex: 1, overflow: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {state === 'empty' ? <ThesisEmpty t={t} />
          : state === 'loading' ? <ThesisLoading t={t} />
          : state === 'error' ? <ThesisError t={t} />
          : (
            <>
              <section style={surfaceStyle}>
                <div style={{ padding: 14 }}>
                  <div className="eyebrow" style={{ marginBottom: 6 }}>Thesis · headline</div>
                  <h3 style={{ fontSize: 15, marginBottom: 8 }}>Demand-led re-rating into FY26</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <KV label="Target" value={<MoneyValue value={t.thesis} size={16} weight={600}/>} sub={<PctValue value={upside} size={11}/>} hi />
                    <KV label="Kill" value={<MoneyValue value={88} size={16} weight={600} color="var(--conv-broken)"/>} sub={<span style={{fontSize:10.5,color:'var(--conv-broken)'}}>−28%</span>} />
                  </div>
                </div>
              </section>
              <FloorTile t={t} />
            </>
          )}
      </div>
      {/* Phone bottom action bar */}
      <div style={{ padding: 12, borderTop: '1px solid var(--rule)', background: 'var(--paper)', display: 'flex', gap: 8, paddingBottom: 18 }}>
        <RunButton state={state === 'loading' ? 'running' : state === 'error' ? 'error' : state === 'stale' ? 'stale' : 'done'} size="md" lastRun={state === 'happy' ? '4h' : null} />
        <button style={{ ...ghostBtn2, flex: 1, justifyContent: 'center', height: 30 }}><Icon name="note" size={12} color="var(--ink-2)"/>Note</button>
        <button style={{ ...ghostBtn2, flex: 1, justifyContent: 'center', height: 30 }}><Icon name="bell" size={12} color="var(--ink-2)"/>Alert</button>
      </div>
    </div>
  );
}

/* ===================== SHARED HELPERS ===================== */
const surfaceStyle = {
  background: 'var(--paper)',
  border: '1px solid var(--rule)',
  borderRadius: 6,
  overflow: 'hidden',
};
const ghostBtn2 = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  height: 28, padding: '0 10px', background: 'var(--paper-1)',
  border: '1px solid var(--rule)', borderRadius: 5, cursor: 'pointer',
  fontSize: 12, color: 'var(--ink-1)', fontFamily: 'var(--font-sans)',
};
const iconBtnSm = {
  width: 24, height: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  background: 'transparent', border: 'none', borderRadius: 4, cursor: 'pointer',
};

function SectionHeader({ eyebrow, children, right, small }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
      padding: small ? '10px 14px 6px' : '14px 18px 8px',
      borderBottom: '1px solid var(--rule-soft)',
      gap: 12,
    }}>
      <div>
        <div className="eyebrow" style={{ marginBottom: 3 }}>{eyebrow}</div>
        <h3 style={{ fontSize: small ? 13 : 15, fontWeight: 600 }}>{children}</h3>
      </div>
      {right}
    </div>
  );
}

function KV({ label, value, sub, hi }) {
  return (
    <div style={{
      padding: 12,
      background: hi ? 'var(--conv-strong-bg)' : 'var(--paper-1)',
      border: hi ? '1px solid var(--conv-strong)' : '1px solid var(--rule-soft)',
      borderRadius: 5,
      display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      <div className="eyebrow" style={{ color: hi ? 'var(--conv-strong)' : 'var(--ink-3)' }}>{label}</div>
      <div>{value}</div>
      {sub && <div>{sub}</div>}
    </div>
  );
}

window.StockDetailArtboard = StockDetailArtboard;
