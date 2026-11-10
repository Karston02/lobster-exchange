"""The whole live feed against a fake Schwab: no network, no schwab-py."""

import asyncio
import dataclasses
import json
from pathlib import Path

from account import SchwabUnavailable
from account.parse import parse_accounts
from account.quotes import Quote
from live import LiveFeed

FIXTURES = Path(__file__).parents[1] / "account" / "fixtures"


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


class FakeClient:
    async def get_account_numbers(self):
        return FakeResponse([{"accountNumber": "99990000", "hashValue": "x"}])


class FakeSchwab:
    def __init__(self, available=True):
        self.available = available

    async def accounts(self):
        if not self.available:
            raise SchwabUnavailable("not_logged_in", "log in")
        return parse_accounts(json.loads((FIXTURES / "accounts.json").read_text()))

    async def quotes(self, symbols):
        return {"SPY": Quote("SPY", 59900, 59700, 200, 0.335)}

    async def raw_client(self):
        return FakeClient()


class FakeStream:
    """Hands out the queued messages, then waits like a quiet market."""

    def __init__(self, messages):
        self.messages = list(messages)
        self.subscribed: list[str] = []
        self.handler = None
        self.logged_out = False

    async def login(self):
        pass

    def add_level_one_equity_handler(self, handler):
        self.handler = handler

    async def level_one_equity_subs(self, symbols):
        self.subscribed = symbols

    async def handle_message(self):
        if not self.messages:
            await asyncio.sleep(3600)
        self.handler(self.messages.pop(0))

    async def logout(self):
        self.logged_out = True


async def wait_for(condition, timeout=2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "timed out"
        await asyncio.sleep(0.01)


def run_feed(schwab, messages):
    """Starts a feed, waits for it to stream and publish, and returns what it sent."""
    stream = FakeStream(messages)

    async def scenario():
        feed = LiveFeed(schwab, stream_factory=lambda client, account_id: stream, publish_every_s=0.01)
        queue = feed.subscribe()
        feed.start()
        try:
            await wait_for(lambda: feed.latest() is not None and feed.latest()["streaming"] and not stream.messages)
            await asyncio.sleep(0.05)  # let the last price publish
            return feed.latest(), queue, stream
        finally:
            await feed.stop()

    return asyncio.run(scenario())


def test_streams_held_symbols_plus_spy_and_publishes_repriced_accounts():
    latest, queue, stream = run_feed(FakeSchwab(), [{"content": [{"key": "SPY", "LAST_PRICE": 520.0, "CLOSE_PRICE": 515.0}]}])

    assert stream.subscribed == ["AAPL", "SPY", "VTI"]
    assert stream.logged_out
    spy = next(p for p in latest["accounts"][0]["positions"] if p["symbol"] == "SPY")
    assert spy["price_cents"] == 52000
    assert latest["portfolio"]["total_value_cents"] == 660620 + 34010 + 3000
    assert latest["quotes"]["SPY"]["change_cents"] == 500  # live SPY replaced the REST quote
    assert queue.get_nowait() == latest  # the page's queue holds the newest message


def test_publishes_snapshot_numbers_before_any_tick():
    latest, _, _ = run_feed(FakeSchwab(), [])

    assert latest["portfolio"]["total_value_cents"] == 660620 + 34010
    assert latest["quotes"]["SPY"]["change_cents"] == 200  # the REST quote


def test_waits_quietly_while_schwab_is_unavailable():
    async def scenario():
        feed = LiveFeed(FakeSchwab(available=False), stream_factory=lambda c, a: FakeStream([]), publish_every_s=0.01)
        feed.start()
        await asyncio.sleep(0.1)
        await feed.stop()
        return feed.latest()

    assert asyncio.run(scenario()) is None


def test_buying_a_new_stock_reconnects_with_the_new_symbol():
    class GrowingSchwab(FakeSchwab):
        bought = False

        async def accounts(self):
            accounts = await super().accounts()
            if self.bought:  # a new symbol appears in the cash account
                nke = dataclasses.replace(accounts[0].positions[1], symbol="NKE")
                accounts[1] = dataclasses.replace(accounts[1], positions=[*accounts[1].positions, nke])
            return accounts

    schwab = GrowingSchwab()
    streams: list[FakeStream] = []

    def factory(client, account_id):
        streams.append(FakeStream([]))
        return streams[-1]

    async def scenario():
        feed = LiveFeed(schwab, stream_factory=factory, publish_every_s=0.01)
        feed.start()
        try:
            await wait_for(lambda: streams and streams[0].subscribed)
            schwab.bought = True
            await feed.refresh()
            await wait_for(lambda: len(streams) == 2 and streams[1].subscribed, timeout=5)
        finally:
            await feed.stop()

    asyncio.run(scenario())
    assert "NKE" not in streams[0].subscribed
    assert "NKE" in streams[1].subscribed
    assert streams[0].logged_out
