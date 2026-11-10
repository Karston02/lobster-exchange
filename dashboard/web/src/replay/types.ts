// The messages the Python server sends (dashboard/server/session.py).
// Prices are integer ticks ($0.01), sizes integer lots (1 satoshi).

export type Side = "buy" | "sell";

export interface Recording {
  name: string;
  minutes: number;
  has_trades: boolean;
}

export interface StrategyInfo {
  key: string;
  name: string;
  description: string;
}

export interface Hello {
  type: "hello";
  recording: string;
  strategy: string;
  duration_s: number;
}

export interface BotOrder {
  /** A string, because bot ids are bigger than a JavaScript number holds exactly. */
  id: string;
  side: Side;
  price: number;
  quantity: number;
  /** Quantity waiting ahead of this order in its line. */
  ahead: number | null;
}

export interface FillMessage {
  /** Seconds since the replay started. */
  t: number;
  side: Side;
  price: number;
  quantity: number;
  maker: boolean;
  fee_usd: number;
}

export interface Tick {
  type: "tick";
  t: number;
  mid: number | null;
  /** [price, quantity] pairs, best first. */
  bids: [number, number][];
  asks: [number, number][];
  orders: BotOrder[];
  fills: FillMessage[];
  position: number;
  pnl_usd: number | null;
  fees_usd: number;
  fill_count: number;
  rejections: number;
}

export interface Done {
  type: "done";
  pnl_usd: number | null;
  fees_usd: number;
  fill_count: number;
  position: number;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type ServerMessage = Hello | Tick | Done | ErrorMessage;

export interface ReplaySettings {
  recording: string;
  strategy: string;
  speed: number;
  size_btc: number;
  latency_ms: number;
  maker_fee_bps: number;
  taker_fee_bps: number;
}
