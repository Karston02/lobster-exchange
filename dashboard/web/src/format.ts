// Formatting things other than money for display.

/** 10 -> "10", 7.5 -> "7.5", 0.12345 -> "0.1235" */
export const shares = (quantity: number) => quantity.toLocaleString("en-US", { maximumFractionDigits: 4 });

/** An ISO time as "Tue, Nov 10, 3:04 PM" in your time zone. */
export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Schwab's ALL_CAPS words as "All caps", e.g. "WORKING" -> "Working". */
export const words = (value: string) => value.charAt(0) + value.slice(1).toLowerCase().replaceAll("_", " ");
