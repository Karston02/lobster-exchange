// Candles as the chart page uses them: dollars (for drawing only) and Unix seconds.

/** One candle from GET /api/candles (prices in cents). */
export interface CandleCents {
  time: number;
  open_cents: number;
  high_cents: number;
  low_cents: number;
  close_cents: number;
  volume: number;
}

export interface CandlesResponse {
  symbol: string;
  timeframe: string;
  candles: CandleCents[];
}

/** A candle ready to draw. Dollars are floats here, but only for display. */
export interface Bar {
  time: number; // Unix seconds, UTC
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export const toBar = (c: CandleCents): Bar => ({
  time: c.time,
  open: c.open_cents / 100,
  high: c.high_cents / 100,
  low: c.low_cents / 100,
  close: c.close_cents / 100,
  volume: c.volume,
});

export const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "D", "W"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export const isIntraday = (tf: Timeframe) => tf !== "D" && tf !== "W";
