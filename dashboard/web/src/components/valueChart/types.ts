// What GET /api/history returns. Mirrors dashboard/server/history/service.py. Money in cents.

export const RANGES = ["1D", "1W", "1M", "1Y", "All"] as const;
export type Range = (typeof RANGES)[number];

export interface HistoryPoint {
  time: number; // Unix seconds
  value_cents: number;
}

export interface History {
  range: Range;
  start: number;
  end: number;
  base_cents: number | null; // 1D: yesterday's close; longer: the first value
  points: HistoryPoint[];
  benchmark: HistoryPoint[]; // SPY, scaled to start at base (whole portfolio only)
}

/** 1D, 1W and 1M points are minutes or hours apart, so their labels show times. */
export const isIntradayRange = (range: Range) => range === "1D" || range === "1W" || range === "1M";
