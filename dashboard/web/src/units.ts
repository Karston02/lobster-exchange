// Display helpers. The data stays in integer ticks and lots; only text is formatted.

export const dollars = (ticks: number) =>
  "$" + (ticks / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const btc = (lots: number, digits = 5) => (lots / 1e8).toFixed(digits);

export const usd = (value: number) =>
  (value < 0 ? "-$" : "$") +
  Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const clock = (seconds: number) => {
  const s = Math.floor(seconds);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
};
