import { parallelThrough } from "../geometry";
import type { ShapeProps } from "../Shape";
import { Segment } from "./Lines";

/** A box between two opposite corners. Grab it anywhere inside to move it. */
export function Rect({ pixels, grab }: ShapeProps) {
  const [a, b] = pixels;
  const x = Math.min(a.x, b.x);
  const y = Math.min(a.y, b.y);
  return (
    <rect
      className="area"
      x={x}
      y={y}
      width={Math.abs(b.x - a.x)}
      height={Math.abs(b.y - a.y)}
      onPointerDown={grab("all")}
    />
  );
}

/** A line through the first two points and a parallel one through the third, shaded between,
 *  with a dashed middle line. While drawing, before the third click, only the first line shows. */
export function Channel({ pixels, grab }: ShapeProps) {
  const [a, b, c] = pixels;
  if (!c) return <Segment a={a} b={b} part="all" grab={grab} />;
  const [a2, b2] = parallelThrough(a, b, c);
  const mid = (p: typeof a, q: typeof a) => ({ x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 });
  const [m1, m2] = [mid(a, a2), mid(b, b2)];
  return (
    <>
      <polygon
        className="area"
        points={[a, b, b2, a2].map((p) => `${p.x},${p.y}`).join(" ")}
        onPointerDown={grab("all")}
      />
      <Segment a={a} b={b} part="all" grab={grab} />
      <Segment a={a2} b={b2} part="all" grab={grab} />
      <line className="stroke dashed" x1={m1.x} y1={m1.y} x2={m2.x} y2={m2.y} />
    </>
  );
}
