"use client";

export default function TimePathChart({
  path,
  currentPrice,
  targetPrice,
  multipleLabel,
  width = 700,
  height = 260,
}: {
  path: { year: number; price: number; multiple: number }[];
  currentPrice: number;
  targetPrice: number;
  multipleLabel: string;
  width?: number;
  height?: number;
}) {
  if (path.length < 2) return null;

  const pad = { top: 30, right: 80, bottom: 40, left: 60 };
  const w = width - pad.left - pad.right;
  const h = height - pad.top - pad.bottom;

  const allPrices = [...path.map(p => p.price), currentPrice, targetPrice].filter(p => p > 0);
  const minP = Math.min(...allPrices) * 0.8;
  const maxP = Math.max(...allPrices) * 1.15;
  const maxYear = path[path.length - 1].year;

  const x = (year: number) => pad.left + (year / maxYear) * w;
  const y = (price: number) => pad.top + h - ((price - minP) / (maxP - minP)) * h;

  const linePoints = path.map(p => `${x(p.year)},${y(p.price)}`).join(" L ");

  // Area fill
  const areaPath = `M ${x(0)},${y(path[0].price)} L ${linePoints} L ${x(maxYear)},${pad.top + h} L ${x(0)},${pad.top + h} Z`;

  const multipleAnnotations = path.filter(p => p.year === Math.round(p.year) && p.year > 0);

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="w-full">
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.15" />
          <stop offset="100%" stopColor="#a78bfa" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid */}
      {[0, 0.25, 0.5, 0.75, 1].map(f => {
        const yPos = pad.top + h * (1 - f);
        const price = minP + (maxP - minP) * f;
        return (
          <g key={f}>
            <line x1={pad.left} y1={yPos} x2={width - pad.right} y2={yPos} stroke="#1e1e2e" strokeWidth="1" />
            <text x={pad.left - 8} y={yPos + 4} textAnchor="end" fill="#555" fontSize="10" fontFamily="monospace">
              ${Math.round(price).toLocaleString()}
            </text>
          </g>
        );
      })}

      {/* Year labels */}
      {Array.from({ length: Math.ceil(maxYear) + 1 }, (_, i) => i).map(yr => (
        <text key={yr} x={x(yr)} y={height - 10} textAnchor="middle" fill="#555" fontSize="10" fontFamily="monospace">
          Y{yr}
        </text>
      ))}

      {/* Current price line */}
      <line x1={pad.left} y1={y(currentPrice)} x2={width - pad.right} y2={y(currentPrice)}
        stroke="#38bdf8" strokeWidth="1" strokeDasharray="6 3" opacity="0.4" />
      <text x={width - pad.right + 6} y={y(currentPrice) + 4} fill="#38bdf8" fontSize="9" fontFamily="monospace">
        Now ${Math.round(currentPrice)}
      </text>

      {/* Target price line */}
      <line x1={pad.left} y1={y(targetPrice)} x2={width - pad.right} y2={y(targetPrice)}
        stroke="#34d399" strokeWidth="1" strokeDasharray="6 3" opacity="0.4" />
      <text x={width - pad.right + 6} y={y(targetPrice) + 4} fill="#34d399" fontSize="9" fontFamily="monospace">
        Target ${Math.round(targetPrice)}
      </text>

      {/* Area fill */}
      <path d={areaPath} fill="url(#areaGrad)" />

      {/* Price line */}
      <path d={`M ${linePoints}`} fill="none" stroke="#a78bfa" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

      {/* Multiple annotations */}
      {multipleAnnotations.map(p => (
        <g key={p.year}>
          <circle cx={x(p.year)} cy={y(p.price)} r="4" fill="#a78bfa" />
          <text x={x(p.year)} y={y(p.price) - 12} textAnchor="middle" fill="#a78bfa" fontSize="9" fontFamily="monospace" fontWeight="bold">
            {p.multiple}\u00D7 {multipleLabel}
          </text>
          <text x={x(p.year)} y={y(p.price) + 16} textAnchor="middle" fill="#888" fontSize="9" fontFamily="monospace">
            ${Math.round(p.price)}
          </text>
        </g>
      ))}

      {/* End dot */}
      <circle cx={x(maxYear)} cy={y(path[path.length - 1].price)} r="5" fill="#a78bfa" stroke="#0a0a0f" strokeWidth="2" />
    </svg>
  );
}
