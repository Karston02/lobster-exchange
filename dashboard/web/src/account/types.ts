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

export interface Position {
  symbol: string;
  description: string;
  asset_type: string;
  quantity: number; // negative when short
  average_price_cents: number;
  price_cents: number;
  market_value_cents: number;
  day_change_cents: number;
  open_pnl_cents: number;
}

export interface Account {
  last4: string; // "…1234"
  name: string; // e.g. "Roth IRA" (LOBSTER_ACCOUNT_NAMES), else the last four digits
  type: string; // CASH or MARGIN
  total_value_cents: number;
  cash_cents: number;
  buying_power_cents: number | null;
  day_change_cents: number;
  open_pnl_cents: number;
  positions: Position[];
}

/** GET /api/account */
export interface Accounts {
  accounts: Account[];
  fetched_at: string | null;
}

export interface Order {
  order_id: string;
  account_last4: string;
  symbol: string;
  side: string; // BUY, SELL, ...
  order_type: string; // LIMIT, MARKET, ...
  quantity: number;
  filled_quantity: number;
  price_cents: number | null;
  status: string;
  is_open: boolean;
  entered_time: string;
}

/** GET /api/orders */
export interface Orders {
  orders: Order[];
}
