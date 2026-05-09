/* hifi/sr-watchlist.jsx — production watchlist
   Default: list (Bloomberg-tight). Toggle to grid or ladder.
   Handles: happy / empty / loading / error / stale states. */

const { useState: wlUseState } = React;

/* ---- Top chrome (header + sub-toolbar) shared by all watchlist views ---- */
function WatchlistChrome({ view, onView, state, onState, breakpoint = 'desktop' }) {
  const isPhone = breakpoint === 'phone';
  const isTablet = breakpoint === 'tablet';
  return (
    <>
      {/* App header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: isPhone ? '10px 14px' : '12px 18px',
        borderBottom: '1px solid var(--rule)',
        background: 'var(--paper)',
        gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6.5" stroke="var(--ink)" strokeWidth="1.4"/>
              <circle cx="8" cy="8" r="3" stroke="var(--ink)" strokeWidth="1.4"/>
              <circle cx="8" cy="8" r="0.8" fill="var(--ink)"/>
            </svg>
            <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: '-0.01em' }}>Stock Radar</span>
          </div>
          {!isPhone && (
            <nav style={{ display: 'flex', gap: 2, marginLeft: 8 }}>
              {['Watchlist','Discovery','Ask','Logs'].map((n,i) => (
                <a key={n} style={{
                  padding: '6px 10px', borderRadius: 4, fontSize: 12.5,
                  color: i===0 ? 'var(--ink)' : 'var(--ink-2)', fontWeight: i===0 ? 600 : 500,
                  background: i===0 ? 'var(--paper-2)' : 'transparent',
                  cursor: 'pointer', textDecoration: 'none',
                }}>{n}</a>
              ))}
            </nav>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {!isPhone && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 9px', background: 'var(--paper-1)',
              border: '1px solid var(--rule)', borderRadius: 5, minWidth: 220,
            }}>
              <Icon name="search" size={13} color="var(--ink-3)"/>
              <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Search ticker, thesis, scout…</span>
              <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>⌘K</span>
            </div>
          )}
          <button style={iconBtn}><Icon name="bell" size={14} color="var(--ink-2)"/></button>
          <div style={{ width: 26, height: 26, borderRadius: '50%', background: 'var(--paper-3)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: 'var(--ink-1)' }}>RM</div>
        </div>
      </div>

      {/* Sub-toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: isPhone ? '8px 14px' : '10px 18px',
        borderBottom: '1px solid var(--rule-soft)',
        background: 'var(--paper)',
        gap: 8, flexWrap: isPhone ? 'wrap' : 'nowrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <h1 style={{ fontSize: isPhone ? 16 : 18, fontWeight: 600, letterSpacing: '-0.015em' }}>Watchlist</h1>
          <StatePill tone="mute" size="sm" dot={false}>12 tickers</StatePill>
          {state === 'happy' && <StatePill tone="ok" size="sm">All synced · 12m</StatePill>}
          {state === 'stale' && <StatePill tone="warn" size="sm">3 stale · &gt;24h</StatePill>}
          {state === 'error' && <StatePill tone="err" size="sm">2 failed runs</StatePill>}
          {state === 'loading' && <StatePill tone="info" size="sm">Running 4 theses</StatePill>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {!isPhone && (
            <>
              <button style={ghostBtn}><Icon name="filter" size={12} color="var(--ink-2)"/>Filter</button>
              <button style={ghostBtn}><Icon name="setting" size={12} color="var(--ink-2)"/>Columns</button>
              <span style={{ width: 1, height: 16, background: 'var(--rule)' }}/>
            </>
          )}
          <ViewToggle
            value={view}
            onChange={onView}
            options={[
              { value: 'list',   label: 'List',   icon: <Icon name="list"   size={12}/> },
              { value: 'grid',   label: 'Grid',   icon: <Icon name="grid"   size={12}/> },
              { value: 'ladder', label: 'Ladder', icon: <Icon name="ladder" size={12}/> },
            ]}
          />
          {!isPhone && <button style={primaryBtn}><Icon name="plus" size={12} color="var(--action-ink)"/>Add ticker</button>}
        </div>
      </div>
    </>
  );
}

const iconBtn = {
  width: 28, height: 28, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  background: 'transparent', border: 'none', borderRadius: 4, cursor: 'pointer',
};
const ghostBtn = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  height: 26, padding: '0 9px', background: 'transparent',
  border: '1px solid var(--rule)', borderRadius: 4, cursor: 'pointer',
  fontSize: 11.5, color: 'var(--ink-1)', fontFamily: 'var(--font-sans)',
};
const primaryBtn = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  height: 28, padding: '0 11px', background: 'var(--action)', color: 'var(--action-ink)',
  border: 'none', borderRadius: 5, cursor: 'pointer',
  fontSize: 12, fontWeight: 500, fontFamily: 'var(--font-sans)',
};

/* ============================================================
   LIST VIEW (desktop) — Bloomberg-tight rows
   ============================================================ */
function WatchlistListDesktop({ state = 'happy' }) {
  const cols = [
    { key: 'tk',   w: 76,  align: 'left',  label: 'TICKER' },
    { key: 'nm',   w: 150, align: 'left',  label: 'NAME' },
    { key: 'last', w: 86,  align: 'right', label: 'LAST' },
    { key: 'chg',  w: 70,  align: 'right', label: 'CHG' },
    { key: 'pct',  w: 64,  align: 'right', label: '%' },
    { key: 'sp',   w: 90,  align: 'left',  label: '5D' },
    { key: 'cv',   w: 92,  align: 'left',  label: 'CONVICTION' },
    { key: 'th',   w: 86,  align: 'right', label: 'THESIS' },
    { key: 'up',   w: 66,  align: 'right', label: 'UPSIDE' },
    { key: 'dc',   w: 78,  align: 'right', label: 'DCF' },
    { key: 'dr',   w: 110, align: 'left',  label: 'DRIFT' },
    { key: 'st',   w: 110, align: 'left',  label: 'SETUP' },
    { key: 'rn',   w: 90,  align: 'left',  label: 'LAST RUN' },
    { key: 'act',  w: 80,  align: 'right', label: '' },
  ];
  const total = cols.reduce((s,c) => s + c.w, 0);
  return (
    <div className="sr" style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: total, fontFamily: 'var(--font-sans)' }}>
        <thead>
          <tr style={{ height: 26, background: 'var(--paper-1)', borderBottom: '1px solid var(--rule)' }}>
            {cols.map(c => (
              <th key={c.key} style={{
                width: c.w, padding: '0 10px', textAlign: c.align,
                fontFamily: 'var(--font-mono)', fontSize: 9.5, fontWeight: 500,
                letterSpacing: '0.1em', color: 'var(--ink-3)', textTransform: 'uppercase',
              }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SR_TICKERS.map((t, i) => (
            <WatchListRow key={t.ticker} t={t} cols={cols} state={state} idx={i} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WatchListRow({ t, cols, state, idx }) {
  // Per-row state derivation: a few rows show non-happy states deterministically
  const rowState =
    state === 'loading' && (idx === 1 || idx === 2 || idx === 4 || idx === 8) ? 'loading' :
    state === 'error'   && (idx === 6 || idx === 10) ? 'error' :
    state === 'stale'   && (idx === 6 || idx === 7 || idx === 11) ? 'stale' :
    state === 'empty'   ? 'empty' :
    'happy';

  const upside = ((t.thesis - t.price) / t.price) * 100;
  const driftPct = ((t.thesis - t.dcf) / t.dcf) * 100;
  const driftAbove = t.thesis > t.dcf;

  const skel = (w) => <span className="sr-skel" style={{ height: 9, width: w, borderRadius: 2 }} />;

  return (
    <tr style={{
      height: 28,
      borderBottom: '1px solid var(--rule-soft)',
      background: idx % 2 === 1 ? 'var(--paper-1)' : 'transparent',
    }}>
      {/* TICKER */}
      <td style={{ padding: '0 10px', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--ink)', letterSpacing: '0.02em' }}>
        {t.ticker}
      </td>
      {/* NAME */}
      <td style={{ padding: '0 10px', fontSize: 12, color: 'var(--ink-2)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 150 }}>
        {t.name}
      </td>
      {/* LAST */}
      <td style={{ padding: '0 10px', textAlign: 'right' }}>
        <MoneyValue value={t.price} size={12} weight={500} />
      </td>
      {/* CHG */}
      <td style={{ padding: '0 10px', textAlign: 'right' }}>
        <span className="num mono" style={{ fontSize: 12, color: t.chg > 0 ? 'var(--pos)' : t.chg < 0 ? 'var(--neg)' : 'var(--neutral)' }}>
          {t.chg > 0 ? '+' : t.chg < 0 ? '−' : ''}{Math.abs(t.chg).toFixed(2)}
        </span>
      </td>
      {/* PCT */}
      <td style={{ padding: '0 10px', textAlign: 'right' }}>
        <PctValue value={t.chgPct} size={11.5} />
      </td>
      {/* SPARK */}
      <td style={{ padding: '0 8px' }}>
        <Sparkline data={t.spark} width={80} height={18} />
      </td>
      {/* CONVICTION */}
      <td style={{ padding: '0 10px' }}>
        {rowState === 'loading' ? skel(60) : <ConvictionBadge level={t.conv} size="xs" />}
      </td>
      {/* THESIS */}
      <td style={{ padding: '0 10px', textAlign: 'right' }}>
        {rowState === 'loading' ? skel(50) :
         rowState === 'empty'   ? <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>—</span> :
         <MoneyValue value={t.thesis} size={12} weight={600} />}
      </td>
      {/* UPSIDE */}
      <td style={{ padding: '0 10px', textAlign: 'right' }}>
        {rowState === 'loading' ? skel(40) :
         rowState === 'empty'   ? <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>—</span> :
         <PctValue value={upside} size={11.5} signed={true} />}
      </td>
      {/* DCF (muted, secondary) */}
      <td style={{ padding: '0 10px', textAlign: 'right' }}>
        {rowState === 'loading' ? skel(40) :
         rowState === 'empty'   ? <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>—</span> :
         <span className="num mono" style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>${t.dcf.toFixed(0)}</span>}
      </td>
      {/* DRIFT */}
      <td style={{ padding: '0 10px' }}>
        {rowState === 'loading' || rowState === 'empty' ? null : (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            fontSize: 10.5, fontFamily: 'var(--font-mono)',
            color: driftAbove ? 'var(--ink-2)' : 'var(--conv-fade)',
          }}>
            <span style={{ fontSize: 11 }}>{driftAbove ? '↑' : '↓'}</span>
            {driftAbove ? 'above' : 'below'} {Math.abs(driftPct).toFixed(0)}%
          </span>
        )}
      </td>
      {/* SETUP */}
      <td style={{ padding: '0 10px' }}>
        <span style={{ fontSize: 11, color: 'var(--ink-2)', fontStyle: 'italic' }}>{t.setup}</span>
      </td>
      {/* LAST RUN */}
      <td style={{ padding: '0 10px' }}>
        {rowState === 'loading' ?
          <StatePill tone="info" size="sm" dot={false}><span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}><span style={{ width: 4, height: 4, borderRadius: '50%', background: 'currentColor', animation: 'sr-pulse 1.2s infinite' }}/>RUNNING</span></StatePill> :
         rowState === 'error' ? <StatePill tone="err" size="sm">FAILED</StatePill> :
         rowState === 'stale' ? <StatePill tone="warn" size="sm">{t.last}</StatePill> :
         rowState === 'empty' ? <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>never run</span> :
         <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{t.last}</span>}
      </td>
      {/* ACTIONS */}
      <td style={{ padding: '0 10px', textAlign: 'right' }}>
        <div style={{ display: 'inline-flex', gap: 4 }}>
          {rowState === 'empty' ? <RunButton state="idle" size="sm" label="Run" /> :
           rowState === 'error' ? <RunButton state="error" size="sm" label="Retry" /> :
           rowState === 'loading' ? null :
           <button style={iconBtn}><Icon name="dots" size={14} color="var(--ink-3)"/></button>}
        </div>
      </td>
    </tr>
  );
}

/* ============================================================
   GRID VIEW — card per ticker
   ============================================================ */
function WatchlistGrid({ state = 'happy', breakpoint = 'desktop' }) {
  const cols = breakpoint === 'phone' ? 1 : breakpoint === 'tablet' ? 2 : 4;
  return (
    <div className="sr" style={{ padding: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 12 }}>
        {SR_TICKERS.map((t, i) => (
          <TickerCard key={t.ticker} t={t} state={state} idx={i} />
        ))}
      </div>
    </div>
  );
}

function TickerCard({ t, state, idx }) {
  const upside = ((t.thesis - t.price) / t.price) * 100;
  const rowState =
    state === 'loading' && (idx === 1 || idx === 4) ? 'loading' :
    state === 'error'   && (idx === 6) ? 'error' :
    state === 'stale'   && (idx === 6 || idx === 7) ? 'stale' :
    state === 'empty'   && (idx === 0) ? 'empty' :
    'happy';
  return (
    <div style={{
      background: 'var(--paper-1)',
      border: '1px solid var(--rule)',
      borderRadius: 6,
      padding: 12,
      display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, letterSpacing: '0.02em' }}>{t.ticker}</span>
          <span style={{ fontSize: 11, color: 'var(--ink-3)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.name}</span>
        </div>
        {rowState === 'loading' ? <span className="sr-skel" style={{ height: 14, width: 60 }}/> : <ConvictionBadge level={t.conv} size="xs" />}
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <MoneyValue value={t.price} size={20} weight={600} />
          <PctValue value={t.chgPct} size={11.5} />
        </div>
        <Sparkline data={t.spark} width={70} height={26} fill />
      </div>
      <div style={{ height: 1, background: 'var(--rule-soft)' }}/>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--ink-3)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 2 }}>Thesis</div>
          {rowState === 'loading' ? <span className="sr-skel" style={{ height: 13, width: 70 }}/> :
           rowState === 'empty'   ? <span style={{ fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>not run yet</span> :
           <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
             <MoneyValue value={t.thesis} size={14} weight={600} />
             <PctValue value={upside} size={11} />
           </div>}
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--ink-3)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 2 }}>Floor</div>
          <span className="num mono" style={{ fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>${t.dcf.toFixed(0)}</span>
        </div>
      </div>
      {rowState === 'error' && <StatePill tone="err" size="sm">subprocess failed</StatePill>}
      {rowState === 'stale' && <StatePill tone="warn" size="sm">stale · {t.last}</StatePill>}
    </div>
  );
}

/* ============================================================
   LADDER VIEW — comparative bar chart
   ============================================================ */
function WatchlistLadder({ state = 'happy' }) {
  const sorted = [...SR_TICKERS].sort((a,b) => ((b.thesis-b.price)/b.price) - ((a.thesis-a.price)/a.price));
  const max = Math.max(...sorted.map(t => Math.abs(((t.thesis-t.price)/t.price)*100)));
  return (
    <div className="sr" style={{ padding: 18 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {sorted.map(t => {
          const up = ((t.thesis - t.price) / t.price) * 100;
          const w = (Math.abs(up) / max) * 100;
          return (
            <div key={t.ticker} style={{ display: 'grid', gridTemplateColumns: '60px 92px 1fr 110px 80px', gap: 12, alignItems: 'center', height: 28 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600 }}>{t.ticker}</span>
              <ConvictionBadge level={t.conv} size="xs" />
              <div style={{ position: 'relative', height: 20, background: 'var(--paper-1)', border: '1px solid var(--rule-soft)', borderRadius: 3 }}>
                <div style={{
                  position: 'absolute', left: 0, top: 0, bottom: 0, width: `${w}%`,
                  background: up > 0 ? 'var(--conv-strong-bg)' : 'var(--conv-broken-bg)',
                  borderRight: `2px solid ${up > 0 ? 'var(--conv-strong)' : 'var(--conv-broken)'}`,
                }}/>
                <span className="num mono" style={{
                  position: 'absolute', left: `calc(${w}% + 6px)`, top: '50%', transform: 'translateY(-50%)',
                  fontSize: 11, fontWeight: 600, color: up > 0 ? 'var(--conv-strong)' : 'var(--conv-broken)',
                }}>{up > 0 ? '+' : '−'}{Math.abs(up).toFixed(1)}%</span>
              </div>
              <MoneyValue value={t.thesis} size={12} weight={500} />
              <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{t.setup}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ============================================================
   PHONE VIEW — stacked cards, full parity
   ============================================================ */
function WatchlistPhone({ state = 'happy' }) {
  return (
    <div className="sr" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {SR_TICKERS.slice(0, 8).map((t, i) => {
        const up = ((t.thesis - t.price) / t.price) * 100;
        const rowState =
          state === 'loading' && i === 1 ? 'loading' :
          state === 'error'   && i === 4 ? 'error' :
          state === 'stale'   && i === 6 ? 'stale' :
          state === 'empty'   && i === 0 ? 'empty' :
          'happy';
        return (
          <div key={t.ticker} style={{
            background: 'var(--paper-1)', border: '1px solid var(--rule)',
            borderRadius: 6, padding: 12,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600 }}>{t.ticker}</span>
                <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{t.name}</span>
              </div>
              {rowState !== 'loading' && <ConvictionBadge level={t.conv} size="xs" />}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
              <div>
                <MoneyValue value={t.price} size={18} weight={600} />
                <span style={{ marginLeft: 6 }}><PctValue value={t.chgPct} size={11.5} /></span>
              </div>
              <Sparkline data={t.spark} width={60} height={22} fill />
            </div>
            <div style={{ height: 1, background: 'var(--rule-soft)', margin: '8px 0' }}/>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11 }}>
              {rowState === 'loading' ? <StatePill tone="info" size="sm">running</StatePill> :
               rowState === 'empty'   ? <span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}>no thesis yet</span> :
               rowState === 'error'   ? <StatePill tone="err" size="sm">failed</StatePill> :
               <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                 <span><span style={{ color: 'var(--ink-3)', marginRight: 4 }}>thesis</span><MoneyValue value={t.thesis} size={12} weight={600}/></span>
                 <PctValue value={up} size={11.5}/>
                 <span style={{ color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>floor ${t.dcf}</span>
               </div>}
              {rowState === 'empty' && <RunButton state="idle" size="sm" />}
              {rowState === 'error' && <RunButton state="error" size="sm" label="Retry" />}
            </div>
          </div>
        );
      })}
      {/* phone bottom nav */}
      <div style={{
        position: 'sticky', bottom: 0, marginLeft: -12, marginRight: -12, marginBottom: -12,
        marginTop: 8,
        background: 'var(--paper)', borderTop: '1px solid var(--rule)',
        display: 'flex', justifyContent: 'space-around', padding: '8px 0', paddingBottom: 14,
      }}>
        {[
          {n:'Watch', icon:'list', a:true},
          {n:'Discover', icon:'eye'},
          {n:'Run', icon:'play'},
          {n:'Ask', icon:'zap'},
          {n:'Logs', icon:'note'},
        ].map(it => (
          <div key={it.n} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, color: it.a ? 'var(--ink)' : 'var(--ink-3)' }}>
            <Icon name={it.icon} size={16} color={it.a ? 'var(--ink)' : 'var(--ink-3)'}/>
            <span style={{ fontSize: 9.5, fontWeight: it.a ? 600 : 500 }}>{it.n}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ============================================================
   Empty / Error / Stale full-frame states for List view
   ============================================================ */
function WatchlistEmpty() {
  return (
    <div className="sr" style={{ padding: 60, textAlign: 'center', color: 'var(--ink-2)' }}>
      <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 14, maxWidth: 420 }}>
        <div style={{ width: 48, height: 48, borderRadius: '50%', background: 'var(--paper-1)', border: '1px dashed var(--rule-strong)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon name="star" size={20} color="var(--ink-3)"/>
        </div>
        <div>
          <h2 style={{ fontSize: 17, marginBottom: 4 }}>Your watchlist is empty</h2>
          <p style={{ fontSize: 13, color: 'var(--ink-3)' }}>Add tickers to start tracking thesis · floor · conviction.</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={primaryBtn}><Icon name="plus" size={12} color="var(--action-ink)"/>Add ticker</button>
          <button style={ghostBtn}>Import CSV</button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   Master export — desktop watchlist artboard
   ============================================================ */
function WatchlistArtboard({ breakpoint = 'desktop', state = 'happy', defaultView = 'list' }) {
  const [view, setView] = wlUseState(defaultView);
  const [s, setS] = wlUseState(state);
  React.useEffect(() => { setS(state); }, [state]);
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <WatchlistChrome view={view} onView={setView} state={s} onState={setS} breakpoint={breakpoint}/>
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {s === 'empty' && view !== 'phone-card' && breakpoint === 'desktop' ? <WatchlistEmpty /> :
         breakpoint === 'phone' ? <WatchlistPhone state={s} /> :
         view === 'grid'   ? <WatchlistGrid state={s} breakpoint={breakpoint} /> :
         view === 'ladder' ? <WatchlistLadder state={s} /> :
         <WatchlistListDesktop state={s} />}
      </div>
    </div>
  );
}

window.WatchlistArtboard = WatchlistArtboard;
