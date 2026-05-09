/* hifi/sr-atoms.jsx — production atoms shared across views */

const { useState, useEffect, useRef, useMemo } = React;

/* =====================================================================
   ConvictionBadge — emerald/lime/amber/orange/red + broken
   ===================================================================== */
function ConvictionBadge({ level, size = 'md', label }) {
  const map = {
    strong: { bg: 'var(--conv-strong-bg)', ink: 'var(--conv-strong)', label: 'STRONG' },
    good:   { bg: 'var(--conv-good-bg)',   ink: 'var(--conv-good)',   label: 'GOOD' },
    watch:  { bg: 'var(--conv-watch-bg)',  ink: 'var(--conv-watch)',  label: 'WATCH' },
    fade:   { bg: 'var(--conv-fade-bg)',   ink: 'var(--conv-fade)',   label: 'FADING' },
    broken: { bg: 'var(--conv-broken-bg)', ink: 'var(--conv-broken)', label: 'BROKEN' },
  };
  const c = map[level] || map.watch;
  const sz = {
    xs: { px: 6,  py: 1,  fs: 9,  ls: 0.1, mr: 4,  dot: 5 },
    sm: { px: 7,  py: 2,  fs: 10, ls: 0.1, mr: 5,  dot: 6 },
    md: { px: 9,  py: 3,  fs: 11, ls: 0.12, mr: 6, dot: 7 },
    lg: { px: 12, py: 5,  fs: 12, ls: 0.14, mr: 7, dot: 8 },
  }[size];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: sz.mr,
      padding: `${sz.py}px ${sz.px}px`,
      background: c.bg, color: c.ink,
      fontFamily: 'var(--font-mono)',
      fontSize: sz.fs, fontWeight: 600,
      letterSpacing: `${sz.ls}em`,
      borderRadius: 3, lineHeight: 1, textTransform: 'uppercase'
    }}>
      <span style={{
        width: sz.dot, height: sz.dot, borderRadius: '50%',
        background: c.ink, flex: '0 0 auto'
      }} />
      {label || c.label}
    </span>
  );
}

/* =====================================================================
   MoneyValue — tabular nums, optional delta
   ===================================================================== */
function MoneyValue({ value, currency = '$', decimals = 2, size = 14, weight = 500, color, prefix }) {
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  const fmt = abs.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return (
    <span className="num mono" style={{
      fontSize: size, fontWeight: weight, color: color || 'var(--ink)',
      letterSpacing: '-0.01em', whiteSpace: 'nowrap'
    }}>{prefix}{sign}{currency}{fmt}</span>
  );
}

function PctValue({ value, decimals = 2, size = 13, weight = 500, signed = true, color }) {
  const c = color || (value > 0 ? 'var(--pos)' : value < 0 ? 'var(--neg)' : 'var(--neutral)');
  const sign = signed ? (value > 0 ? '+' : value < 0 ? '−' : '') : '';
  const v = Math.abs(value).toFixed(decimals);
  return (
    <span className="num mono" style={{ fontSize: size, fontWeight: weight, color: c, whiteSpace: 'nowrap' }}>
      {sign}{v}%
    </span>
  );
}

/* =====================================================================
   Sparkline — tiny SVG, deterministic path, with last-point dot
   ===================================================================== */
function Sparkline({ data, width = 80, height = 22, stroke, fill, hi = false, dot = true }) {
  if (!data || data.length < 2) return <svg width={width} height={height} />;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const stepX = width / (data.length - 1);
  const pts = data.map((v, i) => [i * stepX, height - 2 - ((v - min) / span) * (height - 4)]);
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const trend = data[data.length - 1] - data[0];
  const c = stroke || (trend >= 0 ? 'var(--pos)' : 'var(--neg)');
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
      {fill && (
        <path d={`${path} L${width.toFixed(1)} ${height} L0 ${height} Z`} fill={c} opacity="0.12" />
      )}
      <path d={path} stroke={c} strokeWidth={hi ? 1.5 : 1.25} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {dot && <circle cx={last[0]} cy={last[1]} r="1.75" fill={c} />}
    </svg>
  );
}

/* =====================================================================
   RunButton — multi-state: idle / queued / running / done / error / stale
   ===================================================================== */
function RunButton({ state = 'idle', size = 'md', onClick, label, lastRun }) {
  const sizes = {
    sm: { h: 24, px: 9,  fs: 11, ic: 11 },
    md: { h: 30, px: 12, fs: 12, ic: 13 },
    lg: { h: 36, px: 16, fs: 13, ic: 14 },
  };
  const s = sizes[size];
  const stateMap = {
    idle:    { lbl: 'Run thesis',     bg: 'var(--action)',    ink: 'var(--action-ink)', icon: 'play', dim: false },
    queued:  { lbl: 'Queued…',        bg: 'var(--paper-2)',   ink: 'var(--ink-2)',      icon: 'clock', dim: true },
    running: { lbl: 'Running 47s',    bg: 'var(--paper-2)',   ink: 'var(--ink-1)',      icon: 'spin',  dim: false },
    done:    { lbl: 'Re-run',         bg: 'var(--paper-1)',   ink: 'var(--ink-1)',      icon: 'check', dim: false },
    error:   { lbl: 'Retry',          bg: 'var(--err-bg)',    ink: 'var(--err-ink)',    icon: 'warn',  dim: false },
    stale:   { lbl: 'Re-run · stale', bg: 'var(--warn-bg)',   ink: 'var(--warn-ink)',   icon: 'play',  dim: false },
  };
  const cfg = stateMap[state];
  const Icon = () => {
    const w = s.ic;
    if (cfg.icon === 'play')  return <svg width={w} height={w} viewBox="0 0 16 16"><path d="M5 3l8 5-8 5V3z" fill="currentColor"/></svg>;
    if (cfg.icon === 'clock') return <svg width={w} height={w} viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" stroke="currentColor" fill="none" strokeWidth="1.4"/><path d="M8 4.5V8l2.5 1.5" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round"/></svg>;
    if (cfg.icon === 'spin')  return <svg width={w} height={w} viewBox="0 0 16 16" style={{ animation: 'sr-spin 1s linear infinite' }}><circle cx="8" cy="8" r="6" stroke="currentColor" fill="none" strokeWidth="1.5" strokeDasharray="14 24" strokeLinecap="round"/></svg>;
    if (cfg.icon === 'check') return <svg width={w} height={w} viewBox="0 0 16 16"><path d="M3 8.5l3.5 3.5L13 5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>;
    if (cfg.icon === 'warn')  return <svg width={w} height={w} viewBox="0 0 16 16"><path d="M8 2l6.5 11.5h-13L8 2z" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinejoin="round"/><path d="M8 6.5v3.5M8 12v.01" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>;
    return null;
  };
  return (
    <button onClick={onClick} style={{
      display: 'inline-flex', alignItems: 'center', gap: 7,
      height: s.h, padding: `0 ${s.px}px`,
      background: cfg.bg, color: cfg.ink,
      border: state === 'stale' || state === 'error' ? '1px solid currentColor' : '1px solid transparent',
      borderRadius: 5, cursor: 'pointer',
      fontFamily: 'var(--font-sans)', fontSize: s.fs, fontWeight: 500,
      letterSpacing: '-0.005em', opacity: cfg.dim ? 0.85 : 1,
      transition: 'background 120ms, transform 80ms',
    }}><Icon />{label || cfg.lbl}{lastRun && state === 'done' && <span style={{ color: 'var(--ink-3)', fontSize: s.fs - 1, marginLeft: 4 }}>· {lastRun}</span>}</button>
  );
}

/* =====================================================================
   ViewToggle — segmented, accessible
   ===================================================================== */
function ViewToggle({ value, onChange, options }) {
  return (
    <div role="radiogroup" style={{
      display: 'inline-flex',
      background: 'var(--paper-1)',
      border: '1px solid var(--rule)',
      borderRadius: 5,
      padding: 2,
      gap: 1,
    }}>
      {options.map(o => {
        const active = value === o.value;
        return (
          <button key={o.value} role="radio" aria-checked={active} onClick={() => onChange(o.value)} style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '4px 10px',
            background: active ? 'var(--paper)' : 'transparent',
            color: active ? 'var(--ink)' : 'var(--ink-2)',
            border: 'none',
            borderRadius: 3,
            boxShadow: active ? 'var(--shadow-sm)' : 'none',
            fontSize: 11.5, fontWeight: active ? 600 : 500,
            letterSpacing: '-0.005em',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}>{o.icon}{o.label}</button>
        );
      })}
    </div>
  );
}

/* =====================================================================
   StatePill — info / warn / err / ok
   ===================================================================== */
function StatePill({ tone = 'info', children, dot = true, size = 'md' }) {
  const tones = {
    info: { bg: 'var(--info-bg)', ink: 'var(--info-ink)' },
    warn: { bg: 'var(--warn-bg)', ink: 'var(--warn-ink)' },
    err:  { bg: 'var(--err-bg)',  ink: 'var(--err-ink)' },
    ok:   { bg: 'var(--ok-bg)',   ink: 'var(--ok-ink)' },
    mute: { bg: 'var(--paper-2)', ink: 'var(--ink-2)' },
  };
  const t = tones[tone];
  const sz = size === 'sm' ? { h: 18, fs: 10, px: 6 } : { h: 22, fs: 11, px: 8 };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      height: sz.h, padding: `0 ${sz.px}px`,
      background: t.bg, color: t.ink,
      borderRadius: 3,
      fontFamily: 'var(--font-mono)', fontSize: sz.fs, fontWeight: 500,
      letterSpacing: '0.04em', textTransform: 'uppercase',
    }}>
      {dot && <span style={{ width: 5, height: 5, borderRadius: '50%', background: t.ink }} />}
      {children}
    </span>
  );
}

/* =====================================================================
   Icon library — small set of stroke icons (16px viewbox)
   ===================================================================== */
function Icon({ name, size = 14, color = 'currentColor', stroke = 1.4 }) {
  const paths = {
    search:   <><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14" strokeLinecap="round"/></>,
    plus:     <><path d="M8 3v10M3 8h10" strokeLinecap="round"/></>,
    star:     <><path d="M8 2.5l1.7 3.6 3.8.5-2.8 2.6.7 3.8L8 11.2 4.6 13l.7-3.8L2.5 6.6l3.8-.5L8 2.5z" strokeLinejoin="round"/></>,
    bolt:     <><path d="M9 2L3.5 9h3.5L7 14l5.5-7H9l1-5z" strokeLinejoin="round"/></>,
    list:     <><path d="M5 4h9M5 8h9M5 12h9" strokeLinecap="round"/><circle cx="2.5" cy="4" r="0.6" fill={color}/><circle cx="2.5" cy="8" r="0.6" fill={color}/><circle cx="2.5" cy="12" r="0.6" fill={color}/></>,
    grid:     <><rect x="2.5" y="2.5" width="4.5" height="4.5"/><rect x="9" y="2.5" width="4.5" height="4.5"/><rect x="2.5" y="9" width="4.5" height="4.5"/><rect x="9" y="9" width="4.5" height="4.5"/></>,
    ladder:   <><path d="M3 13V3M13 13V3M3 6h10M3 9.5h10M3 12.5h10" strokeLinecap="round"/></>,
    chevD:    <><path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round"/></>,
    chevR:    <><path d="M6 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round"/></>,
    chevL:    <><path d="M10 4L6 8l4 4" strokeLinecap="round" strokeLinejoin="round"/></>,
    arrowUp:  <><path d="M8 13V3M4 7l4-4 4 4" strokeLinecap="round" strokeLinejoin="round"/></>,
    arrowDn:  <><path d="M8 3v10M4 9l4 4 4-4" strokeLinecap="round" strokeLinejoin="round"/></>,
    dots:     <><circle cx="3.5" cy="8" r="1" fill={color}/><circle cx="8" cy="8" r="1" fill={color}/><circle cx="12.5" cy="8" r="1" fill={color}/></>,
    bell:     <><path d="M3.5 11.5h9c-1-1-1.5-2.5-1.5-4.5C11 5 10 3 8 3S5 5 5 7c0 2-.5 3.5-1.5 4.5z" strokeLinejoin="round"/><path d="M6.5 13.5a1.5 1.5 0 003 0" strokeLinecap="round"/></>,
    edit:     <><path d="M11 3l2 2-7 7H4v-2l7-7z" strokeLinejoin="round"/></>,
    refresh:  <><path d="M13 8a5 5 0 11-1.5-3.5L13 6M13 3v3h-3" strokeLinecap="round" strokeLinejoin="round"/></>,
    filter:   <><path d="M2.5 3h11l-4 5v5l-3-1.5V8l-4-5z" strokeLinejoin="round"/></>,
    setting:  <><circle cx="8" cy="8" r="2"/><path d="M8 1.5v2M8 12.5v2M14.5 8h-2M3.5 8h-2M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4M12.6 12.6l-1.4-1.4M4.8 4.8L3.4 3.4" strokeLinecap="round"/></>,
    play:     <><path d="M5 3l8 5-8 5V3z" fill={color}/></>,
    note:     <><path d="M4 3h6l2.5 2.5V13H4V3z" strokeLinejoin="round"/><path d="M10 3v2.5h2.5M6 7.5h4M6 10h4" strokeLinecap="round"/></>,
    user:     <><circle cx="8" cy="6" r="2.5"/><path d="M3 13c.5-2.5 2.5-4 5-4s4.5 1.5 5 4" strokeLinecap="round"/></>,
    link:     <><path d="M9 4l3-1 1 1-1 3M7 12l-3 1-1-1 1-3M5.5 10.5l5-5" strokeLinecap="round" strokeLinejoin="round"/></>,
    zap:      <><path d="M9 1.5l-5 7.5h3l-1 5.5 5-7.5h-3l1-5.5z" strokeLinejoin="round"/></>,
    target:   <><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r="0.6" fill={color}/></>,
    eye:      <><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth={stroke} style={{ display: 'inline-block', verticalAlign: 'middle', flex: '0 0 auto' }}>
      {paths[name] || null}
    </svg>
  );
}

/* =====================================================================
   Drift indicator — thesis vs DCF, compact
   ===================================================================== */
function DriftChip({ thesis, dcf, current, size = 'sm' }) {
  // thesis above DCF = corroborated; thesis below = stretched
  const above = thesis > dcf;
  const gap = ((thesis - dcf) / dcf) * 100;
  const tone = Math.abs(gap) < 5 ? 'mute' : above ? 'ok' : 'warn';
  const arrow = above ? '↑' : '↓';
  return (
    <StatePill tone={tone} size={size} dot={false}>
      <span style={{ marginRight: 3 }}>{arrow}</span>
      thesis {above ? 'above' : 'below'} floor · {Math.abs(gap).toFixed(1)}%
    </StatePill>
  );
}

/* =====================================================================
   Animations (global)
   ===================================================================== */
(function injectKeyframes() {
  if (document.getElementById('sr-kf')) return;
  const style = document.createElement('style');
  style.id = 'sr-kf';
  style.textContent = `
    @keyframes sr-spin { to { transform: rotate(360deg); } }
    @keyframes sr-pulse { 0%, 100% { opacity: 0.6; } 50% { opacity: 1; } }
  `;
  document.head.appendChild(style);
})();

/* expose globals so other babel scripts can import */
Object.assign(window, {
  ConvictionBadge, MoneyValue, PctValue, Sparkline, RunButton, ViewToggle,
  StatePill, Icon, DriftChip,
});
