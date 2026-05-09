/* Stock Detail — 4 variants */

// ────────────────────────────────────────────────────────────
// A — Inline accordion (row expands in the watchlist)
// ────────────────────────────────────────────────────────────
const DetailA = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    {/* compressed list above */}
    {TICKERS.slice(0, 2).map((row) => (
      <div key={row.t} style={{
        display: 'grid', gridTemplateColumns: '52px 1fr 80px 70px 50px 80px 56px 60px',
        gap: 8, alignItems: 'center', padding: '5px 16px',
        borderBottom: '1px solid var(--rule-faint)', fontSize: 12
      }}>
        <span className="wf-mono" style={{ fontWeight: 600, fontSize: 13 }}>{row.t}</span>
        <span className="wf-tiny">{row.n}</span>
        <span style={{ textAlign: 'right' }}><Money v={row.px} ccy={row.ccy} /></span>
        <span style={{ textAlign: 'right' }}><Pct v={row.dp} /></span>
        <span className="wf-mono" style={{ textAlign: 'right' }}>{row.score.toFixed(1)}</span>
        <span style={{ textAlign: 'right' }}><Money v={row.tgt} ccy={row.ccy} /></span>
        <span style={{ textAlign: 'center' }}><Conv tier={row.conv} /></span>
        <span style={{ textAlign: 'right' }}><Pct v={row.up} /></span>
      </div>
    ))}
    {/* expanded row — LITE */}
    <div style={{
      borderLeft: '3px solid var(--ink)', borderBottom: '1px solid var(--rule-faint)',
      background: 'var(--paper-2)', padding: 0
    }}>
      <div style={{
        display: 'grid', gridTemplateColumns: '52px 1fr 80px 70px 50px 80px 56px 60px',
        gap: 8, alignItems: 'center', padding: '6px 16px', fontSize: 12
      }}>
        <span className="wf-mono" style={{ fontWeight: 700, fontSize: 14 }}>▾ CRWV</span>
        <span className="wf-tiny">CoreWeave</span>
        <span style={{ textAlign: 'right' }}><Money v={122.40} ccy="USD" /></span>
        <span style={{ textAlign: 'right' }}><Pct v={3.2} /></span>
        <span className="wf-mono" style={{ textAlign: 'right' }}>8.9</span>
        <span style={{ textAlign: 'right' }}><Money v={220} ccy="USD" /></span>
        <span style={{ textAlign: 'center' }}><Conv tier="HIGH" /></span>
        <span style={{ textAlign: 'right' }}><Pct v={79.7} /></span>
      </div>
      {/* THESIS HEADLINE STRIP */}
      <div style={{
        margin: '4px 16px 12px', padding: '12px 14px',
        background: 'var(--conv-high-bg)', border: '1.5px solid var(--conv-high)',
        borderRadius: 3
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span className="wf-eyebrow" style={{ color: 'var(--conv-high)' }}>THESIS HEADLINE · v3.2 · 3h ago</span>
          <Conv tier="HIGH" size="lg" />
        </div>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 16,
          alignItems: 'baseline'
        }}>
          {[
            ['THESIS TGT', '$220', '+79.7%'],
            ['BREAKOUT', '$340', null],
            ['RISK-ADJ', '$215', null],
            ['BUY BELOW', '$95', null],
            ['TRIM ABOVE', '$280', null],
            ['POSITION', '25%', null],
          ].map(([l, v, sub]) => (
            <div key={l}>
              <div className="wf-eyebrow">{l}</div>
              <div className="wf-mono" style={{ fontSize: 18, fontWeight: 600, marginTop: 2 }}>{v}</div>
              {sub && <div className="wf-tiny wf-pos wf-mono" style={{ marginTop: 1 }}>{sub}</div>}
            </div>
          ))}
        </div>
      </div>
      {/* 3-col content */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, padding: '0 16px 16px' }}>
        {/* SETUP */}
        <div className="wf-rough-soft" style={{ padding: 10 }}>
          <div className="wf-eyebrow" style={{ marginBottom: 8 }}>SETUP QUALITY · 5/5</div>
          {[
            ['demand inflecting', true, 'AI inference TAM 3×ing'],
            ['ceiling visible', true, 'pricing power firm'],
            ['best competitor', true, 'vs hyperscaler offerings'],
            ['complete chain', true, 'capacity → revenue locked'],
            ['macro supportive', true, 'rate cuts priced'],
          ].map(([l, p, ev]) => (
            <div key={l} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 6 }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%',
                background: p ? 'var(--conv-high)' : 'transparent',
                border: '1px solid var(--rule-soft)', marginTop: 3, flexShrink: 0
              }} />
              <div>
                <div style={{ fontSize: 11, fontWeight: 600 }}>{l}</div>
                <div className="wf-tiny">{ev}</div>
              </div>
            </div>
          ))}
        </div>
        {/* RISKS / CATALYSTS */}
        <div>
          <div className="wf-rough-soft" style={{ padding: 10, marginBottom: 8 }}>
            <div className="wf-eyebrow" style={{ marginBottom: 6 }}>TOP RISKS</div>
            {[
              ['NVDA supply tightens', '40% × −22%', 'Q3 datacenter ship rate'],
              ['Hyperscaler in-source', '25% × −18%', 'AWS Trainium adoption'],
              ['Customer concentration', '20% × −12%', 'top-5 % of revenue'],
            ].map(([n, p, w]) => (
              <div key={n} className="wf-tiny" style={{ marginBottom: 5, lineHeight: 1.4 }}>
                <div style={{ fontWeight: 600, color: 'var(--ink)' }}>{n}</div>
                <span className="wf-mono">{p}</span> · <span style={{ color: 'var(--blue)' }}>watch: {w}</span>
              </div>
            ))}
          </div>
          <div className="wf-rough-soft" style={{ padding: 10 }}>
            <div className="wf-eyebrow" style={{ marginBottom: 6 }}>TOP CATALYSTS</div>
            {[
              ['Q3 backlog reveal', '70% × +25%', 'guide raise'],
              ['Anthropic capacity deal', '35% × +18%', 'press release'],
            ].map(([n, p, w]) => (
              <div key={n} className="wf-tiny" style={{ marginBottom: 5, lineHeight: 1.4 }}>
                <div style={{ fontWeight: 600 }}>{n}</div>
                <span className="wf-mono">{p}</span> · <span style={{ color: 'var(--pos)' }}>confirms: {w}</span>
              </div>
            ))}
          </div>
        </div>
        {/* HUME NOTES + KILL */}
        <div>
          <div style={{
            padding: 10, border: '1.5px solid var(--rule)',
            background: 'var(--paper)', borderRadius: 3, marginBottom: 8
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span className="wf-eyebrow">HUME NOTES · verbatim</span>
              <span className="wf-tiny wf-mono" style={{ color: 'var(--pos)' }}>● saved</span>
            </div>
            <div className="wf-mono" style={{ fontSize: 11, lineHeight: 1.5, color: 'var(--ink-2)' }}>
              spoke w/ K — channel checks confirm Q3 ramp.<br/>
              core thesis intact, breakout at $340 still valid.<br/>
              <span style={{ color: 'var(--ink-3)' }}>cursor▍</span>
            </div>
          </div>
          <div className="wf-dashed" style={{ padding: 10 }}>
            <div className="wf-eyebrow" style={{ color: 'var(--conv-broken)', marginBottom: 6 }}>KILL TRIGGERS · sell if</div>
            <ul className="wf-tiny" style={{ margin: 0, paddingLeft: 16, lineHeight: 1.5 }}>
              <li>Q4 revenue &lt; $1.5B</li>
              <li>top-3 customer churn signal</li>
              <li>price closes below $80 on volume</li>
            </ul>
          </div>
        </div>
      </div>
      {/* SCOUTS + bottom links */}
      <div style={{
        padding: '10px 16px', borderTop: '1px dashed var(--rule-soft)',
        display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center'
      }}>
        <span className="wf-eyebrow" style={{ marginRight: 4 }}>SCOUTS 8/9</span>
        {['Fund ↑','News ↑','Filings →','Insider ↑','Catalyst ↑','Quant ↑','Social ↑','Disc ↑','Moat ↑'].map(s => (
          <Chip key={s}>{s}</Chip>
        ))}
        <span style={{ flex: 1 }} />
        <button className="wf-btn">What-If sandbox →</button>
        <button className="wf-btn wf-btn-primary">Open full workbook →</button>
      </div>
    </div>
    {/* row below */}
    <div style={{
      display: 'grid', gridTemplateColumns: '52px 1fr 80px 70px 50px 80px 56px 60px',
      gap: 8, alignItems: 'center', padding: '5px 16px',
      borderBottom: '1px solid var(--rule-faint)', fontSize: 12
    }}>
      <span className="wf-mono" style={{ fontWeight: 600, fontSize: 13 }}>ASML</span>
      <span className="wf-tiny">ASML Holding</span>
      <span style={{ textAlign: 'right' }}><Money v={932.10} ccy="EUR" /></span>
      <span style={{ textAlign: 'right' }}><Pct v={-0.89} /></span>
      <span className="wf-mono" style={{ textAlign: 'right' }}>6.9</span>
      <span style={{ textAlign: 'right' }}><Money v={1100} ccy="EUR" /></span>
      <span style={{ textAlign: 'center' }}><Conv tier="MEDIUM" /></span>
      <span style={{ textAlign: 'right' }}><Pct v={18.0} /></span>
    </div>

    <div style={{ position: 'absolute', right: 24, top: 80, width: 200 }}>
      <div className="wf-postit">accordion expansion — context preserved.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// B — Full-page route /stock/[ticker]
//   · scouts moved into header as dropdown chip
//   · horizontal price ladder where scouts used to live
// ────────────────────────────────────────────────────────────
const ScoutsHeaderChip = ({ open = false }) => (
  <div style={{ position: 'relative' }}>
    <button className="wf-btn" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
      <span style={{ display: 'inline-flex', gap: 2 }}>
        {[1,1,1,1,1,1,1,1,0].map((on, i) => (
          <span key={i} style={{
            width: 5, height: 5, borderRadius: '50%',
            background: on ? 'var(--conv-high)' : 'var(--rule-soft)'
          }} />
        ))}
      </span>
      <span className="wf-mono" style={{ fontSize: 11 }}>scouts 8/9</span>
      <span style={{ fontSize: 9, color: 'var(--ink-3)' }}>▾</span>
    </button>
    {open && (
      <div style={{
        position: 'absolute', right: 0, top: 'calc(100% + 4px)', zIndex: 5,
        width: 240, padding: 10, background: 'var(--paper)',
        border: '1.5px solid var(--rule)', borderRadius: 3, boxShadow: '2px 2px 0 rgba(0,0,0,0.05)'
      }}>
        <div className="wf-eyebrow" style={{ marginBottom: 6 }}>SCOUT STATUS · 8/9 BULLISH</div>
        {[
          ['Fundamentals', '↑', 'on'],
          ['News',         '↑', 'on'],
          ['Filings',      '→', 'on'],
          ['Insider',      '↑', 'on'],
          ['Catalyst',     '↑', 'on'],
          ['Quant',        '↑', 'on'],
          ['Social',       '↑', 'on'],
          ['Discovery',    '↑', 'on'],
          ['Moat',         '·', 'off'],
        ].map(([n, dir, st]) => (
          <div key={n} style={{
            display: 'flex', justifyContent: 'space-between',
            padding: '3px 0', fontSize: 11, fontFamily: 'var(--mono)',
            color: st === 'off' ? 'var(--ink-3)' : 'var(--ink)'
          }}>
            <span>{n}</span>
            <span style={{
              color: dir === '↑' ? 'var(--pos)' : dir === '↓' ? 'var(--neg)' : 'var(--ink-3)'
            }}>{dir}</span>
          </div>
        ))}
      </div>
    )}
  </div>
);

const DetailB = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <div style={{ padding: '10px 20px', borderBottom: '1px solid var(--rule-faint)', display: 'flex', alignItems: 'center', gap: 12 }}>
      <span className="wf-tiny wf-mono" style={{ color: 'var(--ink-3)' }}>← Watchlist /</span>
      <span className="wf-mono" style={{ fontSize: 22, fontWeight: 600 }}>CRWV</span>
      <span style={{ color: 'var(--ink-2)' }}>CoreWeave</span>
      <Chip>USD</Chip>
      <Chip>AI Compute</Chip>
      <span style={{ flex: 1 }} />
      <Money v={122.40} ccy="USD" big /><Pct v={3.2} />
      <span style={{ width: 12 }} />
      <ScoutsHeaderChip open={true} />
      <button className="wf-btn">re-run thesis</button>
      <button className="wf-btn">Open workbook →</button>
    </div>

    {/* Hero strip — thesis dominant */}
    <div style={{
      margin: 20, padding: '18px 22px',
      background: 'var(--conv-high-bg)', border: '1.5px solid var(--conv-high)', borderRadius: 4
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span className="wf-eyebrow" style={{ color: 'var(--conv-high)' }}>THESIS · v3.2 · 3h ago · coverage HIGH</span>
        <Conv tier="HIGH" size="lg" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr 1fr 1fr 1fr', gap: 20 }}>
        <div>
          <div className="wf-eyebrow">THESIS TARGET</div>
          <div className="wf-mono" style={{ fontSize: 36, fontWeight: 600, lineHeight: 1 }}>$220</div>
          <div className="wf-mono wf-pos" style={{ fontSize: 13, marginTop: 4 }}>+79.7% from $122.40</div>
        </div>
        {[
          ['BREAKOUT', '$340'],
          ['RISK-ADJ', '$215'],
          ['BUY BELOW', '$95'],
          ['TRIM ABOVE', '$280'],
          ['POSITION', '25%'],
        ].map(([l, v]) => (
          <div key={l} style={{ borderLeft: '1px solid var(--conv-high)', paddingLeft: 12 }}>
            <div className="wf-eyebrow">{l}</div>
            <div className="wf-mono" style={{ fontSize: 22, fontWeight: 600, marginTop: 2 }}>{v}</div>
          </div>
        ))}
      </div>
    </div>

    {/* DCF strip — secondary, muted */}
    <div style={{
      margin: '0 20px 20px', padding: '10px 14px',
      background: 'var(--paper-2)', border: '1px dashed var(--rule-soft)', borderRadius: 3,
      display: 'grid', gridTemplateColumns: '160px repeat(4, 1fr)', gap: 16, alignItems: 'baseline'
    }}>
      <div>
        <div className="wf-eyebrow">FLOOR · DCF</div>
        <div className="wf-tiny" style={{ marginTop: 2 }}>downside anchor only</div>
      </div>
      {[['CURRENT', '$122', null], ['DOWNSIDE', '$95', '−22%'], ['BASE', '$165', '+35%'], ['UPSIDE', '$240', '+96%']].map(([l, v, sub]) => (
        <div key={l}>
          <div className="wf-eyebrow">{l}</div>
          <div className="wf-mono" style={{ fontSize: 16, fontWeight: 500, color: 'var(--ink-2)' }}>{v}</div>
          {sub && <div className="wf-tiny wf-mono" style={{ color: 'var(--ink-3)' }}>{sub}</div>}
        </div>
      ))}
    </div>

    {/* 2-col: setup+risks LEFT, hume+memory+scouts RIGHT */}
    <div style={{ padding: '0 20px 20px', display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 16 }}>
      <div>
        <div className="wf-rough-soft" style={{ padding: 12, marginBottom: 12 }}>
          <div className="wf-eyebrow" style={{ marginBottom: 8 }}>SETUP QUALITY · 5/5</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
            {['demand', 'ceiling', 'competitor', 'chain', 'macro'].map((l) => (
              <div key={l} style={{ padding: 8, background: 'var(--conv-high-bg)', border: '1px solid var(--conv-high)', borderRadius: 2, textAlign: 'center' }}>
                <div className="wf-mono" style={{ fontSize: 11, fontWeight: 600 }}>✓ {l}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="wf-rough-soft" style={{ padding: 12, marginBottom: 12 }}>
          <div className="wf-eyebrow" style={{ marginBottom: 8 }}>RISKS · CATALYSTS · KILL TRIGGERS</div>
          <div className="wf-tiny" style={{ lineHeight: 1.7 }}>
            <span className="wf-anno-tag" style={{ background: 'var(--conv-broken-bg)', color: 'var(--conv-broken)' }}>RISK</span> NVDA supply · 40%×−22% · watch Q3 ship rate<br/>
            <span className="wf-anno-tag" style={{ background: 'var(--conv-broken-bg)', color: 'var(--conv-broken)' }}>RISK</span> Hyperscaler in-source · 25%×−18%<br/>
            <span className="wf-anno-tag" style={{ background: 'var(--conv-high-bg)', color: 'var(--conv-high)' }}>CAT</span> Q3 backlog · 70%×+25% · guide raise<br/>
            <span className="wf-anno-tag" style={{ background: 'var(--conv-high-bg)', color: 'var(--conv-high)' }}>CAT</span> Anthropic deal · 35%×+18%<br/>
            <span className="wf-anno-tag" style={{ background: 'var(--ink)', color: 'var(--paper)' }}>KILL</span> Q4 rev &lt; $1.5B
          </div>
        </div>
        {/* Horizontal price ladder — replaces scouts strip */}
        <div className="wf-rough-soft" style={{ padding: '14px 18px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 18 }}>
            <span className="wf-eyebrow">PRICE LADDER · USD</span>
            <span className="wf-tiny wf-mono wf-pos" style={{ fontWeight: 600 }}>conviction band: current → thesis · +79.7%</span>
          </div>
          <div style={{ position: 'relative', height: 84, padding: '0 16px' }}>
            <div style={{ position: 'absolute', left: 16, right: 16, top: 42, borderTop: '1.5px solid var(--rule-soft)' }} />
            {(() => {
              const min = 70, max = 360;
              const x = (v) => `calc(16px + ${((v - min) / (max - min)) * 100}% - ${(((v - min) / (max - min)) * 32)}px)`;
              // alternate sides + stagger to avoid collisions
              const marks = [
                { v: 80,     label: 'KILL',     color: 'var(--conv-broken)', side: 'b', row: 0, big: false },
                { v: 95,     label: 'BUY',      color: 'var(--ink-3)',       side: 't', row: 0, big: false },
                { v: 122.40, label: 'CURRENT',  color: 'var(--ink)',         side: 'b', row: 0, big: true  },
                { v: 165,    label: 'DCF BASE', color: 'var(--ink-3)',       side: 't', row: 0, big: false },
                { v: 215,    label: 'RISK-ADJ', color: 'var(--ink-3)',       side: 'b', row: 1, big: false },
                { v: 220,    label: 'THESIS',   color: 'var(--conv-high)',   side: 't', row: 0, big: true  },
                { v: 280,    label: 'TRIM',     color: 'var(--ink-3)',       side: 'b', row: 0, big: false },
                { v: 340,    label: 'BREAKOUT', color: 'var(--conv-high)',   side: 't', row: 0, big: false },
              ];
              return (
                <>
                  <div style={{
                    position: 'absolute', left: x(122.40), right: `calc(100% - ${x(220)})`,
                    top: 36, height: 12, background: 'var(--conv-high-bg)',
                    border: '1px solid var(--conv-high)', opacity: 0.7
                  }} />
                  {marks.map((m, i) => {
                    // tick
                    const tickTop = m.big ? 30 : 36;
                    const tickH = m.big ? 24 : 12;
                    // label position
                    const baseTopLeader = m.side === 't' ? -8 : 56;
                    // 'b' row=1 means push further down to dodge row=0 below-axis label
                    const offset = m.row === 1 ? 18 : 0;
                    const labelTop = m.side === 't' ? baseTopLeader - offset : baseTopLeader + offset;
                    return (
                      <React.Fragment key={i}>
                        <div style={{
                          position: 'absolute', left: x(m.v), top: tickTop, height: tickH,
                          borderLeft: `${m.big ? 2 : 1.25}px solid ${m.color}`,
                        }} />
                        {/* leader line if staggered */}
                        {m.row === 1 && (
                          <div style={{
                            position: 'absolute', left: x(m.v),
                            top: m.side === 't' ? labelTop + 18 : tickTop + tickH,
                            height: m.side === 't' ? (tickTop - (labelTop + 18)) : (labelTop - (tickTop + tickH)),
                            borderLeft: '1px dashed var(--rule-soft)'
                          }} />
                        )}
                        <div style={{
                          position: 'absolute', left: x(m.v), top: labelTop,
                          textAlign: 'center', whiteSpace: 'nowrap',
                          transform: 'translateX(calc(-50% + 16px))'
                        }}>
                          <div className="wf-eyebrow" style={{ color: m.color, fontWeight: m.big ? 700 : 500, fontSize: m.big ? 9 : 8 }}>{m.label}</div>
                          <div className="wf-mono" style={{
                            fontSize: m.big ? 13 : 10, fontWeight: m.big ? 700 : 500, color: m.color, lineHeight: 1.1
                          }}>${m.v.toLocaleString()}</div>
                        </div>
                      </React.Fragment>
                    );
                  })}
                </>
              );
            })()}
          </div>
        </div>
      </div>
      <div>
        <div style={{ border: '1.5px solid var(--rule)', borderRadius: 3, padding: 12, marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span className="wf-eyebrow">HUME NOTES · YOUR VERBATIM SPACE</span>
            <span className="wf-tiny wf-pos">● saved 12s ago · 412ch</span>
          </div>
          <div className="wf-mono" style={{ fontSize: 11, lineHeight: 1.6, minHeight: 90, color: 'var(--ink-2)' }}>
            spoke w/ K — channel checks confirm Q3 ramp.<br/>
            core thesis intact, breakout $340 valid.<br/>
            <br/>
            ?? if NVDA H200 supply slips, would CRWV lose first-mover edge?<br/>
            <span style={{ color: 'var(--ink-3)' }}>cursor▍</span>
          </div>
        </div>
        <div className="wf-rough-soft" style={{ padding: 10 }}>
          <div className="wf-eyebrow" style={{ marginBottom: 6 }}>MEMORY.MD</div>
          <div className="wf-tiny" style={{ lineHeight: 1.6 }}>
            <div style={{ fontWeight: 600 }}>▾ Stable Facts</div>
            <div style={{ paddingLeft: 10 }}>founded 2017 · NJ-based · public Mar '25</div>
            <div style={{ fontWeight: 600, marginTop: 4 }}>▾ Recent Thesis History</div>
            <div style={{ paddingLeft: 10 }}>v3.2 ($220) · v3.1 ($195) · v3.0 ($170)</div>
            <div style={{ color: 'var(--ink-3)', marginTop: 4 }}>▸ Persistent Risks (3)</div>
            <div style={{ color: 'var(--ink-3)' }}>▸ Resolved (5)</div>
          </div>
        </div>
      </div>
    </div>

    <div style={{ position: 'absolute', right: 24, top: 80, width: 200 }}>
      <div className="wf-postit" style={{ transform: 'rotate(1deg)' }}>scouts → header dropdown chip. price ladder claims the freed bottom-left strip.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// C — Side-drawer hybrid
// ────────────────────────────────────────────────────────────
const DetailC = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <FilterStrip />
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 540px', minHeight: 700 }}>
      <div style={{ borderRight: '1.5px solid var(--rule)', overflow: 'hidden' }}>
        {TICKERS.slice(0, 10).map((row, i) => (
          <div key={row.t} style={{
            display: 'grid', gridTemplateColumns: '60px 1fr 70px 60px 80px 56px 50px',
            gap: 8, padding: '7px 14px', borderBottom: '1px solid var(--rule-faint)',
            background: row.t === 'CRWV' ? 'var(--paper-2)' : 'transparent',
            borderLeft: row.t === 'CRWV' ? '3px solid var(--ink)' : '3px solid transparent',
            fontSize: 12, alignItems: 'center'
          }}>
            <span className="wf-mono" style={{ fontWeight: 600, fontSize: 13 }}>{row.t}</span>
            <span className="wf-tiny">{row.n}</span>
            <span style={{ textAlign: 'right' }}><Money v={row.px} ccy={row.ccy} /></span>
            <span className="wf-mono" style={{ textAlign: 'right' }}>{row.score.toFixed(1)}</span>
            <span style={{ textAlign: 'right' }}><Money v={row.tgt} ccy={row.ccy} /></span>
            <span style={{ display: 'flex', justifyContent: 'flex-end' }}><Conv tier={row.conv} /></span>
            <span style={{ textAlign: 'right' }}><Pct v={row.up} /></span>
          </div>
        ))}
      </div>
      {/* Drawer */}
      <div style={{ background: 'var(--paper)', padding: 16, overflowY: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <div>
            <div className="wf-mono" style={{ fontSize: 24, fontWeight: 600 }}>CRWV</div>
            <div className="wf-tiny">CoreWeave · AI Compute</div>
          </div>
          <span className="wf-tiny wf-mono" style={{ cursor: 'pointer' }}>✕ close</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 4 }}>
          <Money v={122.40} ccy="USD" big /><Pct v={3.2} />
        </div>
        <div className="wf-rough-soft" style={{
          marginTop: 14, padding: 12,
          background: 'var(--conv-high-bg)', border: '1.5px solid var(--conv-high)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="wf-eyebrow" style={{ color: 'var(--conv-high)' }}>THESIS HEADLINE</span>
            <Conv tier="HIGH" size="lg" />
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 6 }}>
            <span className="wf-mono" style={{ fontSize: 28, fontWeight: 600 }}>$220</span>
            <Pct v={79.7} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginTop: 10 }}>
            {[['BREAK','$340'],['BUY','$95'],['TRIM','$280'],['POS','25%']].map(([l,v]) => (
              <div key={l}>
                <div className="wf-eyebrow">{l}</div>
                <div className="wf-mono" style={{ fontSize: 13, fontWeight: 600 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
          <div className="wf-rough-soft" style={{ padding: 10 }}>
            <div className="wf-eyebrow" style={{ marginBottom: 6 }}>SETUP 5/5</div>
            <div className="wf-tiny" style={{ lineHeight: 1.6 }}>
              ● demand · ● ceiling<br/>
              ● compet · ● chain · ● macro
            </div>
          </div>
          <div className="wf-rough-soft" style={{ padding: 10 }}>
            <div className="wf-eyebrow" style={{ marginBottom: 6 }}>FLOOR (DCF)</div>
            <div className="wf-tiny wf-mono" style={{ lineHeight: 1.6, color: 'var(--ink-2)' }}>
              base $165 · low $95<br/>
              high $240
            </div>
          </div>
        </div>
        <div className="wf-rough-soft" style={{ padding: 10, marginTop: 10 }}>
          <div className="wf-eyebrow">RISKS · CATALYSTS</div>
          <div className="wf-tiny" style={{ lineHeight: 1.6, marginTop: 4 }}>
            ▼ NVDA supply · 40%×−22%<br/>
            ▼ Hyperscaler in-source · 25%×−18%<br/>
            ▲ Q3 backlog · 70%×+25%
          </div>
        </div>
        <div style={{
          padding: 10, marginTop: 10, border: '1.5px solid var(--rule)', borderRadius: 3
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="wf-eyebrow">HUME NOTES</span>
            <span className="wf-tiny wf-pos">● saved</span>
          </div>
          <div className="wf-mono" style={{ fontSize: 11, lineHeight: 1.6, marginTop: 4, color: 'var(--ink-2)' }}>
            spoke w/ K — channel checks confirm Q3 ramp.
            <span style={{ color: 'var(--ink-3)' }}>▍</span>
          </div>
        </div>
        <button className="wf-btn wf-btn-primary" style={{ width: '100%', marginTop: 12 }}>
          Open full workbook →
        </button>
      </div>
    </div>
    <div style={{ position: 'absolute', right: 560, top: 90, width: 180 }}>
      <div className="wf-postit">drawer keeps the list visible. j/k cycles. esc closes.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// D — WILDCARD: vertical price ladder spine
// ────────────────────────────────────────────────────────────
const DetailD = () => {
  // Build a vertical price ladder from $0 → $400, with key levels marked
  const min = 0, max = 400;
  const px = (v) => ((max - v) / (max - min)) * 540 + 30;
  const levels = [
    { v: 340, label: 'BREAKOUT', side: 'r', color: 'var(--ink-3)' },
    { v: 280, label: 'TRIM ABOVE', side: 'r', color: 'var(--ink-3)' },
    { v: 240, label: 'DCF UPSIDE', side: 'l', color: 'var(--ink-3)', dim: true },
    { v: 220, label: 'THESIS TARGET', side: 'r', color: 'var(--conv-high)', big: true },
    { v: 165, label: 'DCF BASE', side: 'l', color: 'var(--ink-3)', dim: true },
    { v: 122.40, label: 'CURRENT', side: 'r', color: 'var(--ink)', big: true, anchor: true },
    { v: 95, label: 'BUY BELOW · DCF DOWN', side: 'l', color: 'var(--ink-3)', dim: true },
    { v: 80, label: 'KILL · price stop', side: 'r', color: 'var(--conv-broken)' },
  ];
  return (
    <div className="wf" style={{ width: 1180, minHeight: 760 }}>
      <TopChrome />
      <div style={{ padding: '10px 20px', borderBottom: '1px solid var(--rule-faint)', display: 'flex', alignItems: 'center', gap: 12 }}>
        <span className="wf-mono" style={{ fontSize: 22, fontWeight: 600 }}>CRWV</span>
        <span style={{ color: 'var(--ink-2)' }}>CoreWeave</span>
        <Conv tier="HIGH" size="lg" />
        <span style={{ flex: 1 }} />
        <span className="wf-anno">↑ everything orbits the price spine</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px 1fr', minHeight: 600, padding: '20px 0' }}>
        {/* LEFT — DCF + risks */}
        <div style={{ padding: '0 20px', textAlign: 'right' }}>
          <div className="wf-eyebrow" style={{ textAlign: 'right' }}>FLOOR · DCF (secondary)</div>
          <div className="wf-tiny" style={{ marginTop: 8, lineHeight: 1.7, color: 'var(--ink-3)' }}>
            scenario grid: low $95 · base $165 · high $240<br/>
            engine corroborates breakout — thesis above floor base by +33%
          </div>
          <div className="wf-rough-soft" style={{ padding: 10, marginTop: 14, textAlign: 'left' }}>
            <div className="wf-eyebrow" style={{ marginBottom: 6 }}>TOP RISKS</div>
            <div className="wf-tiny" style={{ lineHeight: 1.6 }}>
              ▼ NVDA supply · 40%×−22%<br/>
              ▼ Hyperscaler in-source · 25%×−18%<br/>
              ▼ Customer concentration · 20%×−12%
            </div>
          </div>
          <div className="wf-dashed" style={{ padding: 10, marginTop: 8, textAlign: 'left' }}>
            <div className="wf-eyebrow" style={{ marginBottom: 6, color: 'var(--conv-broken)' }}>KILL TRIGGERS</div>
            <div className="wf-tiny" style={{ lineHeight: 1.5 }}>
              · Q4 rev &lt; $1.5B<br/>
              · top-3 customer churn<br/>
              · close &lt; $80 on volume
            </div>
          </div>
        </div>
        {/* SPINE */}
        <div style={{ position: 'relative', height: 600 }}>
          {/* axis */}
          <div style={{
            position: 'absolute', left: '50%', top: 20, bottom: 20,
            borderLeft: '1.5px solid var(--rule)', transform: 'translateX(-0.75px)'
          }} />
          {/* current zone shading */}
          <div style={{
            position: 'absolute', left: 'calc(50% - 50px)', width: 100,
            top: px(220), height: px(122.40) - px(220),
            background: 'var(--conv-high-bg)', opacity: 0.45
          }} />
          {levels.map((lev) => (
            <div key={lev.v} style={{ position: 'absolute', left: 0, right: 0, top: px(lev.v) - 10, height: 20 }}>
              <div style={{
                position: 'absolute', left: 'calc(50% - 8px)', width: 16, height: 1.5,
                top: 9, background: lev.color, opacity: lev.dim ? 0.5 : 1
              }} />
              <div style={{
                position: 'absolute',
                [lev.side === 'l' ? 'right' : 'left']: 'calc(50% + 14px)',
                top: 0, textAlign: lev.side, opacity: lev.dim ? 0.55 : 1
              }}>
                <div className="wf-eyebrow" style={{ color: lev.color }}>{lev.label}</div>
                <div className="wf-mono" style={{
                  fontSize: lev.big ? 18 : 13, fontWeight: lev.big ? 700 : 500, color: lev.color
                }}>${lev.v.toLocaleString()}</div>
              </div>
              {lev.anchor && (
                <div style={{
                  position: 'absolute', left: 'calc(50% - 4px)', top: 5, width: 8, height: 8,
                  background: 'var(--ink)', borderRadius: '50%'
                }} />
              )}
            </div>
          ))}
          {/* upside arc label */}
          <div style={{
            position: 'absolute', left: 'calc(50% - 70px)', top: px(170),
            width: 140, textAlign: 'center', pointerEvents: 'none'
          }} className="wf-anno">+79.7%<br/>upside</div>
        </div>
        {/* RIGHT — setup + hume */}
        <div style={{ padding: '0 20px' }}>
          <div className="wf-eyebrow">SETUP QUALITY · 5/5</div>
          <div className="wf-tiny" style={{ marginTop: 8, lineHeight: 1.7 }}>
            ● demand inflecting<br/>
            ● ceiling visible<br/>
            ● best competitor<br/>
            ● complete chain<br/>
            ● macro supportive
          </div>
          <div className="wf-rough-soft" style={{ padding: 10, marginTop: 14 }}>
            <div className="wf-eyebrow" style={{ marginBottom: 6 }}>TOP CATALYSTS</div>
            <div className="wf-tiny" style={{ lineHeight: 1.6 }}>
              ▲ Q3 backlog · 70%×+25%<br/>
              ▲ Anthropic deal · 35%×+18%
            </div>
          </div>
          <div style={{ padding: 10, marginTop: 8, border: '1.5px solid var(--rule)', borderRadius: 3 }}>
            <div className="wf-eyebrow">HUME NOTES</div>
            <div className="wf-mono" style={{ fontSize: 11, lineHeight: 1.5, marginTop: 4, color: 'var(--ink-2)' }}>
              channel checks confirm Q3 ramp. core intact.<br/>
              <span style={{ color: 'var(--ink-3)' }}>▍</span>
            </div>
          </div>
        </div>
      </div>
      <div style={{ position: 'absolute', right: 24, bottom: 24, width: 220 }}>
        <div className="wf-postit" style={{ transform: 'rotate(2deg)' }}>
          wildcard — every price-relevant level (current, breakout, target, floor, kill) is plotted on a single axis. risk vs reward is visible at a glance.
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { DetailA, DetailB, DetailC, DetailD });
