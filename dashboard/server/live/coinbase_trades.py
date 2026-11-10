"""Live crypto trades from Coinbase Advanced Trade's public websocket.

The same feed the Rust recorder uses (crates/recorder). Message shape, from
our recordings: {"channel": "market_trades", "events": [{"type": "snapshot" |
"update", "trades": [{"product_id", "trade_id", "price", "size", "time",
"side"}]}]}. The first event is a snapshot of recent trades, which the candle
history already covers, so only "update" trades become ticks.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .ticks import Tick

log = logging.getLogger("lobster.coinbase")

URL = "wss://advanced-trade-ws.coinbase.com"
MIN_BACKOFF_S = 1.0
MAX_BACKOFF_S = 60.0


def parse_trades(message: dict) -> list[Tick]:
    """The new trades in one message, oldest first."""
    if message.get("channel") != "market_trades":
        return []
    ticks = [
        Tick(symbol=t["product_id"], time=_seconds(t["time"]), price=float(t["price"]), volume=float(t["size"]))
        for event in message.get("events", [])
        if event.get("type") == "update"
        for t in event.get("trades", [])
    ]
    return sorted(ticks, key=lambda tick: tick.time)


def _seconds(iso: str) -> float:
    """'2026-11-10T18:47:22.141819Z' -> Unix seconds. Trims fractions past microseconds."""
    head, _, fraction = iso.rstrip("Z").partition(".")
    return datetime.fromisoformat(f"{head}.{(fraction or '0')[:6]}+00:00").timestamp()


def _connect(url: str) -> Any:
    import websockets  # installed with uvicorn[standard]

    return websockets.connect(url, open_timeout=10)


class CoinbaseTrades:
    """Follows the trades of whichever products charts are watching (one connection for all)."""

    def __init__(self, on_tick: Callable[[Tick], None], connect: Callable[[str], Any] = _connect):
        self._on_tick = on_tick
        self._connect = connect
        self._products: frozenset[str] = frozenset()
        self._changed = asyncio.Event()
        self._task: asyncio.Task | None = None

    def set_products(self, products: set[str] | frozenset[str]) -> None:
        products = frozenset(products)
        if products == self._products:
            return
        self._products = products
        self._changed.set()
        if products and self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        backoff = MIN_BACKOFF_S
        while True:
            if not self._products:
                self._changed.clear()
                await self._changed.wait()
                continue
            try:
                await self._follow(sorted(self._products))
                backoff = MIN_BACKOFF_S  # left on purpose (products changed)
                continue
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.info("Coinbase trade feed dropped (%s)", type(error).__name__)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_S)

    async def _follow(self, products: list[str]) -> None:
        """One connection: subscribe, pass trades on, return when the products change."""
        self._changed.clear()
        async with self._connect(URL) as ws:
            await ws.send(json.dumps({"type": "subscribe", "product_ids": products, "channel": "market_trades"}))
            # Without heartbeats, Coinbase closes quiet connections after 60 to 90 seconds
            await ws.send(json.dumps({"type": "subscribe", "channel": "heartbeats"}))
            changed = asyncio.create_task(self._changed.wait())
            try:
                while True:
                    received = asyncio.create_task(ws.recv())
                    await asyncio.wait({received, changed}, return_when=asyncio.FIRST_COMPLETED)
                    if changed.done():
                        received.cancel()
                        return
                    for tick in parse_trades(json.loads(received.result())):
                        self._on_tick(tick)
            finally:
                changed.cancel()
