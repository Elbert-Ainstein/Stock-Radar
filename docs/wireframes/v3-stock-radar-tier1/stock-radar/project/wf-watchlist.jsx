/* Watchlist — 4 variants */

const TopChrome = ({ running = false }) => (
  <div className="wf-chrome">
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{
        width: 22, height: 22, border: '1.5px solid var(--rule)', borderRadius: 3,
        display: 'grid', placeItems: 'center', fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 700
      }}>SR</div>
      <div className="wf-mono" style={{ fontSize: 13, fontWeight: 600 }}>Stock&nbsp;Radar</div>
    </div>
    <div style={{ display: 'flex', gap: 14, marginLeft: 18 }}>
      {['Watchlist', 'Discovery', 'Models', 'Ask AI', 'Logs'].map((l, i) => (
        <span key={l} className="wf-mono" style={{
          fontSize: 11, color: i === 0 ? 'var(--ink)' : 'var(--ink-3)',
          fontWeight: i === 0 ? 600 : 400,
          borderBottom: i === 0 ? '1.5px solid var(--ink)' : 'none',
          paddingBottom: 2
        }}>{l}</span>
      ))}
    </div>
    <div style={{ flex: 1 }} />
    <span className="wf-tiny wf-mono" style={{ color: running ? 'var(--pos)' : 'var(--ink-3)' }}>
      ● pipeline {running ? 'running 7/12' : 'idle'}
    </span>
    <button className="wf-btn">⌖ Run pipeline</button>
    <button className="wf-btn wf-btn-primary">▶ Run all theses</button>
    <span className="wf-mono" style={{ fontSize: 11, color: 'var(--ink-3)', marginLeft: 8 }}>☾</span>
  </div>
);

const FilterStrip = () => (
  <div style={{
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 16px',
    borderBottom: '1px solid var(--rule-faint)', background: 'var(--paper)'
  }}>
    <span className="wf-eyebrow">SORT</span>
    <Chip active>score ↓</Chip>
    <Chip>conviction</Chip>
    <Chip>upside</Chip>
    <Chip>sector</Chip>
    <Chip>last-run</Chip>
    <span style={{ width: 16 }} />
    <span className="wf-eyebrow">CONVICTION</span>
    <Chip active style={{ borderColor: 'var(--conv-high)' }}>HIGH 6</Chip>
    <Chip active style={{ borderColor: 'var(--conv-med)' }}>MED 4</Chip>
    <Chip>LOW 1</Chip>
    <Chip>BROKEN 0</Chip>
    <div style={{ flex: 1 }} />
    <span className="wf-tiny wf-mono">12 tickers · last sync 2m ago</span>
  </div>
);

// ────────────────────────────────────────────────────────────
// VARIANT A — Bloomberg-tight (28px rows, 12 columns)
// ────────────────────────────────────────────────────────────
const WatchlistA = () => {
  const cols = '52px 1fr 80px 70px 50px 64px 80px 56px 50px 60px 36px';
  return (
    <div className="wf" style={{ width: 1180, minHeight: 760 }}>
      <TopChrome running />
      <FilterStrip />
      <div style={{ padding: '6px 16px', borderBottom: '1px solid var(--rule-faint)' }}>
        <div className="wf-eyebrow" style={{
          display: 'grid', gridTemplateColumns: cols, gap: 8, alignItems: 'center'
        }}>
          <span>TICKER</span>
          <span>NAME · SECTOR</span>
          <span style={{ textAlign: 'right' }}>PRICE</span>
          <span style={{ textAlign: 'right' }}>Δ%</span>
          <span style={{ textAlign: 'right' }}>SCORE</span>
          <span style={{ textAlign: 'center' }}>30d</span>
          <span style={{ textAlign: 'right' }}>TGT</span>
          <span style={{ textAlign: 'center' }}>CONV</span>
          <span style={{ textAlign: 'right' }}>UP%</span>
          <span style={{ textAlign: 'center' }}>FILT · SCOUT</span>
          <span style={{ textAlign: 'right' }}>RUN</span>
        </div>
      </div>
      {TICKERS.map((row) => (
        <div key={row.t} style={{
          display: 'grid', gridTemplateColumns: cols, gap: 8, alignItems: 'center',
          padding: '5px 16px', borderBottom: '1px solid var(--rule-faint)',
          minHeight: 28, fontSize: 12
        }}>
          <span className="wf-mono" style={{ fontWeight: 600, fontSize: 13 }}>{row.t}</span>
          <span style={{ color: 'var(--ink-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {row.n} <span className="wf-tiny">· {row.sec}</span>
          </span>
          <span style={{ textAlign: 'right' }}><Money v={row.px} ccy={row.ccy} /></span>
          <span style={{ textAlign: 'right' }}><Pct v={row.dp} /></span>
          <span className="wf-mono" style={{ textAlign: 'right', fontWeight: 600 }}>{row.score.toFixed(1)}</span>
          <span style={{ textAlign: 'center' }}><Spark dir={row.sd >= 0 ? 'up' : 'down'} /></span>
          <span style={{ textAlign: 'right' }}><Money v={row.tgt} ccy={row.ccy} /></span>
          <span style={{ textAlign: 'center' }}><Conv tier={row.conv} /></span>
          <span style={{ textAlign: 'right' }}><Pct v={row.up} /></span>
          <span style={{ textAlign: 'center' }} className="wf-tiny wf-mono">
            {row.fp}/5 · {row.scout}
          </span>
          <span style={{ textAlign: 'right' }} className="wf-tiny wf-mono">{row.ago}</span>
        </div>
      ))}

      <div style={{ position: 'absolute', right: 24, top: 96, width: 200 }}>
        <div className="wf-postit">
          tight grid — every column is a glance, no card chrome.
          ~28px rows, 12 visible at once.
        </div>
      </div>
      <div style={{ position: 'absolute', left: 240, top: 64 }} className="wf-anno">
        ↑ chrome stays out of the way<br/>nav · status · CTA
      </div>
    </div>
  );
};

// ────────────────────────────────────────────────────────────
// VARIANT B — Breathable two-line rows
// ────────────────────────────────────────────────────────────
const WatchlistB = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <FilterStrip />
    <div style={{ padding: '4px 0' }}>
      {TICKERS.slice(0, 9).map((row, i) => (
        <div key={row.t} style={{
          padding: '14px 20px', borderBottom: '1px solid var(--rule-faint)',
          display: 'grid', gridTemplateColumns: '120px 1fr 200px 220px 160px 80px',
          gap: 18, alignItems: 'center'
        }}>
          {/* Ticker stack */}
          <div>
            <div className="wf-mono" style={{ fontSize: 22, fontWeight: 600, lineHeight: 1 }}>{row.t}</div>
            <div className="wf-tiny" style={{ marginTop: 4 }}>{row.sec} · {row.ccy}</div>
          </div>
          {/* Name + price */}
          <div>
            <div style={{ fontSize: 13, color: 'var(--ink-2)' }}>{row.n}</div>
            <div style={{ marginTop: 4, display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <Money v={row.px} ccy={row.ccy} big />
              <Pct v={row.dp} />
            </div>
          </div>
          {/* Score */}
          <div>
            <div className="wf-eyebrow">MONITOR SCORE</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 2 }}>
              <span className="wf-num-lg">{row.score.toFixed(1)}</span>
              <span className="wf-tiny wf-mono" style={{ color: row.sd >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                {row.sd >= 0 ? '+' : '−'}{Math.abs(row.sd).toFixed(1)}
              </span>
              <Spark dir={row.sd >= 0 ? 'up' : 'down'} w={56} h={20} />
            </div>
          </div>
          {/* Thesis target — emphasized */}
          <div style={{
            border: '1.25px solid var(--rule-soft)', borderRadius: 3,
            padding: '6px 10px', background: 'var(--paper-2)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span className="wf-eyebrow">THESIS TGT</span>
              <Conv tier={row.conv} />
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 2 }}>
              <Money v={row.tgt} ccy={row.ccy} big />
              <Pct v={row.up} />
            </div>
          </div>
          {/* Setup + scout */}
          <div>
            <div className="wf-eyebrow">SETUP · SCOUT</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
              <Dots n={row.fp} />
              <span className="wf-tiny wf-mono">{row.scout} bull</span>
            </div>
            <div className="wf-tiny" style={{ marginTop: 3 }}>pos&nbsp;{row.pos}%</div>
          </div>
          {/* Last run */}
          <div style={{ textAlign: 'right' }}>
            <div className="wf-eyebrow">RUN</div>
            <div className="wf-tiny wf-mono" style={{ marginTop: 2 }}>{row.ago}</div>
          </div>
        </div>
      ))}
    </div>
    <div style={{ position: 'absolute', right: 24, top: 110, width: 210 }}>
      <div className="wf-postit" style={{ transform: 'rotate(1deg)' }}>
        breathable — thesis target gets its own outlined cell so it pops.
        9 rows visible · scroll for rest.
      </div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// VARIANT C — List + sticky right rail preview
// ────────────────────────────────────────────────────────────
const WatchlistC = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <FilterStrip />
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', height: 700 }}>
      <div style={{ borderRight: '1.5px solid var(--rule-soft)', overflow: 'hidden' }}>
        {TICKERS.slice(0, 12).map((row, i) => (
          <div key={row.t} style={{
            display: 'grid', gridTemplateColumns: '60px 1fr 80px 60px 70px 90px 60px',
            gap: 10, alignItems: 'center',
            padding: '8px 14px', borderBottom: '1px solid var(--rule-faint)',
            background: i === 0 ? 'var(--paper-2)' : 'transparent',
            borderLeft: i === 0 ? '3px solid var(--ink)' : '3px solid transparent'
          }}>
            <span className="wf-mono" style={{ fontSize: 14, fontWeight: 600 }}>{row.t}</span>
            <span className="wf-tiny" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.n}</span>
            <span style={{ textAlign: 'right' }}><Money v={row.px} ccy={row.ccy} /></span>
            <span className="wf-mono" style={{ textAlign: 'right', fontSize: 12 }}>{row.score.toFixed(1)}</span>
            <span style={{ textAlign: 'right' }}><Money v={row.tgt} ccy={row.ccy} /></span>
            <span style={{ display: 'flex', justifyContent: 'flex-end' }}><Conv tier={row.conv} /></span>
            <span style={{ textAlign: 'right' }}><Pct v={row.up} /></span>
          </div>
        ))}
      </div>
      {/* Right rail preview */}
      <div style={{ padding: 16, background: 'var(--paper)' }}>
        <div className="wf-eyebrow">PREVIEW · LITE</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
          <span className="wf-mono" style={{ fontSize: 28, fontWeight: 600 }}>LITE</span>
          <span className="wf-tiny">Lumentum Holdings</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', marginTop: 4 }}>
          <Money v={949.93} ccy="USD" big /><Pct v={5.28} />
        </div>
        <div className="wf-rough-soft" style={{
          marginTop: 14, padding: 12, background: 'var(--paper-2)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="wf-eyebrow">THESIS HEADLINE</span>
            <Conv tier="HIGH" size="lg" />
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 6 }}>
            <span className="wf-mono" style={{ fontSize: 24, fontWeight: 600 }}>$1,250</span>
            <Pct v={31.6} />
          </div>
          <div className="wf-tiny wf-mono" style={{ marginTop: 6, color: 'var(--ink-3)' }}>
            buy below $800 · trim above $1,500 · pos 25%
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <div className="wf-eyebrow">SETUP QUALITY · 4/5</div>
          <div className="wf-tiny" style={{ marginTop: 6, lineHeight: 1.7 }}>
            ● demand inflecting<br/>
            ● ceiling visible<br/>
            ● best competitor<br/>
            ○ <span style={{ color: 'var(--ink-3)' }}>complete chain</span><br/>
            ● macro supportive
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <div className="wf-eyebrow">TOP RISK</div>
          <div className="wf-tiny" style={{ marginTop: 4 }}>
            CHIPS Act delay · 30%×−15% · <span style={{ color: 'var(--blue)' }}>watch: q3 capex guide</span>
          </div>
        </div>
        <button className="wf-btn" style={{ marginTop: 14, width: '100%' }}>open full detail →</button>
      </div>
    </div>
    <div style={{ position: 'absolute', left: 580, top: 120, width: 180 }}>
      <div className="wf-postit">selected row spawns preview on the right. arrow keys cycle.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// VARIANT D — WILDCARD: upside ladder, target as horizontal bar
// ────────────────────────────────────────────────────────────
const WatchlistD = () => {
  const sorted = [...TICKERS].sort((a, b) => b.up - a.up);
  const maxUp = Math.max(...sorted.map(r => Math.abs(r.up)));
  return (
    <div className="wf" style={{ width: 1180, minHeight: 760 }}>
      <TopChrome />
      <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--rule-faint)', display: 'flex', gap: 12, alignItems: 'center' }}>
        <span className="wf-eyebrow">VIEW</span>
        <Chip>list</Chip>
        <Chip>grid</Chip>
        <Chip active>ladder</Chip>
        <span style={{ flex: 1 }} />
        <span className="wf-eyebrow">SORTED BY UPSIDE</span>
      </div>
      {/* Header axis */}
      <div style={{ padding: '6px 20px 0 20px' }}>
        <div style={{
          display: 'grid', gridTemplateColumns: '90px 1fr 90px 70px',
          gap: 10, fontSize: 10, color: 'var(--ink-3)',
          fontFamily: 'var(--mono)', letterSpacing: '0.08em', textTransform: 'uppercase'
        }}>
          <span>TICKER</span>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>−25%</span><span>0</span><span>+50%</span><span>+100%</span>
          </div>
          <span style={{ textAlign: 'right' }}>TARGET</span>
          <span style={{ textAlign: 'right' }}>CONV</span>
        </div>
      </div>
      {sorted.map((row) => {
        const pct = row.up;
        const zero = 25 / 125; // current price marker at -25 origin
        const left = zero * 100;
        const w = (Math.abs(pct) / 125) * 100;
        const isNeg = pct < 0;
        const color = row.conv === 'HIGH' ? 'var(--conv-high)' :
                      row.conv === 'MEDIUM' ? 'var(--conv-med)' :
                      row.conv === 'LOW' ? 'var(--conv-low)' : 'var(--conv-broken)';
        return (
          <div key={row.t} style={{
            padding: '8px 20px', borderBottom: '1px solid var(--rule-faint)',
            display: 'grid', gridTemplateColumns: '90px 1fr 90px 70px',
            gap: 10, alignItems: 'center'
          }}>
            <div>
              <div className="wf-mono" style={{ fontSize: 14, fontWeight: 600 }}>{row.t}</div>
              <div className="wf-tiny">{row.sec}</div>
            </div>
            <div style={{ position: 'relative', height: 30 }}>
              {/* axis */}
              <div style={{
                position: 'absolute', left: 0, right: 0, top: 14,
                borderTop: '1px dashed var(--rule-soft)'
              }} />
              {/* zero tick */}
              <div style={{
                position: 'absolute', left: `${left}%`, top: 4, bottom: 4,
                borderLeft: '1.5px solid var(--ink-3)'
              }} />
              {/* bar */}
              <div style={{
                position: 'absolute',
                left: isNeg ? `${left - w}%` : `${left}%`,
                width: `${w}%`, top: 8, height: 14,
                background: color, opacity: 0.55,
                border: `1px solid ${color}`
              }} />
              <span className="wf-mono" style={{
                position: 'absolute',
                left: isNeg ? `${left - w}%` : `calc(${left + w}% + 4px)`,
                transform: isNeg ? 'translateX(calc(-100% - 4px))' : 'none',
                top: 6, fontSize: 11, fontWeight: 600, color: color
              }}>{pct >= 0 ? '+' : '−'}{Math.abs(pct).toFixed(0)}%</span>
            </div>
            <div style={{ textAlign: 'right' }}><Money v={row.tgt} ccy={row.ccy} /></div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}><Conv tier={row.conv} /></div>
          </div>
        );
      })}
      <div style={{ position: 'absolute', right: 24, top: 120, width: 220 }}>
        <div className="wf-postit" style={{ transform: 'rotate(-2deg)' }}>
          wildcard — every ticker becomes a bar from 'current' to 'thesis'.
          conviction = bar color. instantly comparable.
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { WatchlistA, WatchlistB, WatchlistC, WatchlistD, TopChrome });
