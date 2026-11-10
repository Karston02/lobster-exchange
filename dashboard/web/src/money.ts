// Formatting money for display. The server sends integer cents; only here do
// they become dollars, and only as text.

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** 2431842 -> "$24,318.42" */
export const money = (cents: number) => usd.format(cents / 100);

/** 18240 -> "+$182.40", -405 -> "-$4.05" */
export const signedMoney = (cents: number) => (cents > 0 ? "+" : cents < 0 ? "-" : "") + usd.format(Math.abs(cents) / 100);

/** How much `change` is of `base`, in percent; null when there's no base. */
export const percentOf = (change: number, base: number) => (base ? (change / base) * 100 : null);

/** 0.7563 -> "+0.76%" */
export const signedPercent = (pct: number | null) =>
  pct == null ? "—" : `${pct > 0 ? "+" : pct < 0 ? "-" : ""}${Math.abs(pct).toFixed(2)}%`;

/** The CSS class for a change: green up, orange down. */
export const tone = (value: number | null) => (value == null || value === 0 ? "" : value > 0 ? "gain" : "loss");
