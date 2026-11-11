// Pure geometry for drawings: no React, no chart. Checked with Node.

export interface Pixel {
  x: number;
  y: number;
}

/** Where a ray from `a` through `b` leaves the box [0, width] x [0, height]. */
export function rayEnd(a: Pixel, b: Pixel, width: number, height: number): Pixel {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  if (dx === 0 && dy === 0) return b;
  // How far along the direction until each edge; the nearest edge ahead wins
  const steps = [
    dx > 0 ? (width - a.x) / dx : dx < 0 ? -a.x / dx : Infinity,
    dy > 0 ? (height - a.y) / dy : dy < 0 ? -a.y / dy : Infinity,
  ];
  const t = Math.max(1, Math.min(...steps)); // at least as far as b
  return { x: a.x + dx * t, y: a.y + dy * t };
}

/** On the line through `a` and `b`, the y at `x` (the straight line's height there). */
export function yOnLine(a: Pixel, b: Pixel, x: number): number {
  if (b.x === a.x) return a.y;
  return a.y + ((b.y - a.y) * (x - a.x)) / (b.x - a.x);
}

/** A parallel channel's second line: the first line shifted up or down to pass through `c`. */
export function parallelThrough(a: Pixel, b: Pixel, c: Pixel): [Pixel, Pixel] {
  const shift = c.y - yOnLine(a, b, c.x);
  return [
    { x: a.x, y: a.y + shift },
    { x: b.x, y: b.y + shift },
  ];
}

/** The usual Fibonacci retracement levels. */
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

/** Each level's price for a move from `start` to `end`: level 1 at the start, 0 at the end
 *  (TradingView's convention), so 0.618 is how far a pullback has retraced the move. */
export function fibPrices(start: number, end: number): { level: number; price: number }[] {
  return FIB_LEVELS.map((level) => ({ level, price: end + (start - end) * level }));
}

export interface Measurement {
  change: number; // dollars
  percent: number | null;
  bars: number;
  seconds: number;
}

/** What the measure tool reports between two points. */
export function measure(
  a: { price: number; time: number; logical: number },
  b: { price: number; time: number; logical: number },
): Measurement {
  const change = b.price - a.price;
  return {
    change,
    percent: a.price ? (change / a.price) * 100 : null,
    bars: Math.round(b.logical - a.logical),
    seconds: b.time - a.time,
  };
}

/** 200 -> "3m 20s", 90000 -> "1d 1h" (the two largest units). */
export function span(seconds: number): string {
  const s = Math.abs(Math.round(seconds));
  const units: [string, number][] = [
    ["d", 86400],
    ["h", 3600],
    ["m", 60],
    ["s", 1],
  ];
  const parts: string[] = [];
  let rest = s;
  for (const [name, size] of units) {
    const n = Math.floor(rest / size);
    if (n > 0 && parts.length < 2) {
      parts.push(`${n}${name}`);
      rest -= n * size;
    }
  }
  return parts.join(" ") || "0s";
}
