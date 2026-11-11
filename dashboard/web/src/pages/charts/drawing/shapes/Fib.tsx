import { fibPrices } from "../geometry";
import type { ShapeProps } from "../Shape";
import { Segment } from "./Lines";

/** Fibonacci retracement: a level line for each ratio, between the two points' times. */
export function Fib({ drawing, pixels, decimals, grab }: ShapeProps) {
  const [a, b] = pixels;
  const [start, end] = drawing.points;
  const left = Math.min(a.x, b.x);
  const right = Math.max(a.x, b.x);
  // Levels are evenly spaced in price, and the price axis is linear, so in pixels too
  const yOf = (price: number) => b.y + ((a.y - b.y) * (price - end.price)) / (start.price - end.price || 1);
  return (
    <>
      <line className="stroke faint" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
      {fibPrices(start.price, end.price).map(({ level, price }) => {
        const y = yOf(price);
        return (
          <g key={level}>
            <Segment a={{ x: left, y }} b={{ x: right, y }} part="all" grab={grab} />
            <text className="tag num" x={left + 4} y={y - 4}>
              {level} ({price.toFixed(decimals)})
            </text>
          </g>
        );
      })}
    </>
  );
}
