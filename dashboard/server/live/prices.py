"""The latest price per symbol, built from Schwab's level one quote stream.

Each stream message only carries the fields that changed, so updates are
merged into what's already known. schwab-py renames Schwab's numeric field
keys to names like LAST_PRICE before we see them; `key` is the symbol.
"""

from dataclasses import dataclass

from account.money import cents

# Regular-session fields first (8:30 to 3:00 Central), the same choice as the
# REST quotes in account/quotes.py; the all-hours fields are the fallback.
LAST = ("REGULAR_MARKET_LAST_PRICE", "LAST_PRICE", "MARK")
CLOSE = ("CLOSE_PRICE",)
VOLUME = "TOTAL_VOLUME"  # shares traded so far today
FIELDS = LAST + CLOSE + (VOLUME,)


@dataclass(frozen=True)
class LivePrice:
    symbol: str
    last_cents: int
    close_cents: int  # yesterday's close; 0 until known

    @property
    def change_cents(self) -> int:
        return self.last_cents - self.close_cents if self.close_cents else 0

    @property
    def change_pct(self) -> float | None:
        return self.change_cents / self.close_cents * 100 if self.close_cents else None


class LivePrices:
    def __init__(self):
        self._fields: dict[str, dict[str, float]] = {}  # symbol -> latest raw field values

    def apply(self, content: list[dict]) -> set[str]:
        """Merges one message's `content` list. Returns the symbols whose price changed."""
        changed = set()
        for item in content:
            symbol = item.get("key")
            if not symbol:
                continue
            before = self.get(symbol)
            known = self._fields.setdefault(symbol, {})
            known.update({name: item[name] for name in FIELDS if item.get(name) is not None})
            if self.get(symbol) != before:
                changed.add(symbol)
        return changed

    def last_raw(self, symbol: str) -> float | None:
        """The latest price exactly as Schwab sent it (dollars), for chart ticks."""
        known = self._fields.get(symbol, {})
        return next((float(known[name]) for name in LAST if name in known), None)

    def volume(self, symbol: str) -> float | None:
        value = self._fields.get(symbol, {}).get(VOLUME)
        return None if value is None else float(value)

    def get(self, symbol: str) -> LivePrice | None:
        known = self._fields.get(symbol, {})
        last = next((known[name] for name in LAST if name in known), None)
        if last is None:
            return None
        return LivePrice(symbol=symbol, last_cents=cents(last), close_cents=cents(known.get("CLOSE_PRICE")))
