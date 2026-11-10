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

/** Each timeframe's period in seconds. */
export const PERIOD_S: Record<Timeframe, number> = {
  "1m": 60,
  "5m": 300,
  "15m": 900,
  "1h": 3600,
  "4h": 4 * 3600,
  D: 86400,
  W: 7 * 86400,
};

/** A live trade, from /ws/ticks. */
export interface Tick {
  symbol: string;
  time: number; // Unix seconds
  price: number;
  volume: number; // traded since the previous tick
}

/** The last bar after a trade: the same bar updated, or a new bar if the period rolled over.
 *  Null for a trade older than the last bar (it's already in the history).
 *
 *  A new bar starts a whole number of periods after the last one. That keeps
 *  every alignment the server chose (9:30 for stock hours, UTC for crypto,
 *  the trading day for D and W) without redoing it here. */
export function applyTick(last: Bar, tick: Tick, periodS: number): Bar | null {
  if (tick.time < last.time) return null;
  if (tick.time < last.time + periodS) {
    return {
      ...last,
      high: Math.max(last.high, tick.price),
      low: Math.min(last.low, tick.price),
      close: tick.price,
      volume: last.volume + tick.volume,
    };
  }
  const start = last.time + Math.floor((tick.time - last.time) / periodS) * periodS;
  return { time: start, open: tick.price, high: tick.price, low: tick.price, close: tick.price, volume: tick.volume };
}
