interface Marker {
  x: number;
  y: number;
  color: string;
}

interface Props {
  title: string;
  x: number[];
  y: number[];
  format: (value: number) => string;
  color?: string;
  markers?: Marker[];
  /** Draw a line at zero (for PnL and position). */
  zeroLine?: boolean;
  height?: number;
}

const WIDTH = 600;

/** A minimal SVG line chart: no library, just scaled points. */
export function LineChart({ title, x, y, format, color = "#4ea1ff", markers = [], zeroLine, height = 160 }: Props) {
  const pad = { left: 70, right: 10, top: 10, bottom: 20 };
  const last = y.length ? y[y.length - 1] : null;

  if (x.length < 2) {
    return (
      <section className="panel chart">
        <h2>{title}</h2>
        <div className="empty" style={{ height }}>
          Waiting for data…
        </div>
      </section>
    );
  }

  const xMin = x[0];
  const xMax = x[x.length - 1];
  let yMin = Math.min(...y);
  let yMax = Math.max(...y);
  if (zeroLine) {
    yMin = Math.min(yMin, 0);
    yMax = Math.max(yMax, 0);
  }
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }

  const sx = (v: number) => pad.left + ((v - xMin) / (xMax - xMin || 1)) * (WIDTH - pad.left - pad.right);
  const sy = (v: number) => pad.top + (1 - (v - yMin) / (yMax - yMin)) * (height - pad.top - pad.bottom);
  const points = x.map((v, i) => `${sx(v).toFixed(1)},${sy(y[i]).toFixed(1)}`).join(" ");
  const visibleMarkers = markers.filter((m) => m.x >= xMin && m.x <= xMax);

  return (
    <section className="panel chart">
      <h2>
        {title} {last !== null && <span className="value">{format(last)}</span>}
      </h2>
      <svg viewBox={`0 0 ${WIDTH} ${height}`} preserveAspectRatio="none" style={{ height }}>
        <text x={pad.left - 6} y={pad.top + 10} textAnchor="end" className="axis">
          {format(yMax)}
        </text>
        <text x={pad.left - 6} y={height - pad.bottom} textAnchor="end" className="axis">
          {format(yMin)}
        </text>
        {zeroLine && <line x1={pad.left} x2={WIDTH - pad.right} y1={sy(0)} y2={sy(0)} className="zero" />}
        <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        {visibleMarkers.map((m, i) => (
          <circle key={i} cx={sx(m.x)} cy={sy(m.y)} r={3} fill={m.color} />
        ))}
      </svg>
    </section>
  );
}
