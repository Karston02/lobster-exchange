// What the server's account routes return. Mirrors dashboard/server/account/.
// Money is integer cents.

export interface Holding {
  symbol: string;
  description: string; // empty for some positions
  quantity: number;
  market_value_cents: number;
  day_change_cents: number;
}

/** GET /api/portfolio: every account added together. */
export interface Portfolio {
  total_value_cents: number;
  day_change_cents: number;
  previous_value_cents: number;
  cash_cents: number;
  account_count: number;
  holdings: Holding[];
}

export interface Quote {
  symbol: string;
  last_cents: number;
  previous_close_cents: number;
  change_cents: number;
  change_pct: number | null;
}

/** GET /api/quotes?symbols=... */
export interface Quotes {
  quotes: Record<string, Quote>;
}
