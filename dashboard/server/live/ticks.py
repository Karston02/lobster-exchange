"""Ticks: each new trade price for a symbol a chart is watching.

The chart page subscribes to one symbol; the hub counts who's watching what
and tells the sources (Schwab's quote stream for stocks, Coinbase's trade
feed for crypto) which symbols to follow.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

MAX_QUEUED = 1000  # a page that falls this far behind loses its oldest ticks


@dataclass(frozen=True)
class Tick:
    symbol: str
    time: float  # Unix seconds
    price: float  # dollars, for drawing only (the chart works in floats)
    volume: float  # shares or coins traded since the previous tick


class TickHub:
    def __init__(self):
        self._watchers: dict[str, set[asyncio.Queue]] = {}
        self._listeners: list[Callable[[frozenset[str]], None]] = []

    def on_change(self, listener: Callable[[frozenset[str]], None]) -> None:
        """`listener(symbols)` is called whenever the set of watched symbols changes."""
        self._listeners.append(listener)

    def symbols(self) -> frozenset[str]:
        return frozenset(self._watchers)

    def subscribe(self, symbol: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUED)
        first = symbol not in self._watchers
        self._watchers.setdefault(symbol, set()).add(queue)
        if first:
            self._changed()
        return queue

    def unsubscribe(self, symbol: str, queue: asyncio.Queue) -> None:
        watchers = self._watchers.get(symbol)
        if watchers is None:
            return
        watchers.discard(queue)
        if not watchers:
            del self._watchers[symbol]
            self._changed()

    def publish(self, tick: Tick) -> None:
        for queue in self._watchers.get(tick.symbol, ()):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(tick)

    def _changed(self) -> None:
        for listener in self._listeners:
            listener(self.symbols())
