// Drawings as the chart page holds them. Mirrors dashboard/server/drawings/store.py.

/** A point on the chart: a moment and a price, so it stays put across zoom, scroll and timeframes. */
export interface Anchor {
  time: number; // Unix seconds
  price: number; // dollars
}

export type DrawingKind = "hline" | "trend" | "ray" | "rect" | "fib" | "channel" | "text";

export interface Drawing {
  id: string;
  symbol: string;
  kind: DrawingKind;
  points: Anchor[];
  text: string; // text drawings only
  locked: boolean; // can't be moved or deleted until unlocked
}

/** What a click on the chart does. Measure is a drawing tool whose result isn't saved. */
export type Tool = "select" | DrawingKind | "measure";

/** How many clicks each tool takes. */
export const CLICKS: Record<Exclude<Tool, "select">, number> = {
  hline: 1,
  text: 1,
  trend: 2,
  ray: 2,
  rect: 2,
  fib: 2,
  measure: 2,
  channel: 3, // two for the line, one for the parallel line's distance
};
