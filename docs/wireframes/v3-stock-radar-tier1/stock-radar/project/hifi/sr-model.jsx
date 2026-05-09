/* hifi/sr-model.jsx — Model detail: Thesis tab + Floor (DCF) tab.
   Headline / Floor language is enforced visually:
   thesis tab uses full-bleed layouts and the action color;
   floor tab uses muted chrome, dashed borders, italic numerals.
*/

const { useState: mdUseState } = React;

function ModelDetailArtboard({ tab = 'thesis' }) {
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <ModelHeader tab={tab} />
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {tab === 'thesis' ? <ThesisTab /> : <FloorTab />}
      </div>
    </div>
  );
}

function ModelHeader({ tab }) {
  return (
    <div style={{ background: 'var(--paper)', borderBottom: '1px solid var(--rule)' }}>
      <div style={{ padding: '12px 22px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: 'var(--ink-3)' }}>
          <a style={{ cursor: 'pointer', textDecoration: 'none', color: 'var(--ink-3)' }}>← Models</a>
          <span>/</span>
          <span style={{ color: 'var(--ink-2)' }}>equity-thesis-v3.2</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <StatePill tone="ok" size="sm">healthy</StatePill>
          <button style={ghostBtn3}><Icon name="setting" size={12} color="var(--ink-2)"/>Configure</button>
          <button style={ghostBtn3}><Icon name="refresh" size={12} color="var(--ink-2)"/>Run on watchlist</button>
        </div>
      </div>
      <div style={{ padding: '4px 22px 0', display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
            <h1 style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.015em' }}>equity-thesis-v3.2</h1>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)' }}>v3.2.4 · last edit 2d ago</span>
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--ink-2)', marginTop: 4, maxWidth: 720 }}>Thesis-first model. Reasoned headline & conviction is the output; DCF is the floor — secondary input only.</p>
        </div>
        <nav style={{ display: 'flex', gap: 0 }}>
          {[
            { k: 'thesis', n: 'Thesis', primary: true },
            { k: 'floor',  n: 'Floor (DCF)' },
            { k: 'inputs', n: 'Inputs' },
            { k: 'runs',   n: 'Runs' },
            { k: 'tests',  n: 'Eval' },
          ].map(t => {
            const a = t.k === tab;
            return (
              <a key={t.k} style={{
                padding: '10px 14px', fontSize: 12.5, cursor: 'pointer',
                color: a ? 'var(--ink)' : 'var(--ink-2)',
                fontWeight: a ? 600 : 500,
                borderBottom: a ? '2px solid var(--ink)' : '2px solid transparent',
                display: 'inline-flex', alignItems: 'center', gap: 6,
              }}>
                {t.primary && <span style={{ width: 5, height: 5, borderRadius: '50%', background: a ? 'var(--ink)' : 'var(--ink-3)' }}/>}
                {t.n}
              </a>
            );
          })}
        </nav>
      </div>
    </div>
  );
}

/* ============= THESIS TAB ============= */
function ThesisTab() {
  return (
    <div style={{ padding: 22, display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18 }}>
      {/* Main */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        {/* Pipeline */}
        <section style={surfaceStyle3}>
          <SectionHeader3 eyebrow="Pipeline · what this model does">Reasoning chain</SectionHeader3>
          <div style={{ padding: '16px 18px 18px', display: 'flex', alignItems: 'center', gap: 6, overflowX: 'auto' }}>
            {[
              { n: 'Fundamentals', sub: '12mo · 247 pts', icon: 'list' },
              { n: 'Cohort comp',  sub: '8 peers',        icon: 'grid' },
              { n: 'Transcript reasoning', sub: 'last 4 calls', icon: 'note' },
              { n: 'Thesis synthesis', sub: 'headline · target · kill', icon: 'target', hi: true },
              { n: 'Conviction calibration', sub: '5-level', icon: 'star' },
            ].map((s, i, arr) => (
              <React.Fragment key={i}>
                <div style={{
                  flex: '1 1 0', minWidth: 130,
                  padding: '10px 12px',
                  background: s.hi ? 'var(--conv-strong-bg)' : 'var(--paper-1)',
                  border: s.hi ? '1px solid var(--conv-strong)' : '1px solid var(--rule-soft)',
                  borderRadius: 5,
                  display: 'flex', flexDirection: 'column', gap: 4,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Icon name={s.icon} size={12} color={s.hi ? 'var(--conv-strong)' : 'var(--ink-2)'} />
                    <span style={{ fontSize: 12, fontWeight: 600, color: s.hi ? 'var(--conv-strong)' : 'var(--ink-1)' }}>{s.n}</span>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{s.sub}</span>
                </div>
                {i < arr.length - 1 && <Icon name="chevR" size={12} color="var(--ink-3)" />}
              </React.Fragment>
            ))}
          </div>
        </section>

        {/* Prompt scaffold */}
        <section style={surfaceStyle3}>
          <SectionHeader3 eyebrow="Thesis prompt · system" right={<button style={ghostBtn3}><Icon name="edit" size={11} color="var(--ink-2)"/>Edit</button>}>
            What we ask the model to produce
          </SectionHeader3>
          <pre style={{
            margin: 0, padding: '14px 18px',
            fontFamily: 'var(--font-mono)', fontSize: 11.5, lineHeight: 1.55,
            color: 'var(--ink-1)', background: 'var(--paper-1)',
            borderTop: '1px solid var(--rule-soft)',
            whiteSpace: 'pre-wrap',
            maxHeight: 240, overflow: 'auto',
          }}>
{`You are an equity analyst building a 9–14mo thesis.
Output the headline first; floor (DCF) is provided
separately and is NOT your job.

Required fields:
  • thesis: <≤30 words, must be falsifiable>
  • target: <USD price, single number>
  • kill:   <USD price below which thesis is broken>
  • conviction: STRONG | GOOD | WATCH | FADING | BROKEN
  • setup, risks (3), catalysts (3), horizon

Hard rules:
  • Never anchor on the DCF base case
  • Identify the diagnostic that must hit by next print
  • If conviction < GOOD, recommend WATCH not BUY`}
          </pre>
        </section>

        {/* Output spec */}
        <section style={surfaceStyle3}>
          <SectionHeader3 eyebrow="Output schema">Fields produced per run</SectionHeader3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
            {[
              { k: 'thesis',     t: 'string · headline', hi: true },
              { k: 'target',     t: 'number · USD', hi: true },
              { k: 'kill',       t: 'number · USD' },
              { k: 'conviction', t: 'enum · 5 levels', hi: true },
              { k: 'horizon',    t: 'string · "9–14 mo"' },
              { k: 'setup',      t: 'string[]' },
              { k: 'risks',      t: 'string[3]' },
              { k: 'catalysts',  t: 'string[3]' },
              { k: 'diagnostic', t: 'string · falsifier' },
              { k: 'memory_tag', t: 'string · semantic key' },
            ].map((f, i) => (
              <div key={f.k} style={{
                display: 'flex', justifyContent: 'space-between',
                padding: '9px 14px',
                borderBottom: '1px solid var(--rule-soft)',
                borderRight: i % 2 === 0 ? '1px solid var(--rule-soft)' : 'none',
                background: f.hi ? 'var(--conv-strong-bg)' : 'transparent',
              }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: f.hi ? 'var(--conv-strong)' : 'var(--ink-1)', fontWeight: f.hi ? 600 : 500 }}>{f.k}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)' }}>{f.t}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* Side */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
        <section style={surfaceStyle3}>
          <SectionHeader3 eyebrow="Last 7d performance" small>How thesis tracks</SectionHeader3>
          <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <Stat label="Runs"          value="142" />
            <Stat label="Avg latency"   value="74s" />
            <Stat label="Failure rate"  value="2.1%" tone="warn" />
            <Stat label="Drift (thesis vs floor)" value="+18.4%" tone="ok" />
          </div>
        </section>

        <section style={{ ...surfaceStyle3, borderStyle: 'dashed', opacity: 0.95 }}>
          <SectionHeader3 eyebrow="Floor input · DCF · secondary" small>Linked from /floor</SectionHeader3>
          <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--ink-3)' }}>WACC</span>
              <span className="num mono" style={{ color: 'var(--ink-3)' }}>9.2%</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--ink-3)' }}>Terminal g</span>
              <span className="num mono" style={{ color: 'var(--ink-3)' }}>3.0%</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--ink-3)' }}>Horizon</span>
              <span className="num mono" style={{ color: 'var(--ink-3)' }}>5y</span>
            </div>
            <div style={{ paddingTop: 8, borderTop: '1px solid var(--rule-soft)' }}>
              <a style={{ fontSize: 11.5, color: 'var(--link)', cursor: 'pointer' }}>Open Floor tab →</a>
            </div>
          </div>
        </section>

        <section style={surfaceStyle3}>
          <SectionHeader3 eyebrow="Recent runs" small>Last 6 outputs</SectionHeader3>
          <div>
            {[
              { tk: 'CRWD', t: '4h ago', conv: 'strong', tg: 220, ok: true },
              { tk: 'NVDA', t: '12m ago', conv: 'strong', tg: 1180, ok: true },
              { tk: 'META', t: '1d ago',  conv: 'good',   tg: 620,  ok: true },
              { tk: 'PLTR', t: '5h ago',  conv: 'watch',  tg: 32,   ok: true },
              { tk: 'ROKU', t: '2d ago',  conv: 'fade',   tg: 78,   ok: true },
              { tk: 'PYPL', t: '12d ago', conv: 'broken', tg: 72,   ok: false },
            ].map((r, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderTop: i ? '1px solid var(--rule-soft)' : 'none' }}>
                <span style={{ flex: '0 0 50px', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600 }}>{r.tk}</span>
                <ConvictionBadge level={r.conv} size="xs"/>
                <span style={{ flex: 1 }}/>
                <MoneyValue value={r.tg} size={12} weight={500} decimals={0}/>
                <span style={{ fontSize: 10.5, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{r.t}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ============= FLOOR TAB ============= */
function FloorTab() {
  return (
    <div style={{ padding: 22, background: 'var(--paper-1)' }}>
      {/* Banner reinforcing role */}
      <div style={{
        padding: '10px 14px', marginBottom: 16,
        background: 'var(--paper-2)', border: '1px dashed var(--rule-strong)', borderRadius: 5,
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <Icon name="bell" size={14} color="var(--ink-2)"/>
        <span style={{ fontSize: 12.5, color: 'var(--ink-1)' }}>
          <strong style={{ color: 'var(--ink)' }}>Floor is a guard rail, not the headline.</strong> Used by the thesis prompt only as a "below-which" reference. Don't optimize toward this number.
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <section style={surfaceStyle3}>
            <SectionHeader3 eyebrow="DCF · base/bull/bear">Three-case output</SectionHeader3>
            <div style={{ padding: '16px 18px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              {[
                { k: 'Bear', v: 128, w: '20%', col: 'var(--conv-broken)' },
                { k: 'Base', v: 165, w: '60%', col: 'var(--ink-2)' },
                { k: 'Bull', v: 195, w: '20%', col: 'var(--conv-strong)' },
              ].map(c => (
                <div key={c.k} style={{ padding: 14, border: '1px dashed var(--rule)', background: 'var(--paper)', borderRadius: 5 }}>
                  <div className="eyebrow" style={{ marginBottom: 4 }}>{c.k} · weight {c.w}</div>
                  <div className="num mono" style={{ fontSize: 22, fontWeight: 500, fontStyle: 'italic', color: c.col }}>${c.v}</div>
                  <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 6 }}>WACC 9.2% · g 3.0%</div>
                </div>
              ))}
            </div>
          </section>

          <section style={surfaceStyle3}>
            <SectionHeader3 eyebrow="Inputs">Sensitivity grid</SectionHeader3>
            <div style={{ padding: 16, overflow: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                <thead>
                  <tr>
                    <th style={{ padding: '6px 8px', textAlign: 'left', color: 'var(--ink-3)', fontWeight: 500 }}>g \ WACC</th>
                    {[8, 9, 10, 11, 12].map(w => <th key={w} style={{ padding: '6px 10px', color: 'var(--ink-3)', fontWeight: 500 }}>{w}.0%</th>)}
                  </tr>
                </thead>
                <tbody>
                  {[2.0, 2.5, 3.0, 3.5, 4.0].map(g => (
                    <tr key={g}>
                      <td style={{ padding: '5px 8px', color: 'var(--ink-3)' }}>{g.toFixed(1)}%</td>
                      {[8, 9, 10, 11, 12].map(w => {
                        const v = Math.round(165 * (10 / w) * (1 + (g - 3) * 0.07));
                        const isBase = g === 3.0 && w === 9;
                        return (
                          <td key={w} style={{
                            padding: '5px 10px', textAlign: 'right',
                            color: isBase ? 'var(--conv-strong)' : 'var(--ink-2)',
                            fontWeight: isBase ? 600 : 400,
                            background: isBase ? 'var(--conv-strong-bg)' : 'transparent',
                            fontStyle: isBase ? 'normal' : 'italic',
                          }}>${v}</td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <section style={surfaceStyle3}>
            <SectionHeader3 eyebrow="Thesis (linked)" small>Headline · primary</SectionHeader3>
            <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Target</span>
                <MoneyValue value={220} size={18} weight={600} color="var(--conv-strong)" />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Drift vs floor</span>
                <DriftChip thesis={220} dcf={165} current={122.4} size="sm" />
              </div>
              <a style={{ fontSize: 11.5, color: 'var(--link)', cursor: 'pointer' }}>Open Thesis tab →</a>
            </div>
          </section>

          <section style={surfaceStyle3}>
            <SectionHeader3 eyebrow="Floor inputs" small>Tunable parameters</SectionHeader3>
            <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { l: 'WACC',         v: '9.2', u: '%' },
                { l: 'Terminal g',   v: '3.0', u: '%' },
                { l: 'Forecast yrs', v: '5',   u: '' },
                { l: 'Margin floor', v: '21',  u: '%' },
                { l: 'Capex/rev',    v: '4.5', u: '%' },
              ].map(r => (
                <div key={r.l} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ flex: 1, fontSize: 12, color: 'var(--ink-2)' }}>{r.l}</span>
                  <input defaultValue={r.v} style={{
                    width: 60, padding: '5px 8px',
                    border: '1px solid var(--rule)', borderRadius: 4,
                    fontFamily: 'var(--font-mono)', fontSize: 12,
                    textAlign: 'right', background: 'var(--paper)', color: 'var(--ink-1)',
                  }}/>
                  <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', width: 16 }}>{r.u}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

/* helpers */
const surfaceStyle3 = { background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 6, overflow: 'hidden' };
const ghostBtn3 = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  height: 26, padding: '0 9px', background: 'var(--paper-1)',
  border: '1px solid var(--rule)', borderRadius: 4, cursor: 'pointer',
  fontSize: 11.5, color: 'var(--ink-1)', fontFamily: 'var(--font-sans)',
};

function SectionHeader3({ eyebrow, children, right, small }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: small ? '10px 14px 6px' : '14px 18px 8px', borderBottom: '1px solid var(--rule-soft)', gap: 12 }}>
      <div>
        <div className="eyebrow" style={{ marginBottom: 3 }}>{eyebrow}</div>
        <h3 style={{ fontSize: small ? 13 : 15, fontWeight: 600 }}>{children}</h3>
      </div>
      {right}
    </div>
  );
}

function Stat({ label, value, tone }) {
  const ink = tone === 'ok' ? 'var(--pos)' : tone === 'warn' ? 'var(--conv-fade)' : 'var(--ink-1)';
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
      <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{label}</span>
      <span className="num mono" style={{ fontSize: 14, fontWeight: 500, color: ink }}>{value}</span>
    </div>
  );
}

window.ModelDetailArtboard = ModelDetailArtboard;
