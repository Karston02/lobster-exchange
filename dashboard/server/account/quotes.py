"""Turns Schwab's quote JSON into today's price and change per symbol.

The response is keyed by symbol. Each entry has a `quote` block (which, outside
market hours, includes pre- and after-hours trades) and a `regular` block (the
8:30 to 3:00 Central session only). "Today's change" uses `regular` when it's
there, since that's the number usually quoted, and falls back to `quote`.
Field names checked against a real response (Nov 2026).
"""

from dataclasses import dataclass

from .money import cents


@dataclass(frozen=True)
class Quote:
    symbol: str
    last_cents: int
    previous_close_cents: int
    change_cents: int
    change_pct: float | None  # in percent, e.g. 0.62 for +0.62%; None without a previous close


def parse_quotes(data: dict) -> dict[str, Quote]:
    return {symbol: _quote(symbol, item) for symbol, item in data.items() if isinstance(item, dict)}


def _quote(symbol: str, item: dict) -> Quote:
    quote = item.get("quote", {})
    regular = item.get("regular", {})
    close = cents(quote.get("closePrice"))
    if "regularMarketLastPrice" in regular:
        last = cents(regular["regularMarketLastPrice"])
        change_raw, pct_raw = regular.get("regularMarketNetChange"), regular.get("regularMarketPercentChange")
    else:
        last = cents(quote.get("lastPrice", quote.get("mark")))
        change_raw, pct_raw = quote.get("netChange"), quote.get("netPercentChange")
    change = cents(change_raw) if change_raw is not None else last - close
    if pct_raw is not None:
        pct = float(pct_raw)
    else:
        pct = change / close * 100 if close else None
    return Quote(symbol=symbol, last_cents=last, previous_close_cents=close, change_cents=change, change_pct=pct)
