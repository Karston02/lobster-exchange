"""Tests for candles and timeframes. Run: pytest dashboard/server/market"""

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from market.candles import Candle, combine
from market.history import fetch_candles, parse_candles
from market.timeframes import session_bucket

NY = ZoneInfo("America/New_York")


def at(day: int, hour: int, minute: int, month: int = 11) -> int:
    """Unix seconds for a New York wall-clock time in 2026."""
    return int(datetime(2026, month, day, hour, minute, tzinfo=NY).timestamp())


def candle(t: int, o: int, h: int, low: int, c: int, v: int = 100) -> Candle:
    return Candle(t, o, h, low, c, v)


def test_combine_takes_first_open_last_close_and_extremes():
    halves = [candle(0, 100, 110, 95, 105, 10), candle(1800, 105, 120, 101, 118, 20)]

    (hour,) = combine(halves, lambda t: 0)

    assert hour == Candle(0, 100, 120, 95, 118, 30)


def test_hours_start_at_the_930_open_not_the_clock_hour():
    hour = session_bucket(3600)

    assert hour(at(10, 9, 30)) == at(10, 9, 30)
    assert hour(at(10, 10, 0)) == at(10, 9, 30)  # 10:00-10:30 belongs to the 9:30 hour
    assert hour(at(10, 10, 30)) == at(10, 10, 30)
    assert hour(at(10, 15, 30)) == at(10, 15, 30)  # the last, half-hour bar of the day


def test_four_hour_bars_split_the_day_at_130():
    four = session_bucket(4 * 3600)

    assert four(at(10, 13, 0)) == at(10, 9, 30)
    assert four(at(10, 13, 30)) == at(10, 13, 30)
    assert four(at(10, 15, 30)) == at(10, 13, 30)


def test_buckets_follow_daylight_saving_time():
    hour = session_bucket(3600)

    assert hour(at(15, 10, 0, month=7)) == at(15, 9, 30, month=7)  # July: Eastern is UTC-4


def test_a_day_of_30_minute_candles_makes_7_hourly_bars():
    halves = [candle(at(10, 9, 30) + i * 1800, 100, 101, 99, 100) for i in range(13)]  # 9:30 to 16:00

    hours = combine(halves, session_bucket(3600))

    assert len(hours) == 7
    assert hours[-1].time == at(10, 15, 30) and hours[-1].volume == 100  # the half-hour 15:30 bar
    assert hours[0].volume == 200


def test_parse_sorts_and_drops_duplicate_times():
    data = {
        "candles": [
            {"open": 2, "high": 2, "low": 2, "close": 2, "volume": 5, "datetime": 2000},
            {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 5, "datetime": 1000},
            {"open": 3, "high": 3, "low": 3, "close": 3, "volume": 5, "datetime": 2000},
            {"open": 9},
        ]
    }

    candles = parse_candles(data)

    assert [c.time for c in candles] == [1, 2]
    assert candles[1].close_cents == 300  # the later duplicate wins
    assert parse_candles({"empty": True}) == []


def test_fetch_asks_for_the_regular_session_and_builds_hours():
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            start = at(10, 9, 30) * 1000
            return {"candles": [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10, "datetime": start + i * 1_800_000} for i in range(4)]}

    class Client:
        async def get_price_history_every_thirty_minutes(self, symbol, **kwargs):
            calls.append((symbol, kwargs))
            return Response()

    now = datetime(2026, 11, 10, 22, 0, tzinfo=timezone.utc)
    hours = asyncio.run(fetch_candles(Client(), "AAPL", "1h", now))

    symbol, kwargs = calls[0]
    assert symbol == "AAPL"
    assert kwargs["need_extended_hours_data"] is False
    assert kwargs["end_datetime"] == now
    assert [h.volume for h in hours] == [20, 20]
    assert hours[0].high_cents == 200 and hours[0].low_cents == 50
