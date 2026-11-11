import { signedPercent } from "../../../money";
import { span, type Measurement, type Pixel } from "./geometry";

interface Props {
  a: Pixel;
  b: Pixel;
  result: Measurement;
  decimals: number;
}

/** The measure tool's box: price change, percent, bars and time between two points. Not saved. */
export function MeasureBox({ a, b, result, decimals }: Props) {
  const up = result.change >= 0;
  const x = Math.min(a.x, b.x);
  const y = Math.min(a.y, b.y);
  const sign = result.change > 0 ? "+" : result.change < 0 ? "-" : "";
  const label = `${sign}${Math.abs(result.change).toFixed(decimals)} (${signedPercent(result.percent)}) · ${result.bars} bars · ${span(result.seconds)}`;
  return (
    <g className={`measure ${up ? "gain" : "loss"}`}>
      <rect x={x} y={y} width={Math.abs(b.x - a.x)} height={Math.abs(b.y - a.y)} />
      <text className="num" x={(a.x + b.x) / 2} y={up ? y - 8 : y + Math.abs(b.y - a.y) + 16} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}
