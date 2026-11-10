// Candles as the chart page uses them: dollars (for drawing only) and Unix seconds.

/** One candle from GET /api/candles: prices are whole numbers of 10^-decimals dollars. */
export interface CandleUnits {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlesResponse {
  symbol: string;
  timeframe: string;
  source: "schwab" | "coinbase";
  decimals: number; // 2 for most stocks, up to 8 for coins like SHIB-USD
  candles: CandleUnits[];
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

export function toBar(c: CandleUnits, decimals: number): Bar {
  const unit = 10 ** decimals;
  return { time: c.time, open: c.open / unit, high: c.high / unit, low: c.low / unit, close: c.close / unit, volume: c.volume };
}

export const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "D", "W"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export const isIntraday = (tf: Timeframe) => tf !== "D" && tf !== "W";
