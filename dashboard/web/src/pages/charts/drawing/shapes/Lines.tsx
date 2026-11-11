import { rayEnd, type Pixel } from "../geometry";
import type { Part, ShapeProps } from "../Shape";

/** A line with a wide invisible twin that's easy to click. */
export function Segment({ a, b, part, grab }: { a: Pixel; b: Pixel; part: Part; grab: ShapeProps["grab"] }) {
  return (
    <>
      <line className="hit" x1={a.x} y1={a.y} x2={b.x} y2={b.y} onPointerDown={grab(part)} />
      <line className="stroke" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
    </>
  );
}

export function HLine({ drawing, pixels, width, decimals, grab }: ShapeProps) {
  const y = pixels[0].y;
  return (
    <>
      <Segment a={{ x: 0, y }} b={{ x: width, y }} part={0} grab={grab} />
      <text className="tag num" x={width - 6} y={y - 6} textAnchor="end">
        {drawing.points[0].price.toFixed(decimals)}
      </text>
    </>
  );
}

export function Trend({ pixels, grab }: ShapeProps) {
  return <Segment a={pixels[0]} b={pixels[1]} part="all" grab={grab} />;
}

/** From the first point through the second, on to the edge of the chart. */
export function Ray({ pixels, width, height, grab }: ShapeProps) {
  return <Segment a={pixels[0]} b={rayEnd(pixels[0], pixels[1], width, height)} part="all" grab={grab} />;
}
