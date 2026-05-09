/* Model Detail — 4 variants + 3 drift treatments */

const MDHeader = ({ variant }) => (
  <div style={{ padding: '10px 20px', borderBottom: '1px solid var(--rule-faint)', display: 'flex', alignItems: 'center', gap: 12 }}>
    <span className="wf-tiny wf-mono" style={{ color: 'var(--ink-3)' }}>← Models /</span>
    <span className="wf-mono" style={{ fontSize: 22, fontWeight: 600 }}>CRWV</span>
    <span style={{ color: 'var(--ink-2)' }}>CoreWeave</span>
    <Chip>USD</Chip><Chip>AI Compute</Chip>
    <span style={{ flex: 1 }} />
    <span className="wf-eyebrow">HORIZON</span>
    <Chip>12mo</Chip><Chip active>24mo</Chip><Chip>36mo</Chip>
    <button className="wf-btn">⤓ Excel</button>
    <span className="wf-tiny" style={{ color: 'var(--ink-3)', marginLeft: 6 }}>variant {variant}</span>
  </div>
);

const Tabs = ({ active = 0 }) => {
  const tabs = ['Thesis', 'Setup', 'Risks & Catalysts', 'Floor (DCF)', 'Income', 'Cash', 'Formulas', 'What-If'];
  return (
    <div style={{ display: 'flex', gap: 4, padding: '0 20px', borderBottom: '1px solid var(--rule-soft)' }}>
      {tabs.map((t, i) => (
        <span key={t} className={`wf-tab ${i === active ? 'wf-tab-active' : ''}`}>{t}</span>
      ))}
    </div>
  );
};

// ────────────────────────────────────────────────────────────
// A — Standard tabs · thesis anchor strip · DCF below
// ────────────────────────────────────────────────────────────
const ModelA = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <MDHeader variant="A" />
    <Tabs active={0} />
    {/* Thesis anchor strip — emerald, dominant */}
    <div style={{
      margin: 16, padding: '16px 20px',
      background: 'var(--conv-high-bg)', border: '1.5px solid var(--conv-high)', borderRadius: 4
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <span className="wf-eyebrow" style={{ color: 'var(--conv-high)' }}>THESIS · v3.2 · breakout setup</span>
        <Conv tier="HIGH" size="lg" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr repeat(4, 1fr)', gap: 18, alignItems: 'baseline' }}>
        <div>
          <div className="wf-eyebrow">DESTINATION</div>
          <div className="wf-mono" style={{ fontSize: 36, fontWeight: 600, lineHeight: 1 }}>$220</div>
          <div className="wf-mono wf-pos" style={{ marginTop: 4 }}>+79.7% from $122</div>
        </div>
        {[['BREAKOUT','$340'],['RISK-ADJ','$215'],['BUY','$95'],['POSITION','25%']].map(([l,v])=>(
          <div key={l} style={{ borderLeft: '1px solid var(--conv-high)', paddingLeft: 12 }}>
            <div className="wf-eyebrow">{l}</div>
            <div className="wf-mono" style={{ fontSize: 22, fontWeight: 600 }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
    {/* DCF summary grid — secondary */}
    <div style={{ margin: '0 16px 12px' }}>
      <div className="wf-eyebrow" style={{ marginBottom: 6, color: 'var(--ink-3)' }}>FLOOR · DCF SUMMARY · downside anchor only</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
        {[['CURRENT','$122',null],['DOWNSIDE','$95','−22%'],['FLOOR BASE','$165','+35%'],['UPSIDE','$240','+96%']].map(([l,v,sub])=>(
          <div key={l} style={{ padding: 10, background: 'var(--paper-2)', border: '1px dashed var(--rule-soft)', borderRadius: 3 }}>
            <div className="wf-eyebrow">{l}</div>
            <div className="wf-mono" style={{ fontSize: 18, color: 'var(--ink-2)', marginTop: 2 }}>{v}</div>
            {sub && <div className="wf-tiny wf-mono" style={{ color: 'var(--ink-3)' }}>{sub}</div>}
          </div>
        ))}
      </div>
    </div>
    {/* Drift indicator strip */}
    <div style={{ margin: '0 16px 16px', padding: '8px 12px', border: '1px dashed var(--rule-soft)', borderRadius: 3, display: 'flex', alignItems: 'center', gap: 12 }}>
      <span className="wf-eyebrow">DRIFT</span>
      <span className="wf-anno-tag" style={{ background: 'var(--conv-high-bg)', color: 'var(--conv-high)' }}>thesis above floor</span>
      <span className="wf-tiny wf-mono">$220 vs $165 · +33% gap · engine corroborates within reasonable variance</span>
    </div>
    {/* Tab content body */}
    <div style={{ padding: '0 16px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <div className="wf-rough-soft" style={{ padding: 12 }}>
        <div className="wf-eyebrow">SETUP QUALITY · 5/5</div>
        <div className="wf-tiny" style={{ lineHeight: 1.8, marginTop: 6 }}>
          ● demand inflecting · AI inference 3×ing<br/>
          ● ceiling visible · pricing power firm<br/>
          ● best competitor · vs hyperscaler offerings<br/>
          ● complete chain · capacity → revenue locked<br/>
          ● macro supportive · rate cuts priced
        </div>
      </div>
      <div className="wf-rough-soft" style={{ padding: 12 }}>
        <div className="wf-eyebrow">RISKS · CATALYSTS · KILL</div>
        <div className="wf-tiny" style={{ lineHeight: 1.8, marginTop: 6 }}>
          ▼ NVDA supply · 40%×−22%<br/>
          ▼ Hyperscaler in-source · 25%×−18%<br/>
          ▲ Q3 backlog · 70%×+25%<br/>
          <span style={{ color: 'var(--conv-broken)' }}>KILL · Q4 rev &lt; $1.5B</span>
        </div>
      </div>
    </div>
    <div style={{ position: 'absolute', right: 24, top: 130, width: 200 }}>
      <div className="wf-postit">canonical layout — thesis is biggest type on page; DCF is dashed-border + muted.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// B — Split-pane: thesis LEFT, DCF RIGHT, drift line between
// ────────────────────────────────────────────────────────────
const ModelB = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <MDHeader variant="B" />
    <Tabs active={0} />
    <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 60px 1fr', minHeight: 560, padding: 16, gap: 0 }}>
      {/* THESIS pane */}
      <div style={{
        padding: 18, background: 'var(--conv-high-bg)',
        border: '1.5px solid var(--conv-high)', borderRadius: '4px 0 0 4px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="wf-eyebrow" style={{ color: 'var(--conv-high)' }}>THESIS · HEADLINE</span>
          <Conv tier="HIGH" size="lg" />
        </div>
        <div className="wf-mono" style={{ fontSize: 56, fontWeight: 700, lineHeight: 1, marginTop: 14 }}>$220</div>
        <div className="wf-mono wf-pos" style={{ fontSize: 14, marginTop: 6 }}>+79.7% from $122.40 current</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginTop: 18 }}>
          {[['BREAKOUT','$340'],['BUY BELOW','$95'],['TRIM ABOVE','$280'],['POSITION','25%']].map(([l,v])=>(
            <div key={l} style={{ padding: 8, background: 'rgba(255,255,255,0.4)', borderRadius: 2 }}>
              <div className="wf-eyebrow">{l}</div>
              <div className="wf-mono" style={{ fontSize: 18, fontWeight: 600 }}>{v}</div>
            </div>
          ))}
        </div>
      </div>
      {/* DRIFT spine */}
      <div style={{ position: 'relative', borderTop: '1.5px solid var(--rule)', borderBottom: '1.5px solid var(--rule)', background: 'var(--paper-2)' }}>
        <svg width="60" height="100%" viewBox="0 0 60 560" preserveAspectRatio="none" style={{ display: 'block' }}>
          <line x1="30" y1="0" x2="30" y2="560" stroke="var(--rule-soft)" strokeWidth="1" strokeDasharray="3 3" />
          <path d="M 8 280 Q 30 220 52 280" stroke="var(--blue)" strokeWidth="1.25" fill="none" />
          <text x="30" y="160" textAnchor="middle" fontFamily="Caveat" fontSize="13" fill="var(--blue)">drift</text>
          <text x="30" y="180" textAnchor="middle" fontFamily="Caveat" fontSize="13" fill="var(--blue)">+33%</text>
          <text x="30" y="310" textAnchor="middle" fontFamily="Geist Mono" fontSize="9" fill="var(--ink-3)">THESIS</text>
          <text x="30" y="322" textAnchor="middle" fontFamily="Geist Mono" fontSize="9" fill="var(--ink-3)">vs FLOOR</text>
        </svg>
      </div>
      {/* DCF pane */}
      <div style={{
        padding: 18, background: 'var(--paper-2)',
        border: '1px dashed var(--rule-soft)', borderLeft: 'none', borderRadius: '0 4px 4px 0'
      }}>
        <div className="wf-eyebrow">FLOOR · DCF · base case</div>
        <div className="wf-mono" style={{ fontSize: 36, fontWeight: 500, lineHeight: 1, marginTop: 14, color: 'var(--ink-2)' }}>$165</div>
        <div className="wf-tiny wf-mono" style={{ color: 'var(--ink-3)', marginTop: 6 }}>+35% vs current · DCF base case</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 18 }}>
          {[['LOW','$95'],['BASE','$165'],['HIGH','$240']].map(([l,v])=>(
            <div key={l} style={{ padding: 8, background: 'var(--paper)', border: '1px solid var(--rule-faint)' }}>
              <div className="wf-eyebrow">{l}</div>
              <div className="wf-mono" style={{ fontSize: 14, color: 'var(--ink-2)' }}>{v}</div>
            </div>
          ))}
        </div>
        <div className="wf-tiny" style={{ marginTop: 14, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          revenue CAGR 32% · gross margin 41% · WACC 11.5% · terminal mult 14×
        </div>
      </div>
    </div>
    <div style={{ padding: '0 16px 16px' }}>
      <div className="wf-rough-soft" style={{ padding: 12 }}>
        <div className="wf-eyebrow">SETUP · 5/5 PASSING</div>
        <div className="wf-tiny" style={{ marginTop: 6 }}>● demand · ● ceiling · ● competitor · ● chain · ● macro</div>
      </div>
    </div>
    <div style={{ position: 'absolute', right: 24, top: 200, width: 180 }}>
      <div className="wf-postit" style={{ transform: 'rotate(-1deg)' }}>split — thesis & floor share the eye but typography rank makes thesis the headline.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// C — Stacked + collapsing sections
// ────────────────────────────────────────────────────────────
const ModelC = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <MDHeader variant="C" />
    <div style={{ padding: 16 }}>
      {[
        { open: true, title: 'THESIS', tier: 'HIGH', kind: 'thesis' },
        { open: true, title: 'SETUP QUALITY', kind: 'setup' },
        { open: false, title: 'RISKS & CATALYSTS', kind: 'risks' },
        { open: false, title: 'FLOOR · DCF', tier: 'FLOOR', kind: 'dcf' },
        { open: false, title: 'INCOME · CASH · FORMULAS', kind: 'fin' },
        { open: false, title: 'WHAT-IF SANDBOX', kind: 'whatif' },
      ].map((s, i) => (
        <div key={s.title} style={{
          marginBottom: 8, border: '1.25px solid var(--rule-soft)', borderRadius: 3,
          background: s.open && s.tier === 'HIGH' ? 'var(--conv-high-bg)' : (s.open ? 'var(--paper)' : 'var(--paper-2)'),
          borderColor: s.open && s.tier === 'HIGH' ? 'var(--conv-high)' : 'var(--rule-soft)',
          opacity: s.open ? 1 : 0.85
        }}>
          <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
            <span className="wf-mono" style={{ fontSize: 12, color: 'var(--ink-3)' }}>{s.open ? '▾' : '▸'}</span>
            <span className="wf-eyebrow" style={{ color: s.tier === 'HIGH' ? 'var(--conv-high)' : 'var(--ink-2)' }}>{s.title}</span>
            {s.tier === 'HIGH' && <Conv tier="HIGH" />}
            {s.tier === 'FLOOR' && <span className="wf-anno-tag" style={{ background: 'var(--paper-2)', color: 'var(--ink-3)' }}>secondary · floor only</span>}
            <span style={{ flex: 1 }} />
            {!s.open && <span className="wf-tiny wf-mono" style={{ color: 'var(--ink-3)' }}>
              {s.kind === 'risks' && '3 risks · 2 catalysts · 3 kill'}
              {s.kind === 'dcf' && 'base $165 · drift +33%'}
              {s.kind === 'fin' && 'rev 2027E $4.8B · GM 41%'}
              {s.kind === 'whatif' && '4 sliders'}
            </span>}
          </div>
          {s.open && s.kind === 'thesis' && (
            <div style={{ padding: '0 18px 16px', display: 'grid', gridTemplateColumns: '1.4fr repeat(4, 1fr)', gap: 16, alignItems: 'baseline' }}>
              <div>
                <div className="wf-eyebrow">DESTINATION</div>
                <div className="wf-mono" style={{ fontSize: 36, fontWeight: 700 }}>$220</div>
                <div className="wf-pos wf-mono">+79.7%</div>
              </div>
              {[['BREAK','$340'],['RISK-ADJ','$215'],['BUY','$95'],['POS','25%']].map(([l,v])=>(
                <div key={l}><div className="wf-eyebrow">{l}</div><div className="wf-mono" style={{ fontSize: 18, fontWeight: 600 }}>{v}</div></div>
              ))}
            </div>
          )}
          {s.open && s.kind === 'setup' && (
            <div style={{ padding: '0 18px 14px', display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8 }}>
              {['demand','ceiling','competitor','chain','macro'].map(l => (
                <div key={l} style={{ padding: 8, background: 'var(--conv-high-bg)', border: '1px solid var(--conv-high)', textAlign: 'center', borderRadius: 2 }}>
                  <div className="wf-mono" style={{ fontSize: 11, fontWeight: 600 }}>✓ {l}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
    <div style={{ position: 'absolute', right: 24, top: 130, width: 200 }}>
      <div className="wf-postit" style={{ transform: 'rotate(1deg)' }}>tabs replaced with collapsibles — every section visible at once. floor stays collapsed by default.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// D — WILDCARD: What-If first; sliders top, results recompute
// ────────────────────────────────────────────────────────────
const ModelD = () => (
  <div className="wf" style={{ width: 1180, minHeight: 760 }}>
    <TopChrome />
    <MDHeader variant="D" />
    <Tabs active={7} />
    <div style={{ padding: 16 }}>
      {/* Sliders strip */}
      <div className="wf-rough-soft" style={{ padding: '12px 16px', background: 'var(--paper-2)' }}>
        <div className="wf-eyebrow" style={{ marginBottom: 8 }}>WHAT-IF · live recompute</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
          {[
            ['REV CAGR', '32%', 0.7, 'rev → $4.8B'],
            ['GROSS MARGIN', '41%', 0.55, 'opex held'],
            ['EXIT MULT', '14×', 0.5, 'EV/EBITDA'],
            ['DISCOUNT', '11.5%', 0.4, 'WACC'],
          ].map(([l, v, pos, sub]) => (
            <div key={l}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className="wf-eyebrow">{l}</span>
                <span className="wf-mono" style={{ fontSize: 13, fontWeight: 600 }}>{v}</span>
              </div>
              <div style={{ position: 'relative', height: 6, background: 'var(--rule-faint)', marginTop: 8, borderRadius: 3 }}>
                <div style={{ position: 'absolute', left: 0, top: 0, height: 6, width: `${pos*100}%`, background: 'var(--ink-2)', borderRadius: 3 }} />
                <div style={{ position: 'absolute', left: `${pos*100}%`, top: -3, width: 12, height: 12, borderRadius: '50%', background: 'var(--paper)', border: '1.5px solid var(--ink)' }} />
              </div>
              <div className="wf-tiny" style={{ marginTop: 4 }}>{sub}</div>
            </div>
          ))}
        </div>
      </div>
      {/* Result strip */}
      <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 14 }}>
        <div style={{ padding: 16, background: 'var(--conv-high-bg)', border: '1.5px solid var(--conv-high)', borderRadius: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="wf-eyebrow" style={{ color: 'var(--conv-high)' }}>THESIS · live</span>
            <Conv tier="HIGH" size="lg" />
          </div>
          <div className="wf-mono" style={{ fontSize: 48, fontWeight: 700, lineHeight: 1, marginTop: 8 }}>$220 <span style={{ fontSize: 16, color: 'var(--ink-3)' }}>→ $232</span></div>
          <div className="wf-tiny wf-mono" style={{ marginTop: 6 }}>recomputed: +5.5% from baseline thesis target as sliders moved</div>
        </div>
        <div style={{ padding: 16, background: 'var(--paper-2)', border: '1px dashed var(--rule-soft)', borderRadius: 4 }}>
          <div className="wf-eyebrow">FLOOR · DCF · live</div>
          <div className="wf-mono" style={{ fontSize: 32, fontWeight: 500, lineHeight: 1, marginTop: 8, color: 'var(--ink-2)' }}>$165 <span style={{ fontSize: 14, color: 'var(--ink-3)' }}>→ $172</span></div>
          <div className="wf-tiny wf-mono" style={{ marginTop: 6, color: 'var(--ink-3)' }}>+4.2% vs baseline floor base</div>
        </div>
      </div>
      {/* Drift bar */}
      <div className="wf-dashed" style={{ padding: 12, marginTop: 12 }}>
        <div className="wf-eyebrow" style={{ marginBottom: 6 }}>DRIFT — thesis vs floor</div>
        <div style={{ position: 'relative', height: 28 }}>
          <div style={{ position: 'absolute', left: 0, right: 0, top: 14, borderTop: '1.5px solid var(--rule-soft)' }} />
          <div style={{ position: 'absolute', left: '20%', top: 6, width: 12, height: 12, background: 'var(--ink)', borderRadius: '50%' }} />
          <span className="wf-mono" style={{ position: 'absolute', left: '20%', top: -2, fontSize: 10, transform: 'translateX(-50%)' }}>$122</span>
          <span className="wf-tiny" style={{ position: 'absolute', left: '20%', top: 22, transform: 'translateX(-50%)' }}>current</span>
          <div style={{ position: 'absolute', left: '50%', top: 6, width: 12, height: 12, background: 'var(--ink-3)', borderRadius: '50%' }} />
          <span className="wf-mono" style={{ position: 'absolute', left: '50%', top: -2, fontSize: 10, color: 'var(--ink-3)', transform: 'translateX(-50%)' }}>$172</span>
          <span className="wf-tiny" style={{ position: 'absolute', left: '50%', top: 22, color: 'var(--ink-3)', transform: 'translateX(-50%)' }}>floor base</span>
          <div style={{ position: 'absolute', left: '78%', top: 4, width: 16, height: 16, background: 'var(--conv-high)', borderRadius: '50%', border: '2px solid var(--paper)' }} />
          <span className="wf-mono" style={{ position: 'absolute', left: '78%', top: -2, fontSize: 10, color: 'var(--conv-high)', fontWeight: 600, transform: 'translateX(-50%)' }}>$232</span>
          <span className="wf-tiny" style={{ position: 'absolute', left: '78%', top: 22, color: 'var(--conv-high)', fontWeight: 600, transform: 'translateX(-50%)' }}>thesis</span>
        </div>
      </div>
    </div>
    <div style={{ position: 'absolute', right: 24, top: 130, width: 200 }}>
      <div className="wf-postit" style={{ transform: 'rotate(2deg)' }}>wildcard — what-if as the FRONT door. live drift between thesis and floor as you scrub.</div>
    </div>
  </div>
);

// ────────────────────────────────────────────────────────────
// Drift treatments — 3 mini variants
// ────────────────────────────────────────────────────────────
const Drift1 = () => (
  <div className="wf" style={{ width: 460, minHeight: 200, padding: 16 }}>
    <div className="wf-eyebrow" style={{ marginBottom: 6 }}>1 · TEXT LABEL</div>
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
      <span className="wf-anno-tag" style={{ background: 'var(--conv-high-bg)', color: 'var(--conv-high)' }}>thesis above floor</span>
      <span className="wf-tiny wf-mono">engine corroborates · gap +33%</span>
    </div>
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
      <span className="wf-anno-tag" style={{ background: 'var(--paper-2)', color: 'var(--ink-3)' }}>engine corroborates</span>
      <span className="wf-tiny wf-mono">thesis $220 ≈ floor base $215</span>
    </div>
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <span className="wf-anno-tag" style={{ background: 'var(--conv-broken-bg)', color: 'var(--conv-broken)' }}>thesis below floor</span>
      <span className="wf-tiny wf-mono">red flag · gap −18%</span>
    </div>
    <div className="wf-tiny" style={{ marginTop: 10, color: 'var(--ink-3)' }}>
      simplest. no chart. status as language.
    </div>
  </div>
);

const Drift2 = () => (
  <div className="wf" style={{ width: 460, minHeight: 200, padding: 16 }}>
    <div className="wf-eyebrow" style={{ marginBottom: 10 }}>2 · DRIFT GAUGE</div>
    <div style={{ position: 'relative', height: 60, padding: '0 8px' }}>
      <div style={{ position: 'absolute', left: 8, right: 8, top: 30, borderTop: '1.5px solid var(--rule-soft)' }} />
      {/* zero gap */}
      <div style={{ position: 'absolute', left: '50%', top: 22, bottom: 22, borderLeft: '1px dashed var(--ink-3)' }} />
      <span className="wf-tiny" style={{ position: 'absolute', left: '50%', top: 4, transform: 'translateX(-50%)' }}>parity</span>
      {/* drift marker */}
      <div style={{
        position: 'absolute', left: '72%', top: 22, width: 16, height: 16,
        background: 'var(--conv-high)', borderRadius: '50%', border: '2px solid var(--paper)'
      }} />
      <span className="wf-mono" style={{ position: 'absolute', left: '72%', top: 44, transform: 'translateX(-50%)', fontSize: 11, fontWeight: 600, color: 'var(--conv-high)' }}>+33% above</span>
      <span className="wf-tiny" style={{ position: 'absolute', left: '8px', top: 44, color: 'var(--ink-3)' }}>thesis &lt; floor</span>
      <span className="wf-tiny" style={{ position: 'absolute', right: '8px', top: 44, color: 'var(--ink-3)' }}>thesis » floor</span>
    </div>
    <div className="wf-tiny" style={{ marginTop: 10, color: 'var(--ink-3)' }}>
      gauge — sign + magnitude on one axis. zero = engine corroborates.
    </div>
  </div>
);

const Drift3 = () => (
  <div className="wf" style={{ width: 460, minHeight: 200, padding: 16 }}>
    <div className="wf-eyebrow" style={{ marginBottom: 10 }}>3 · PRICE LADDER</div>
    <div style={{ position: 'relative', height: 140, paddingLeft: 80, paddingRight: 80 }}>
      <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, borderLeft: '1.5px solid var(--rule)' }} />
      {[
        { y: 20, label: 'THESIS', val: '$220', color: 'var(--conv-high)', side: 'r', big: true },
        { y: 60, label: 'FLOOR HIGH', val: '$240', color: 'var(--ink-3)', side: 'l' },
        { y: 90, label: 'FLOOR BASE', val: '$165', color: 'var(--ink-3)', side: 'l' },
        { y: 110, label: 'CURRENT', val: '$122', color: 'var(--ink)', side: 'r' },
        { y: 130, label: 'FLOOR LOW', val: '$95', color: 'var(--ink-3)', side: 'l' },
      ].map((m, i) => (
        <div key={i} style={{ position: 'absolute', left: 0, right: 0, top: m.y }}>
          <div style={{ position: 'absolute', left: 'calc(50% - 6px)', width: 12, height: 1.5, background: m.color, top: 4 }} />
          <span className="wf-mono" style={{
            position: 'absolute',
            [m.side === 'l' ? 'right' : 'left']: 'calc(50% + 12px)',
            fontSize: m.big ? 13 : 11, fontWeight: m.big ? 700 : 500, color: m.color
          }}>{m.label} {m.val}</span>
        </div>
      ))}
    </div>
    <div className="wf-tiny" style={{ marginTop: 6, color: 'var(--ink-3)' }}>
      ladder — every level on shared price axis. drift = vertical distance.
    </div>
  </div>
);

Object.assign(window, { ModelA, ModelB, ModelC, ModelD, Drift1, Drift2, Drift3 });
