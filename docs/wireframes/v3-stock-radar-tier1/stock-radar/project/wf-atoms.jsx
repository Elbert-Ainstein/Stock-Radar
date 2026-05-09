/* Shared wireframe atoms — used across all variants */

const Conv = ({ tier, size = 'sm' }) => {
  const cls = `wf-conv wf-conv-${tier.toLowerCase()}`;
  const style = size === 'lg' ? { fontSize: 12, padding: '3px 8px' } : {};
  return <span className={cls} style={style}>{tier}</span>;
};

const Chip = ({ children, active, style }) => (
  <span className={`wf-chip ${active ? 'wf-chip-active' : ''}`} style={style}>{children}</span>
);

const Money = ({ v, ccy = 'USD', big, signed }) => {
  const sym = ccy === 'USD' ? '$' : ccy === 'HKD' ? 'HK$' : ccy === 'EUR' ? '€' : '';
  const isNeg = v < 0;
  const cls = signed ? (isNeg ? 'wf-neg' : 'wf-pos') : '';
  const sign = signed ? (isNeg ? '−' : '+') : '';
  const abs = Math.abs(v);
  const formatted = abs >= 1000 ? abs.toLocaleString(undefined, { maximumFractionDigits: 2 }) :
                    abs.toFixed(2);
  return <span className={`wf-mono ${cls}`} style={big ? { fontSize: 16, fontWeight: 600 } : null}>
    {sign}{sym}{formatted}
  </span>;
};

const Pct = ({ v, signed = true }) => {
  const isNeg = v < 0;
  const cls = isNeg ? 'wf-neg' : 'wf-pos';
  const sign = signed ? (isNeg ? '−' : '+') : '';
  return <span className={`wf-mono ${cls}`}>{sign}{Math.abs(v).toFixed(2)}%</span>;
};

const Spark = ({ data, w = 64, h = 18, dir = 'up' }) => {
  // tiny sketchy line
  const pts = data || [3, 5, 4, 6, 8, 7, 9, 11, 10, 12, 11, 13];
  const max = Math.max(...pts), min = Math.min(...pts);
  const norm = pts.map((p, i) => [
    (i / (pts.length - 1)) * w,
    h - ((p - min) / (max - min || 1)) * h
  ]);
  const path = norm.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const color = dir === 'up' ? 'var(--pos)' : dir === 'down' ? 'var(--neg)' : 'var(--ink-3)';
  return (
    <svg className="wf-spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path d={path} stroke={color} strokeWidth="1.25" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

const Dots = ({ n, total = 5 }) => (
  <span style={{ display: 'inline-flex', gap: 2 }}>
    {Array.from({ length: total }).map((_, i) => (
      <span key={i} style={{
        width: 6, height: 6, borderRadius: '50%',
        background: i < n ? 'var(--ink)' : 'transparent',
        border: '1px solid var(--rule-soft)'
      }} />
    ))}
  </span>
);

const ScribbleArrow = ({ from, to, label, color = 'var(--blue)' }) => {
  const dx = to.x - from.x, dy = to.y - from.y;
  const cx = from.x + dx * 0.4 + (dy * 0.15);
  const cy = from.y + dy * 0.4 - (dx * 0.15);
  return (
    <svg style={{ position: 'absolute', left: 0, top: 0, pointerEvents: 'none', overflow: 'visible' }} width="1" height="1">
      <path d={`M${from.x},${from.y} Q${cx},${cy} ${to.x},${to.y}`}
            stroke={color} strokeWidth="1.25" fill="none" strokeLinecap="round" />
      <polygon points={`${to.x},${to.y} ${to.x - 6},${to.y - 3} ${to.x - 5},${to.y + 4}`} fill={color} />
      {label && <text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 6}
        fontFamily="Caveat" fontSize="13" fill={color} fontWeight="600">{label}</text>}
    </svg>
  );
};

// Mock data — 12 tickers, mixed currencies
const TICKERS = [
  { t: 'LITE',    n: 'Lumentum Holdings',         sec: 'Photonics',     px: 949.93,  d: 47.61, dp: 5.28,  ccy: 'USD', score: 7.7, sd: 0.3,  tgt: 1250,    conv: 'HIGH',   pos: 25, up: 31.6,  fp: 4, scout: '6/9', ago: '3h' },
  { t: 'AEHR',    n: 'Aehr Test Systems',         sec: 'Semis Equip.',  px: 18.42,   d: 0.21,  dp: 1.15,  ccy: 'USD', score: 8.2, sd: 0.5,  tgt: 32,      conv: 'HIGH',   pos: 25, up: 73.7,  fp: 5, scout: '7/9', ago: '1h' },
  { t: '6082.HK', n: 'SMIC',                       sec: 'Foundry',       px: 67.50,   d: -1.20, dp: -1.75, ccy: 'HKD', score: 7.1, sd: -0.1, tgt: 95,      conv: 'HIGH',   pos: 20, up: 40.7,  fp: 4, scout: '5/9', ago: '2h' },
  { t: 'CRWV',    n: 'CoreWeave',                  sec: 'AI Compute',    px: 122.40,  d: 3.80,  dp: 3.20,  ccy: 'USD', score: 8.9, sd: 0.7,  tgt: 220,     conv: 'HIGH',   pos: 25, up: 79.7,  fp: 5, scout: '8/9', ago: '0h' },
  { t: 'ASML',    n: 'ASML Holding',               sec: 'Litho.',        px: 932.10,  d: -8.40, dp: -0.89, ccy: 'EUR', score: 6.9, sd: 0.0,  tgt: 1100,    conv: 'MEDIUM', pos: 15, up: 18.0,  fp: 3, scout: '4/9', ago: '4h' },
  { t: 'NBIS',    n: 'Nebius Group',               sec: 'AI Infra',      px: 41.80,   d: 1.90,  dp: 4.76,  ccy: 'USD', score: 7.4, sd: 0.2,  tgt: 70,      conv: 'HIGH',   pos: 20, up: 67.5,  fp: 4, scout: '5/9', ago: '2h' },
  { t: 'TSM',     n: 'Taiwan Semi',                sec: 'Foundry',       px: 198.30,  d: 0.40,  dp: 0.20,  ccy: 'USD', score: 7.3, sd: 0.1,  tgt: 240,     conv: 'MEDIUM', pos: 15, up: 21.0,  fp: 3, scout: '4/9', ago: '5h' },
  { t: 'AMAT',    n: 'Applied Materials',          sec: 'Semis Equip.',  px: 211.50,  d: 1.10,  dp: 0.52,  ccy: 'USD', score: 6.4, sd: -0.2, tgt: 245,     conv: 'MEDIUM', pos: 12, up: 15.8,  fp: 3, scout: '3/9', ago: '6h' },
  { t: 'ANET',    n: 'Arista Networks',            sec: 'Networking',    px: 388.20,  d: 4.10,  dp: 1.07,  ccy: 'USD', score: 7.0, sd: 0.1,  tgt: 480,     conv: 'HIGH',   pos: 20, up: 23.6,  fp: 4, scout: '5/9', ago: '3h' },
  { t: 'CLS',     n: 'Celestica',                  sec: 'EMS',           px: 142.90,  d: 0.80,  dp: 0.56,  ccy: 'USD', score: 6.8, sd: 0.0,  tgt: 175,     conv: 'MEDIUM', pos: 12, up: 22.5,  fp: 3, scout: '4/9', ago: '5h' },
  { t: '0285.HK', n: 'BYD Electronic',             sec: 'EMS',           px: 38.10,   d: -0.45, dp: -1.17, ccy: 'HKD', score: 5.4, sd: -0.4, tgt: 48,      conv: 'LOW',    pos: 5,  up: 26.0,  fp: 2, scout: '2/9', ago: '7h' },
  { t: 'WOLF',    n: 'Wolfspeed',                  sec: 'SiC',           px: 7.20,    d: -0.18, dp: -2.44, ccy: 'USD', score: 3.1, sd: -0.5, tgt: 6,       conv: 'BROKEN', pos: 0,  up: -16.7, fp: 1, scout: '1/9', ago: '1d' },
];

Object.assign(window, { Conv, Chip, Money, Pct, Spark, Dots, ScribbleArrow, TICKERS });
