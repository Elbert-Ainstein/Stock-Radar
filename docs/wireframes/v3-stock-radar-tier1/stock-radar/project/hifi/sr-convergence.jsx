/* hifi/sr-convergence.jsx
   New flows:
     1) Discovery (Convergence) — multi-class signal aggregation, 3 row variants
     2) Watchlist Convergence Refresh — top-section, 2 variants
   Plus: queue-thesis confirmation patterns, all states, all breakpoints.
   Uses ONLY existing tokens from hifi/tokens.css.
*/

const { useState: cvUseState } = React;

/* ============================================================
   Class taxonomy — single source of truth
   ============================================================ */
const CLASSES = {
  smart_money: { label: 'SMART MONEY', short: '13F',     ink: 'var(--conv-strong)',  bg: 'var(--conv-strong-bg)', heavy: true },
  insider:     { label: 'INSIDER',     short: 'INSIDER', ink: 'var(--info-ink)',     bg: 'var(--info-bg)',         heavy: true },
  news:        { label: 'NEWS',        short: 'NEWS',    ink: 'var(--conv-watch)',   bg: 'var(--conv-watch-bg)',   heavy: false },
  theme:       { label: 'THEME',       short: 'THEME',   ink: 'var(--conv-good)',    bg: 'var(--conv-good-bg)',    heavy: true },
  momentum:    { label: 'MOMENTUM',    short: 'MOM',     ink: 'var(--ink-3)',        bg: 'var(--paper-2)',         heavy: false, noisy: true },
  manual:      { label: 'MANUAL',      short: 'MANUAL',  ink: 'var(--ink-2)',        bg: 'var(--paper-2)',         heavy: false },
};

/* tier rule, encoded:
   STRONG: 3+ classes including {smart_money | theme}
   MEDIUM: 2+ classes OR 3+ noise-only classes
   SINGLE: exactly 1 class
*/
function deriveTier(classes) {
  const set = new Set(classes);
  if (set.size === 1) return 'single';
  const heavy = ['smart_money','theme'].some(k => set.has(k));
  if (set.size >= 3 && heavy) return 'strong';
  if (set.size >= 2) return 'medium';
  return 'single';
}

/* ============================================================
   Sample candidate dataset
   ============================================================ */
const CANDIDATES = [
  {
    tk: 'AVGO', class_count: 4, source_count: 9, cheap: 8.4, status: 'qualified',
    classes: ['smart_money','insider','news','theme'],
    why: {
      smart_money: 'Coatue + Lone Pine new positions in Q4 13F',
      insider:     'CFO + 2 directors bought $4.2M last 30d',
      news:        'Bullish earnings beat May 7; AI-ASIC TAM revised',
      theme:       'Hyperscaler accelerator scan — 8 peers flagged',
    },
  },
  {
    tk: 'NET', class_count: 3, source_count: 7, cheap: 7.6, status: 'promising',
    classes: ['smart_money','news','momentum'],
    why: {
      smart_money: 'D1 Capital initiated 1.4% position',
      news:        'Workers AI usage cited in Perplexity bullish',
      momentum:    'Yahoo most-active 2 sessions',
    },
  },
  {
    tk: 'ANET', class_count: 3, source_count: 8, cheap: 8.0, status: 'qualified',
    classes: ['smart_money','theme','news'],
    why: {
      smart_money: 'Tiger Global, Whale Rock — adds Q4',
      theme:       '800G optical scan — 4 peers flagged',
      news:        'Channel checks bullish, TD Cowen upgrade',
    },
  },
  {
    tk: 'TEAM', class_count: 2, source_count: 4, cheap: 6.2, status: 'promising',
    classes: ['insider','news'],
    why: {
      insider: 'Co-founder bought $1.1M; rare on-market buy',
      news:    'Cloud ARR mix re-accelerating per Perplexity',
    },
  },
  {
    tk: 'CFLT', class_count: 2, source_count: 3, cheap: 5.4, status: 'exploring',
    classes: ['smart_money','momentum'],
    why: {
      smart_money: 'Whale Rock Q4 position add',
      momentum:    'Yahoo gainers 2 sessions',
    },
  },
  {
    tk: 'SOFI', class_count: 1, source_count: 2, cheap: 3.8, status: 'exploring',
    classes: ['momentum'],
    why: {
      momentum: 'Yahoo most-active retail darling — low signal',
    },
  },
  {
    tk: 'SMCI', class_count: 1, source_count: 1, cheap: 2.4, status: 'exploring',
    classes: ['momentum'],
    why: {
      momentum: 'Yahoo gainers session-only',
    },
  },
];

/* ============================================================
   Tier badge — variants for the "loud vs same" question
   ============================================================ */
function TierBadge({ tier, loud = true, size = 'md' }) {
  const map = {
    strong: { ink: 'var(--conv-strong)', bg: 'var(--conv-strong-bg)', label: 'STRONG' },
    medium: { ink: 'var(--conv-watch)',  bg: 'var(--conv-watch-bg)',  label: 'MEDIUM' },
    single: { ink: 'var(--ink-3)',       bg: 'var(--paper-2)',        label: 'SINGLE' },
  };
  const m = map[tier];
  const sz = size === 'sm' ? { h: 18, px: 6, fs: 9.5 } : { h: 22, px: 8, fs: 10.5 };
  if (!loud) {
    // muted — same chrome for every tier, only ink color hints at importance
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center',
        height: sz.h, padding: `0 ${sz.px}px`,
        background: 'transparent',
        border: '1px solid var(--rule)',
        borderRadius: 3,
        fontFamily: 'var(--font-mono)', fontSize: sz.fs, fontWeight: 600,
        letterSpacing: '0.08em', color: m.ink,
      }}>{m.label}</span>
    );
  }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      height: sz.h, padding: `0 ${sz.px}px`,
      background: m.bg,
      borderRadius: 3,
      fontFamily: 'var(--font-mono)', fontSize: sz.fs, fontWeight: 600,
      letterSpacing: '0.08em', color: m.ink,
    }}>{m.label}</span>
  );
}

/* ============================================================
   ClassChip — colored per signal class
   ============================================================ */
function ClassChip({ kind, size = 'sm', short }) {
  const c = CLASSES[kind] || CLASSES.manual;
  const sz = size === 'xs' ? { h: 16, px: 5, fs: 9 } : { h: 19, px: 6, fs: 10 };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      height: sz.h, padding: `0 ${sz.px}px`,
      background: c.bg, color: c.ink,
      borderRadius: 3,
      fontFamily: 'var(--font-mono)', fontSize: sz.fs, fontWeight: 600,
      letterSpacing: '0.06em',
      border: c.noisy ? '1px dashed var(--rule)' : 'none',
    }}>{short || c.short}</span>
  );
}

/* ============================================================
   QueueThesis button — two patterns
   pattern 'one-click' = one-click + toast (for promising)
   pattern 'two-click' = explicit modal (for high-cost confirm)
   ============================================================ */
function QueueThesisAction({ tk, pattern = 'one-click', size = 'sm', cheap }) {
  const [phase, setPhase] = cvUseState('idle'); // idle | confirming | toast
  const sz = size === 'sm' ? { h: 26, px: 9, fs: 11 } : { h: 30, px: 11, fs: 12 };

  if (phase === 'confirming') {
    return (
      <div style={{
        display: 'inline-flex', alignItems: 'stretch',
        border: '1px solid var(--ink)', borderRadius: 4,
        background: 'var(--paper)',
        boxShadow: 'var(--shadow-md)',
      }}>
        <span style={{ padding: '0 10px', display: 'inline-flex', alignItems: 'center', fontSize: 11, color: 'var(--ink-2)', borderRight: '1px solid var(--rule)' }}>~$3–5 · Opus run</span>
        <button onClick={() => setPhase('toast')} style={{
          ...primaryBtnX, height: sz.h, borderRadius: 0, border: 'none',
        }}>Confirm queue</button>
        <button onClick={() => setPhase('idle')} style={{
          height: sz.h, padding: '0 10px', background: 'transparent', border: 'none',
          fontSize: 11, color: 'var(--ink-3)', cursor: 'pointer',
        }}>Cancel</button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setPhase(pattern === 'two-click' ? 'confirming' : 'toast')}
      style={{
        ...primaryBtnX, height: sz.h, fontSize: sz.fs,
        background: phase === 'toast' ? 'var(--conv-strong)' : 'var(--action)',
      }}
    >
      <Icon name="zap" size={11} color={phase === 'toast' ? 'var(--paper)' : 'var(--action-ink)'} />
      {phase === 'toast' ? 'Queued' : 'Queue thesis run'}
    </button>
  );
}

const primaryBtnX = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '0 11px', background: 'var(--action)', color: 'var(--action-ink)',
  border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 500,
};
const ghostBtnX = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  height: 26, padding: '0 9px', background: 'var(--paper-1)',
  border: '1px solid var(--rule)', borderRadius: 4, cursor: 'pointer',
  fontSize: 11.5, color: 'var(--ink-1)',
};

/* ============================================================
   Discovery shared chrome
   ============================================================ */
function DiscoveryChrome({ variant, breakpoint = 'desktop', count = 7 }) {
  const isPhone = breakpoint === 'phone';
  return (
    <div style={{ borderBottom: '1px solid var(--rule)', background: 'var(--paper)' }}>
      <div style={{
        padding: isPhone ? '12px 14px' : '14px 22px',
        display: 'flex', flexDirection: isPhone ? 'column' : 'row',
        justifyContent: 'space-between', alignItems: isPhone ? 'flex-start' : 'center',
        gap: isPhone ? 10 : 0,
      }}>
        <div>
          <h1 style={{ fontSize: isPhone ? 16 : 18, fontWeight: 600 }}>Discovery</h1>
          <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
            Cross-source convergence · {count} candidates · last 24h
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          <StatePill tone="ok" size="sm">{count} new</StatePill>
          <StatePill tone="info" size="sm">2 qualified</StatePill>
          {!isPhone && <button style={ghostBtnX}><Icon name="filter" size={11} color="var(--ink-2)" />Filters</button>}
          {!isPhone && <button style={ghostBtnX}><Icon name="refresh" size={11} color="var(--ink-2)" />Re-feed</button>}
        </div>
      </div>
      {/* legend strip */}
      <div style={{
        padding: isPhone ? '6px 14px 8px' : '6px 22px 10px',
        display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
        fontSize: 10, color: 'var(--ink-3)',
      }}>
        <span className="eyebrow" style={{ marginRight: 4 }}>signal classes</span>
        {Object.keys(CLASSES).filter(k => k !== 'manual').map(k => <ClassChip key={k} kind={k} size="xs" />)}
      </div>
    </div>
  );
}

/* ============================================================
   VARIANT A — Bloomberg-tight table (one row per candidate)
   ============================================================ */
function DiscoveryA({ breakpoint = 'desktop', state = 'happy', loud = true }) {
  if (state === 'empty')   return <DiscoveryEmpty />;
  if (state === 'loading') return <DiscoverySkeletonTable />;
  if (state === 'error')   return <DiscoveryError />;

  const isPhone = breakpoint === 'phone';
  if (isPhone) return <DiscoveryB breakpoint="phone" state={state} loud={loud} />; // table can't fit

  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DiscoveryChrome variant="A" breakpoint={breakpoint} count={CANDIDATES.length} />
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-sans)' }}>
          <thead>
            <tr style={{ background: 'var(--paper-1)', borderBottom: '1px solid var(--rule)' }}>
              {['TICKER','TIER','CLASSES','SIGNAL','CHEAP','STATUS','ACTIONS'].map(h =>
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: 9.5, letterSpacing: '0.1em', color: 'var(--ink-3)', fontWeight: 500 }}>{h}</th>
              )}
            </tr>
          </thead>
          <tbody>
            {CANDIDATES.map((c, i) => {
              const tier = deriveTier(c.classes);
              return (
                <tr key={c.tk} style={{ borderBottom: '1px solid var(--rule-soft)', height: 32 }}>
                  <td style={{ padding: '0 12px', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>{c.tk}</td>
                  <td style={{ padding: '0 12px' }}><TierBadge tier={tier} loud={loud} size="sm" /></td>
                  <td style={{ padding: '0 12px' }}>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {c.classes.map(k => <ClassChip key={k} kind={k} size="xs" />)}
                    </div>
                  </td>
                  <td style={{ padding: '0 12px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-2)' }}>
                    {c.source_count} tags · {c.class_count} class{c.class_count === 1 ? '' : 'es'}
                  </td>
                  <td style={{ padding: '0 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: c.cheap >= 7 ? 'var(--conv-strong)' : c.cheap >= 5 ? 'var(--ink-1)' : 'var(--ink-3)', fontWeight: 600 }}>
                    {c.cheap.toFixed(1)}
                  </td>
                  <td style={{ padding: '0 12px' }}>
                    <span style={{ fontSize: 10.5, fontFamily: 'var(--font-mono)', color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{c.status}</span>
                  </td>
                  <td style={{ padding: '0 12px', textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', gap: 6 }}>
                      <button style={ghostBtnX}>Dismiss</button>
                      <QueueThesisAction tk={c.tk} pattern="one-click" />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ============================================================
   VARIANT B — Card per candidate, "why" reasons summarized
   ============================================================ */
function DiscoveryB({ breakpoint = 'desktop', state = 'happy', loud = true, confirmPattern = 'one-click' }) {
  if (state === 'empty')   return <DiscoveryEmpty />;
  if (state === 'loading') return <DiscoverySkeletonCards breakpoint={breakpoint} />;
  if (state === 'error')   return <DiscoveryError />;

  const isPhone = breakpoint === 'phone';
  const isTablet = breakpoint === 'tablet';
  const cols = isPhone ? 1 : isTablet ? 1 : 2;

  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DiscoveryChrome variant="B" breakpoint={breakpoint} count={CANDIDATES.length} />
      <div style={{ flex: 1, overflow: 'auto', padding: isPhone ? 12 : 16, display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 10, minHeight: 0 }}>
        {CANDIDATES.map((c, i) => {
          const tier = deriveTier(c.classes);
          const tierAccent = tier === 'strong' && loud;
          return (
            <article key={c.tk} style={{
              background: tierAccent ? 'var(--paper)' : 'var(--paper-1)',
              border: tierAccent ? '1px solid var(--conv-strong)' : '1px solid var(--rule)',
              borderLeft: tierAccent ? '3px solid var(--conv-strong)' : '1px solid var(--rule)',
              borderRadius: 6,
              padding: 14,
              display: 'flex', flexDirection: 'column', gap: 10,
            }}>
              <header style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: isPhone ? 16 : 18, fontWeight: 600 }}>{c.tk}</span>
                  <TierBadge tier={tier} loud={loud} size="sm" />
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{c.status}</span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: c.cheap >= 7 ? 'var(--conv-strong)' : 'var(--ink-1)' }}>{c.cheap.toFixed(1)}</div>
                  <div className="eyebrow" style={{ fontSize: 9 }}>cheap-score</div>
                </div>
              </header>

              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {c.classes.map(k => <ClassChip key={k} kind={k} />)}
                <span style={{ fontSize: 10.5, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', alignSelf: 'center', marginLeft: 4 }}>
                  {c.source_count} tags / {c.class_count} classes
                </span>
              </div>

              <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
                {c.classes.map(k => (
                  <li key={k} style={{ display: 'flex', gap: 8, fontSize: 12, color: 'var(--ink-1)', alignItems: 'flex-start' }}>
                    <span style={{ flex: '0 0 64px', fontFamily: 'var(--font-mono)', fontSize: 9.5, color: CLASSES[k].ink, textTransform: 'uppercase', letterSpacing: '0.06em', paddingTop: 3, fontWeight: 600 }}>{CLASSES[k].short}</span>
                    <span style={{ flex: 1, lineHeight: 1.45 }}>{c.why[k]}</span>
                  </li>
                ))}
              </ul>

              <footer style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', borderTop: '1px solid var(--rule-soft)', paddingTop: 10 }}>
                <button style={ghostBtnX}>Dismiss</button>
                <QueueThesisAction tk={c.tk} pattern={confirmPattern} />
              </footer>
            </article>
          );
        })}
      </div>
    </div>
  );
}

/* ============================================================
   VARIANT C — Pipeline ladder (Trello-style, tier × cheap)
   ============================================================ */
function DiscoveryC({ breakpoint = 'desktop', state = 'happy', loud = true }) {
  if (state === 'empty')   return <DiscoveryEmpty />;
  if (state === 'loading') return <DiscoverySkeletonCards breakpoint={breakpoint} />;
  if (state === 'error')   return <DiscoveryError />;

  const lanes = ['strong','medium','single'];
  const grouped = lanes.reduce((acc, L) => {
    acc[L] = CANDIDATES
      .map(c => ({ ...c, tier: deriveTier(c.classes) }))
      .filter(c => c.tier === L)
      .sort((a, b) => b.cheap - a.cheap);
    return acc;
  }, {});

  const isPhone = breakpoint === 'phone';

  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DiscoveryChrome variant="C" breakpoint={breakpoint} count={CANDIDATES.length} />
      <div style={{
        flex: 1, overflow: 'auto', padding: isPhone ? 10 : 16,
        display: 'grid',
        gridTemplateColumns: isPhone ? '1fr' : 'repeat(3, 1fr)',
        gap: 10, minHeight: 0,
      }}>
        {lanes.map(L => {
          const items = grouped[L];
          const meta = {
            strong: { label: 'STRONG', sub: '3+ classes incl. {smart_money | theme}', ink: 'var(--conv-strong)', bg: loud ? 'var(--conv-strong-bg)' : 'var(--paper-1)' },
            medium: { label: 'MEDIUM', sub: '2+ classes', ink: 'var(--conv-watch)', bg: loud ? 'var(--conv-watch-bg)' : 'var(--paper-1)' },
            single: { label: 'SINGLE', sub: '1 class — usually noise', ink: 'var(--ink-3)', bg: 'var(--paper-1)' },
          }[L];
          return (
            <section key={L} style={{
              background: meta.bg,
              border: '1px solid var(--rule)',
              borderRadius: 6,
              display: 'flex', flexDirection: 'column',
              minHeight: 0,
            }}>
              <header style={{
                padding: '10px 12px',
                borderBottom: '1px solid var(--rule-soft)',
                display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
              }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: meta.ink, letterSpacing: '0.1em' }}>{meta.label}</div>
                  <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>{meta.sub}</div>
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-2)' }}>{items.length}</span>
              </header>
              <div style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 6, overflow: 'auto' }}>
                {items.map(c => (
                  <div key={c.tk} style={{
                    background: 'var(--paper)',
                    border: '1px solid var(--rule)', borderRadius: 4,
                    padding: 10, display: 'flex', flexDirection: 'column', gap: 6,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600 }}>{c.tk}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: c.cheap >= 7 ? 'var(--conv-strong)' : 'var(--ink-2)', fontWeight: 600 }}>{c.cheap.toFixed(1)}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                      {c.classes.map(k => <ClassChip key={k} kind={k} size="xs" />)}
                    </div>
                    <div style={{ fontSize: 10.5, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{c.source_count} tags · {c.status}</div>
                    <div style={{ display: 'flex', gap: 5, marginTop: 2 }}>
                      <QueueThesisAction tk={c.tk} pattern="one-click" size="sm" />
                    </div>
                  </div>
                ))}
                {items.length === 0 && <div style={{ padding: 14, textAlign: 'center', fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>none in this tier</div>}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

/* ============================================================
   States — empty, loading skeletons, error
   ============================================================ */
function DiscoveryEmpty() {
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DiscoveryChrome variant="" count={0} />
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 30 }}>
        <div style={{
          maxWidth: 460, textAlign: 'center',
          padding: 28, border: '1px dashed var(--rule-strong)', borderRadius: 8,
          background: 'var(--paper-1)',
        }}>
          <div style={{ width: 36, height: 36, margin: '0 auto 12px', borderRadius: '50%', background: 'var(--paper-2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="search" size={16} color="var(--ink-3)" />
          </div>
          <h3 style={{ fontSize: 15, marginBottom: 6 }}>No candidates yet</h3>
          <p style={{ fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 14 }}>Run feeders to populate the convergence list. Each feeder pulls from its own source — 13F filings, Form-4 filings, news, sector themes, momentum signals.</p>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button style={primaryBtnX2}><Icon name="play" size={11} color="var(--action-ink)" />Run all feeders</button>
            <button style={ghostBtnX}>Configure sources</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function DiscoverySkeletonTable() {
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DiscoveryChrome variant="" count={0} />
      <div style={{ flex: 1, padding: 0, overflow: 'hidden' }}>
        <div style={{ background: 'var(--paper-1)', borderBottom: '1px solid var(--rule)', padding: '8px 12px', display: 'flex', gap: 32 }}>
          {['TICKER','TIER','CLASSES','SIGNAL','CHEAP','STATUS','ACTIONS'].map(h =>
            <span key={h} style={{ fontSize: 9.5, letterSpacing: '0.1em', color: 'var(--ink-3)', fontWeight: 500 }}>{h}</span>
          )}
        </div>
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', borderBottom: '1px solid var(--rule-soft)', height: 36 }}>
            <span className="sr-skel" style={{ width: 50,  height: 14 }} />
            <span className="sr-skel" style={{ width: 70,  height: 14 }} />
            <span className="sr-skel" style={{ width: 200, height: 14 }} />
            <span className="sr-skel" style={{ width: 130, height: 12 }} />
            <span className="sr-skel" style={{ width: 30,  height: 12 }} />
            <span className="sr-skel" style={{ width: 60,  height: 10 }} />
            <span className="sr-skel" style={{ width: 140, height: 18, marginLeft: 'auto' }} />
          </div>
        ))}
        <div style={{ padding: '14px 22px', display: 'flex', alignItems: 'center', gap: 10, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--info-ink)', animation: 'sr-shimmer 1.4s linear infinite' }}></span>
          running 3 feeders · ETA ~25s
        </div>
      </div>
    </div>
  );
}

function DiscoverySkeletonCards({ breakpoint = 'desktop' }) {
  const isPhone = breakpoint === 'phone';
  const cols = isPhone ? 1 : 2;
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DiscoveryChrome variant="" count={0} />
      <div style={{ flex: 1, padding: 16, display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 10 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} style={{ background: 'var(--paper-1)', border: '1px solid var(--rule)', borderRadius: 6, padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <span className="sr-skel" style={{ width: 80, height: 18 }} />
            <span className="sr-skel" style={{ width: 200, height: 12 }} />
            <span className="sr-skel" style={{ width: '100%', height: 12 }} />
            <span className="sr-skel" style={{ width: '90%', height: 12 }} />
            <span className="sr-skel" style={{ width: '60%', height: 12 }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function DiscoveryError() {
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <DiscoveryChrome variant="" count={0} />
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 30 }}>
        <div style={{
          maxWidth: 540, padding: 22,
          background: 'var(--paper-1)', border: '1px solid var(--err-ink)',
          borderRadius: 8,
        }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--err-bg)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flex: '0 0 28px' }}>
              <Icon name="bell" size={14} color="var(--err-ink)" />
            </div>
            <div>
              <h3 style={{ fontSize: 14, marginBottom: 4 }}>2 of 5 feeders failed</h3>
              <p style={{ fontSize: 12, color: 'var(--ink-2)' }}>Other feeders completed — partial results below. SEC EDGAR rate-limit hit at 14:22 ET; Yahoo timed out twice.</p>
            </div>
          </div>
          <div style={{ background: 'var(--paper-2)', border: '1px solid var(--rule-soft)', borderRadius: 4, padding: 8, fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--ink-1)', marginBottom: 10 }}>
            <div>[14:22:18] feeder.smart_money: 429 from edgar — backing off 60s</div>
            <div>[14:22:31] feeder.momentum: TimeoutError after 30s</div>
            <div style={{ color: 'var(--err-ink)' }}>[14:22:41] both feeders failed permanently for this run</div>
          </div>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            <button style={ghostBtnX}>View partial results</button>
            <button style={primaryBtnX2}>Retry failed feeders</button>
          </div>
        </div>
      </div>
    </div>
  );
}

const primaryBtnX2 = { ...primaryBtnX, height: 28, fontSize: 12 };

/* ============================================================
   Master Discovery artboard — accepts variant + breakpoint + state
   ============================================================ */
function DiscoveryConvergenceArtboard({ variant = 'B', breakpoint = 'desktop', state = 'happy', loud = true, confirmPattern = 'one-click' }) {
  if (variant === 'A') return <DiscoveryA breakpoint={breakpoint} state={state} loud={loud} />;
  if (variant === 'C') return <DiscoveryC breakpoint={breakpoint} state={state} loud={loud} />;
  return <DiscoveryB breakpoint={breakpoint} state={state} loud={loud} confirmPattern={confirmPattern} />;
}

/* ============================================================
   WATCHLIST CONVERGENCE REFRESH — top-section component
   ============================================================ */
const REFRESH_ITEMS = [
  {
    tk: 'CRWD', class_count: 3, when: '6h ago',
    classes: ['smart_money','insider','news'],
    diff: '+1 new 13F manager · insider $2.1M last 30d · earnings beat 6h ago',
  },
  {
    tk: 'NVDA', class_count: 2, when: '12h ago',
    classes: ['smart_money','theme'],
    diff: '+2 13F managers Q4 · hyperscaler scan re-flagged',
  },
  {
    tk: 'META', class_count: 2, when: '1d ago',
    classes: ['insider','news'],
    diff: 'Director buy $1.4M · Reels monetization upside per channel',
  },
  {
    tk: 'PLTR', class_count: 1, when: '2d ago',
    classes: ['momentum'],
    diff: 'Yahoo gainers 3 sessions — low quality',
  },
];

function ConvergenceRefreshA({ breakpoint = 'desktop', state = 'happy' }) {
  // Inline horizontal strip
  if (state === 'empty') return <RefreshEmptyInline />;

  const isPhone = breakpoint === 'phone';
  return (
    <section style={{
      background: 'var(--paper-1)',
      borderBottom: '1px solid var(--rule)',
      padding: isPhone ? '10px 12px 12px' : '12px 22px 14px',
    }}>
      <header style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span className="eyebrow">Fresh signal · last 30d</span>
          <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{REFRESH_ITEMS.length} on watchlist</span>
        </div>
        <a style={{ fontSize: 11, color: 'var(--link)', cursor: 'pointer' }}>See all</a>
      </header>
      <div style={{
        display: 'flex', gap: 8,
        overflowX: 'auto',
        scrollSnapType: 'x mandatory',
        paddingBottom: 4,
      }}>
        {REFRESH_ITEMS.map(it => (
          <article key={it.tk} style={{
            flex: '0 0 auto',
            width: isPhone ? 240 : 260,
            scrollSnapAlign: 'start',
            background: 'var(--paper)',
            border: '1px solid var(--rule)',
            borderRadius: 6,
            padding: 10,
            display: 'flex', flexDirection: 'column', gap: 6,
          }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>{it.tk}</span>
              <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{it.when}</span>
            </div>
            <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              {it.classes.map(k => <ClassChip key={k} kind={k} size="xs" />)}
            </div>
            <p style={{ fontSize: 11.5, color: 'var(--ink-1)', lineHeight: 1.4 }}>{it.diff}</p>
            <div style={{ display: 'flex', gap: 4, marginTop: 2 }}>
              <button style={{ ...primaryBtnX, height: 24, fontSize: 11 }}>Open</button>
              <button style={{ ...ghostBtnX, height: 24, fontSize: 10.5 }}>What changed</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function RefreshEmptyInline() {
  return (
    <section style={{ background: 'var(--paper-1)', borderBottom: '1px solid var(--rule)', padding: '14px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--ink-2)', fontStyle: 'italic', fontSize: 12.5 }}>
        <Icon name="bell" size={12} color="var(--ink-3)" />
        Watchlist quiet — no fresh signal in the last 30 days.
      </div>
    </section>
  );
}

function ConvergenceRefreshB({ breakpoint = 'desktop', state = 'happy' }) {
  // Sticky right rail — meant to live beside the watchlist table
  if (state === 'empty') {
    return (
      <aside style={railStyle}>
        <header style={railHeader}>
          <span className="eyebrow">Fresh signal · 30d</span>
        </header>
        <div style={{ padding: '20px 14px', textAlign: 'center', fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>
          Watchlist quiet — no fresh signal.
        </div>
      </aside>
    );
  }
  return (
    <aside style={railStyle}>
      <header style={railHeader}>
        <span className="eyebrow">Fresh signal · 30d</span>
        <span style={{ fontSize: 10.5, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{REFRESH_ITEMS.length}</span>
      </header>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {REFRESH_ITEMS.map((it, i) => (
          <div key={it.tk} style={{
            padding: '10px 12px',
            borderBottom: '1px solid var(--rule-soft)',
            display: 'flex', flexDirection: 'column', gap: 5,
            cursor: 'pointer',
          }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>{it.tk}</span>
              <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{it.when}</span>
            </div>
            <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              {it.classes.map(k => <ClassChip key={k} kind={k} size="xs" />)}
            </div>
            <p style={{ fontSize: 11, color: 'var(--ink-1)', lineHeight: 1.4 }}>{it.diff}</p>
          </div>
        ))}
      </div>
    </aside>
  );
}
const railStyle = { width: 280, background: 'var(--paper-1)', borderLeft: '1px solid var(--rule)', display: 'flex', flexDirection: 'column' };
const railHeader = { padding: '10px 12px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' };

/* Demo artboard wrapping the existing watchlist with the refresh strip
   ============================================================ */
function WatchlistWithRefresh({ variant = 'A', breakpoint = 'desktop', refreshState = 'happy' }) {
  if (variant === 'B') {
    // Right-rail layout
    return (
      <div className="sr sr-artboard" style={{ display: 'flex', minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <WatchlistArtboard breakpoint={breakpoint} state="happy" defaultView="list" />
        </div>
        <ConvergenceRefreshB breakpoint={breakpoint} state={refreshState} />
      </div>
    );
  }
  // Inline strip on top
  return (
    <div className="sr sr-artboard" style={{ display: 'flex', flexDirection: 'column' }}>
      <ConvergenceRefreshA breakpoint={breakpoint} state={refreshState} />
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <WatchlistArtboard breakpoint={breakpoint} state="happy" defaultView="list" />
      </div>
    </div>
  );
}

window.DiscoveryConvergenceArtboard = DiscoveryConvergenceArtboard;
window.WatchlistWithRefresh = WatchlistWithRefresh;
window.TierBadge = TierBadge;
window.ClassChip = ClassChip;
