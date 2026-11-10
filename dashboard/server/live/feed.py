"""Runs the live feed on the server, whether or not a page is open.

Three loops share the work:
- refresh: every minute, reload accounts from Schwab (catches trades, cash,
  new positions) and work out which symbols to stream;
- stream: keep one Schwab quote stream open for those symbols, reconnecting
  with growing waits if it drops; a change of symbols reconnects too;
- publish: at most once a second, if anything changed, reprice the accounts
  and send the result to every open page.
"""

import asyncio
import dataclasses
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from account import SchwabService, SchwabUnavailable
from account.models import Account
from account.portfolio import summarize
from account.quotes import Quote

from .prices import LivePrices
from .revalue import live_quote, revalue

log = logging.getLogger("lobster.live")

BENCHMARK = "SPY"
MIN_BACKOFF_S = 1.0
MAX_BACKOFF_S = 60.0


def _schwab_stream(client: Any, account_id: int) -> Any:
    from schwab.streaming import StreamClient  # only needed once a stream starts

    return StreamClient(client, account_id=account_id)


class LiveFeed:
    def __init__(
        self,
        schwab: SchwabService,
        stream_factory: Callable[[Any, int], Any] = _schwab_stream,
        publish_every_s: float = 1.0,
        refresh_every_s: float = 60.0,
    ):
        self._schwab = schwab
        self._stream_factory = stream_factory
        self._publish_every_s = publish_every_s
        self._refresh_every_s = refresh_every_s

        self._prices = LivePrices()
        self._accounts: list[Account] | None = None
        self._benchmark: Quote | None = None  # SPY from REST, until the stream has it
        self._symbols: frozenset[str] = frozenset()
        self._symbols_changed = asyncio.Event()
        self._have_symbols = asyncio.Event()
        self._streaming = False
        self._dirty = False

        self._latest: dict | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None

    # --- lifecycle ---

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        await asyncio.gather(self._refresh_loop(), self._stream_loop(), self._publish_loop())

    # --- what the websocket route uses ---

    def latest(self) -> dict | None:
        """The last message sent, for a page that just connected."""
        return self._latest

    def subscribe(self) -> asyncio.Queue:
        """A queue that always holds the newest message (older unread ones are dropped)."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    # --- refresh: accounts and symbols ---

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except SchwabUnavailable as error:
                log.info("live feed waiting for Schwab: %s", error.reason)
            await asyncio.sleep(self._refresh_every_s)

    async def refresh(self) -> None:
        self._accounts = await self._schwab.accounts()
        try:
            self._benchmark = (await self._schwab.quotes([BENCHMARK])).get(BENCHMARK)
        except SchwabUnavailable:
            pass  # Home simply shows no SPY until it's back
        symbols = frozenset(
            p.symbol for a in self._accounts for p in a.positions if p.asset_type != "OPTION"
        ) | {BENCHMARK}
        if symbols != self._symbols:
            self._symbols = symbols
            self._symbols_changed.set()
        self._have_symbols.set()
        self._dirty = True

    # --- stream: one Schwab connection ---

    async def _stream_loop(self) -> None:
        backoff = MIN_BACKOFF_S
        while True:
            await self._have_symbols.wait()
            started = asyncio.get_running_loop().time()
            try:
                await self._stream_once()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # dropped connection, expired login, ...
                log.info("quote stream ended (%s)", type(error).__name__)
            finally:
                self._streaming = False
                self._dirty = True
            if asyncio.get_running_loop().time() - started > 60:
                backoff = MIN_BACKOFF_S  # it was a healthy connection; start over
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_S)

    async def _stream_once(self) -> None:
        """Connects, subscribes, and handles messages until the symbols change or it drops."""
        client = await self._schwab.raw_client()
        response = await client.get_account_numbers()
        response.raise_for_status()
        # The full number is needed to log in to the stream; it stays in this variable only
        account_id = int(response.json()[0]["accountNumber"])
        stream = self._stream_factory(client, account_id)
        await stream.login()
        try:
            stream.add_level_one_equity_handler(self._on_quotes)  # handler before subscribing
            self._symbols_changed.clear()
            await stream.level_one_equity_subs(sorted(self._symbols))
            self._streaming = True
            self._dirty = True
            changed = asyncio.create_task(self._symbols_changed.wait())
            try:
                while not changed.done():
                    message = asyncio.create_task(stream.handle_message())
                    await asyncio.wait({message, changed}, return_when=asyncio.FIRST_COMPLETED)
                    if not message.done():
                        message.cancel()  # symbols changed: reconnect with the new list
                    else:
                        message.result()  # raises if the connection broke
            finally:
                changed.cancel()
        finally:
            try:
                await stream.logout()
            except Exception:
                pass  # the connection may already be gone

    def _on_quotes(self, message: dict) -> None:
        if self._prices.apply(message.get("content", [])):
            self._dirty = True

    # --- publish: reprice and send ---

    async def _publish_loop(self) -> None:
        while True:
            self.publish_if_changed()
            await asyncio.sleep(self._publish_every_s)

    def publish_if_changed(self) -> None:
        if not self._dirty or self._accounts is None:
            return
        self._dirty = False
        accounts = revalue(self._accounts, self._prices)
        live_spy = self._prices.get(BENCHMARK)
        spy = live_quote(live_spy) if live_spy and live_spy.close_cents else self._benchmark
        self._latest = {
            "type": "live",
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "streaming": self._streaming,
            "accounts": [dataclasses.asdict(a) for a in accounts],
            "portfolio": dataclasses.asdict(summarize(accounts)),
            "quotes": {BENCHMARK: dataclasses.asdict(spy)} if spy else {},
        }
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()  # a slow page only ever gets the newest update
            queue.put_nowait(self._latest)
