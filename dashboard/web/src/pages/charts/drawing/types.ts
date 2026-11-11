// Drawings as the chart page holds them. Mirrors dashboard/server/drawings/store.py.

/** A point on the chart: a moment and a price, so it stays put across zoom, scroll and timeframes. */
export interface Anchor {
  time: number; // Unix seconds
  price: number; // dollars
}

export type DrawingKind = "hline" | "trend";

export interface Drawing {
  id: string;
  symbol: string;
  kind: DrawingKind;
  points: Anchor[]; // hline: 1, trend: 2
}

/** What a click on the chart does: select and drag, or draw a new shape. */
export type Tool = "select" | DrawingKind;
