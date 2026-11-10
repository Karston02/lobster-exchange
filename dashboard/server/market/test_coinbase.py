"""Coinbase candles against a fake HTTP client. Run: pytest dashboard/server/market"""

import asyncio
from datetime import datetime, timezone

import pytest

from market.coinbase import CoinbaseMarket, SourceUnavailable, UnknownSymbol, decimals_of, utc_bucket
from market.symbols import is_crypto

NOW = datetime(2026, 11, 10, 21, 30, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


class FakeHttp:
    """Serves hourly BTC candles for any window, newest first, like Coinbase; `history_s` limits how far back."""

    def __init__(self, history_s=10**9, product_status=200):
        self.history_s = history_s
        self.product_status = product_status
        self.calls: list[tuple[str, dict]] = []

    async def get(self, path, params):
        self.calls.append((path, params))
        if not path.endswith("/candles"):
            return FakeResponse({"id": "BTC-USD", "quote_increment": "0.01"}, self.product_status)
        g = params["granularity"]
        start = int(datetime.strptime(params["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
        end = int(datetime.strptime(params["end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
        oldest = int(NOW.timestamp()) - self.history_s
        times = [t for t in range(end, start - 1, -g) if t >= oldest]
        assert len(times) <= 300, "Coinbase rejects more than 300 points"
        return FakeResponse([[t, 99.5, 101.25, 100.0, 100.75, 0.5] for t in times])


def market(http) -> CoinbaseMarket:
    return CoinbaseMarket(http=http, now=lambda: NOW)


def test_crypto_symbols_have_a_dash():
    assert is_crypto("BTC-USD") and is_crypto("ETH-USDC")
    assert not is_crypto("AAPL") and not is_crypto("BRK.B")


def test_decimals_come_from_the_price_step():
    assert decimals_of("0.01") == 2
    assert decimals_of("0.00000001") == 8
    assert decimals_of("1") == 0
    assert decimals_of("0.10") == 1


def test_hourly_candles_page_backwards_300_at_a_time():
    http = FakeHttp()
    series = asyncio.run(market(http).candles("BTC-USD", "1h"))

    candle_calls = [p for path, p in http.calls if path.endswith("/candles")]
    assert len(candle_calls) == 4
    assert len(series.candles) == 1200
    times = [c.time for c in series.candles]
    assert times == sorted(times) and len(set(times)) == len(times)
    assert series.decimals == 2 and series.source == "coinbase"
    assert series.candles[-1].close == 10075 and series.candles[-1].volume == 0.5


def test_paging_stops_where_history_ends():
    http = FakeHttp(history_s=100 * 3600)
    series = asyncio.run(market(http).candles("BTC-USD", "1h"))

    assert len(series.candles) == 100  # the 100 hourly candles in the last 100 hours
    assert len([1 for path, _ in http.calls if path.endswith("/candles")]) == 2  # the second page came back empty


def test_four_hour_bars_are_built_from_hours_on_utc_boundaries():
    series = asyncio.run(market(FakeHttp()).candles("BTC-USD", "4h"))

    assert all(c.time % (4 * 3600) == 0 for c in series.candles)
    assert series.candles[-2].volume == 2.0  # four hourly candles of 0.5


def test_weeks_start_on_monday():
    week = utc_bucket(7 * 86400, 4 * 86400)
    wednesday = int(datetime(2026, 11, 11, 12, tzinfo=timezone.utc).timestamp())
    monday = int(datetime(2026, 11, 9, tzinfo=timezone.utc).timestamp())

    assert week(wednesday) == monday


def test_answers_are_cached():
    http = FakeHttp()
    coinbase = market(http)

    async def twice():
        await coinbase.candles("BTC-USD", "D")
        await coinbase.candles("BTC-USD", "D")

    asyncio.run(twice())
    assert len(http.calls) == 1 + 4  # one product lookup, one set of pages


def test_unknown_products_and_outages_are_explained():
    with pytest.raises(UnknownSymbol, match="NOPE-USD"):
        asyncio.run(market(FakeHttp(product_status=404)).candles("NOPE-USD", "D"))
    with pytest.raises(SourceUnavailable, match="HTTP 503"):
        asyncio.run(market(FakeHttp(product_status=503)).candles("BTC-USD", "D"))
