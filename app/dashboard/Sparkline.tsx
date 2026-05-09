// ─── Sparkline SVG ───
// Renders a tiny line chart of `data`. Handles degenerate cases:
//   - empty / 1 point → returns null
//   - all-equal points → renders a flat midline so the column isn't blank

export default function Sparkline({
  data,
  color = "#a78bfa",
  width = 120,
  height = 32,
}: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min;
  // Degenerate (all-equal): render a flat dashed midline so user sees "no movement"
  if (range === 0) {
    const y = height / 2;
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        <line x1={2} y1={y} x2={width - 2} y2={y} stroke={color} strokeWidth="1.25" strokeDasharray="3 2" opacity={0.5} />
        <circle cx={width - 2} cy={y} r="2" fill={color} opacity={0.7} />
      </svg>
    );
  }
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const pathD = `M ${points.join(" L ")}`;
  const lastPt = points[points.length - 1].split(",");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={parseFloat(lastPt[0])} cy={parseFloat(lastPt[1])} r="2" fill={color} />
    </svg>
  );
}
