"""Ticks for the chart's live candle. Run: pytest dashboard/server/live"""

import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import live.feed
from live import CoinbaseTrades, LiveFeed, Tick, TickHub
from live.coinbase_trades import parse_trades
from market.timeframes import in_regular_session

NY = ZoneInfo("America/New_York")

# Shaped like data/coinbase recordings (trade ids and sizes shortened)
UPDATE = {
    "channel": "market_trades",
    "events": [
        {
            "type": "update",
            "trades": [
                {"product_id": "BTC-USD", "trade_id": "2", "price": "73405.34", "size": "0.002", "time": "2026-11-10T18:47:22.141819Z", "side": "SELL"},
                {"product_id": "BTC-USD", "trade_id": "1", "price": "73402.45", "size": "0.001", "time": "2026-11-10T18:47:21.987074Z", "side": "BUY"},
            ],
        }
    ],
}


def test_the_hub_tells_sources_what_to_follow_as_pages_come_and_go():
    hub = TickHub()
    seen = []
    hub.on_change(seen.append)

    a = hub.subscribe("AAPL")
    b = hub.subscribe("AAPL")  # a second page on the same symbol changes nothing
    c = hub.subscribe("BTC-USD")
    hub.unsubscribe("AAPL", a)
    hub.unsubscribe("AAPL", b)
    hub.unsubscribe("BTC-USD", c)

    assert seen == [frozenset({"AAPL"}), frozenset({"AAPL", "BTC-USD"}), frozenset({"BTC-USD"}), frozenset()]


def test_ticks_reach_only_pages_watching_that_symbol():
    hub = TickHub()
    aapl, btc = hub.subscribe("AAPL"), hub.subscribe("BTC-USD")

    hub.publish(Tick("AAPL", 1.0, 190.0, 5))

    assert aapl.get_nowait().price == 190.0
    assert btc.empty()


def test_coinbase_updates_become_ticks_oldest_first():
    ticks = parse_trades(UPDATE)

    assert [t.price for t in ticks] == [73402.45, 73405.34]
    assert ticks[0].volume == 0.001
    assert ticks[0].time == datetime.fromisoformat("2026-11-10T18:47:21.987074+00:00").timestamp()


def test_coinbase_snapshots_and_heartbeats_are_skipped():
    snapshot = {**UPDATE, "events": [{**UPDATE["events"][0], "type": "snapshot"}]}

    assert parse_trades(snapshot) == []
    assert parse_trades({"channel": "heartbeats", "events": []}) == []


def test_coinbase_nanosecond_times_are_trimmed():
    message = json.loads(json.dumps(UPDATE).replace("22.141819Z", "22.141819123Z"))

    assert parse_trades(message)[1].time == datetime.fromisoformat("2026-11-10T18:47:22.141819+00:00").timestamp()


class FakeSocket:
    def __init__(self, messages):
        self.messages = [json.dumps(m) for m in messages]
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def recv(self):
        if not self.messages:
            await asyncio.sleep(3600)
        return self.messages.pop(0)


def test_coinbase_trades_subscribe_and_pass_ticks_on():
    got: list[Tick] = []
    sockets: list[FakeSocket] = []

    def connect(url):
        sockets.append(FakeSocket([UPDATE]))
        return sockets[-1]

    async def scenario():
        trades = CoinbaseTrades(on_tick=got.append, connect=connect)
        trades.set_products({"BTC-USD"})
        for _ in range(100):
            if len(got) == 2:
                break
            await asyncio.sleep(0.01)
        trades.set_products({"BTC-USD", "ETH-USD"})  # a second chart: reconnect with both
        for _ in range(100):
            if len(sockets) == 2 and sockets[1].sent:
                break
            await asyncio.sleep(0.01)
        await trades.stop()

    asyncio.run(scenario())
    assert [t.price for t in got[:2]] == [73402.45, 73405.34]
    assert sockets[0].sent[0] == {"type": "subscribe", "product_ids": ["BTC-USD"], "channel": "market_trades"}
    assert sockets[0].sent[1]["channel"] == "heartbeats"
    assert sockets[1].sent[0]["product_ids"] == ["BTC-USD", "ETH-USD"]


def test_regular_session_hours():
    at = lambda *args: datetime(2026, 11, *args, tzinfo=NY).timestamp()  # noqa: E731

    assert in_regular_session(at(10, 9, 30))
    assert in_regular_session(at(10, 15, 59))
    assert not in_regular_session(at(10, 16, 0))
    assert not in_regular_session(at(10, 9, 29))
    assert not in_regular_session(at(14, 12, 0))  # a Saturday


def test_stock_ticks_carry_new_trades_volume(monkeypatch):
    monkeypatch.setattr(live.feed, "in_regular_session", lambda t: True)
    got: list[Tick] = []
    feed = LiveFeed(schwab=None, on_tick=got.append)

    feed._on_quotes({"content": [{"key": "AAPL", "LAST_PRICE": 190.0, "TOTAL_VOLUME": 1_000_000}]})
    feed._on_quotes({"content": [{"key": "AAPL", "TOTAL_VOLUME": 1_000_300}]})  # same price, more shares
    feed._on_quotes({"content": [{"key": "AAPL", "BID_PRICE": 189.9}]})  # a quote, not a trade

    assert [(t.price, t.volume) for t in got] == [(190.0, 0.0), (190.0, 300.0)]


def test_no_stock_ticks_outside_the_session(monkeypatch):
    monkeypatch.setattr(live.feed, "in_regular_session", lambda t: False)
    got: list[Tick] = []
    feed = LiveFeed(schwab=None, on_tick=got.append)

    feed._on_quotes({"content": [{"key": "AAPL", "LAST_PRICE": 190.0}]})

    assert got == []


def test_charted_stocks_join_the_stream():
    feed = LiveFeed(schwab=None)
    feed.set_extra_symbols({"MSFT"})

    assert feed._symbols == {"MSFT", "SPY"}
    assert feed._have_symbols.is_set()
