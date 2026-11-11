import type { Bar } from "../bars";
import type { Viewport } from "../lightweight";

/** Snap (a "magnet"): move a point onto the nearest bar, at whichever of its open,
 *  high, low or close is closest on screen. Beyond the last bar there's nothing to
 *  snap to, so only the position moves onto the bar grid. Returns the bar position
 *  (a whole number) and the price; the caller turns the position into a time. */
export function snapToBar(logical: number, price: number, y: number, bars: Bar[], view: Viewport) {
  const index = Math.round(logical);
  const bar = bars[index];
  if (!bar) return { logical: index, price };
  let best = price;
  let bestDistance = Infinity;
  for (const candidate of [bar.open, bar.high, bar.low, bar.close]) {
    const py = view.priceToY(candidate);
    if (py === null) continue;
    if (Math.abs(py - y) < bestDistance) {
      bestDistance = Math.abs(py - y);
      best = candidate;
    }
  }
  return { logical: index, price: best };
}
