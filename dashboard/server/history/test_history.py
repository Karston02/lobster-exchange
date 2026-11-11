"""Tests for value history. Run: pytest dashboard/server/history"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from account import SchwabUnavailable
from db import open_database
from history import HistoryRecorder, build_history
from history.ranges import last_session
from history.store import last_value_before, record_values, values_between
from market import Candle

NY = ZoneInfo("America/New_York")


def ny(day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(2026, 11, day, hour, minute, tzinfo=NY).timestamp())


@pytest.fixture
def conn(tmp_path):
    connection = open_database(tmp_path / "lobster.db")
    yield connection
    connection.close()


def test_sessions_roll_back_over_nights_and_weekends():
    assert last_session(ny(10, 12)) == (ny(10, 9, 30), ny(10, 16))  # Tuesday midday: today
    assert last_session(ny(10, 20)) == (ny(10, 9, 30), ny(10, 16))  # Tuesday evening: still today
    assert last_session(ny(10, 8)) == (ny(9, 9, 30), ny(9, 16))  # Tuesday before the open: Monday
    assert last_session(ny(9, 8)) == (ny(6, 9, 30), ny(6, 16))  # Monday before the open: Friday
    assert last_session(ny(15, 12)) == (ny(13, 9, 30), ny(13, 16))  # Sunday: Friday


def test_values_are_thinned_to_the_last_in_each_bucket(conn):
    for minute in range(10):
        record_values(conn, 600 + minute * 60, {"all": 1000 + minute})

    five_minute = values_between(conn, "all", 0, 10_000, 300)

    assert [(v.time, v.value_cents) for v in five_minute] == [(840, 1004), (1140, 1009)]
    assert last_value_before(conn, "all", 600) is None
    assert last_value_before(conn, "all", 700).value_cents == 1001


def test_recording_a_minute_twice_keeps_the_later(conn):
    record_values(conn, 60, {"all": 1})
    record_values(conn, 60, {"all": 2})

    assert [v.value_cents for v in values_between(conn, "all", 0, 100, 60)] == [2]


@dataclass
class Series:
    candles: list


class FakeSchwab:
    def __init__(self, candles=None, available=True):
        self.series = Series(candles or [])
        self.available = available
        self.asked = []

    async def candles(self, symbol, timeframe):
        self.asked.append((symbol, timeframe))
        if not self.available:
            raise SchwabUnavailable("error", "down")
        return self.series


def spy(t, close):
    return Candle(t, close, close, close, close, 100)


def test_one_day_uses_the_previous_close_and_scales_spy_to_it(conn):
    record_values(conn, ny(9, 15, 59), {"all": 100_000})  # Monday's last value: the previous close
    record_values(conn, ny(10, 9, 31), {"all": 101_000})
    record_values(conn, ny(10, 10, 0), {"all": 102_000})
    schwab = FakeSchwab([spy(ny(9, 15, 59), 50_000), spy(ny(10, 9, 31), 50_500), spy(ny(10, 10, 0), 51_000)])
    now = datetime.fromtimestamp(ny(10, 10, 5), timezone.utc)

    chart = asyncio.run(build_history(conn, schwab, "1D", "all", now))

    assert chart["base_cents"] == 100_000
    assert [p["value_cents"] for p in chart["points"]] == [101_000, 102_000]
    # SPY up 1% then 2% from its previous close, drawn from the portfolio's previous close
    assert [p["value_cents"] for p in chart["benchmark"]] == [101_000, 102_000]
    assert schwab.asked == [("SPY", "1m")]


def test_the_first_day_falls_back_to_the_live_previous_close(conn):
    record_values(conn, ny(10, 9, 31), {"all": 101_000})
    now = datetime.fromtimestamp(ny(10, 10), timezone.utc)

    chart = asyncio.run(build_history(conn, FakeSchwab(), "1D", "all", now, live_previous_close=99_000))

    assert chart["base_cents"] == 99_000


def test_longer_ranges_start_both_lines_together(conn):
    record_values(conn, ny(2, 12), {"all": 200_000})
    record_values(conn, ny(9, 12), {"all": 210_000})
    schwab = FakeSchwab([spy(ny(2, 12), 600), spy(ny(9, 12), 630)])
    now = datetime.fromtimestamp(ny(10, 12), timezone.utc)

    chart = asyncio.run(build_history(conn, schwab, "1M", "all", now))

    assert chart["base_cents"] == 200_000
    assert [p["value_cents"] for p in chart["benchmark"]] == [200_000, 210_000]  # SPY +5%, portfolio +5%


def test_single_accounts_get_no_spy_and_spy_outages_are_quiet(conn):
    record_values(conn, ny(9, 12), {"all": 5, "1234": 3})
    now = datetime.fromtimestamp(ny(10, 12), timezone.utc)

    one = asyncio.run(build_history(conn, FakeSchwab([spy(ny(9, 12), 1)]), "1W", "1234", now))
    down = asyncio.run(build_history(conn, FakeSchwab(available=False), "1W", "all", now))

    assert one["benchmark"] == [] and [p["value_cents"] for p in one["points"]] == [3]
    assert down["benchmark"] == [] and down["points"]


class FakeFeed:
    def __init__(self, message):
        self.message = message

    def latest(self):
        return self.message


def message(as_of: float) -> dict:
    return {
        "as_of": datetime.fromtimestamp(as_of, timezone.utc).isoformat(),
        "portfolio": {"total_value_cents": 700},
        "accounts": [{"last4": "…1234", "total_value_cents": 300}, {"last4": "…4428", "total_value_cents": 400}],
    }


def test_the_recorder_writes_the_portfolio_and_each_account(tmp_path):
    db = tmp_path / "lobster.db"
    open_database(db).close()
    now = 1_794_000_030.0
    recorder = HistoryRecorder(FakeFeed(message(now - 20)), db, clock=lambda: now)

    assert recorder.record_once() is True

    conn = open_database(db)
    rows = conn.execute("SELECT account, time, total_cents FROM value_history ORDER BY account").fetchall()
    assert [tuple(r) for r in rows] == [("1234", 1_794_000_000, 300), ("4428", 1_794_000_000, 400), ("all", 1_794_000_000, 700)]


def test_the_recorder_skips_stale_or_missing_numbers(tmp_path):
    db = tmp_path / "lobster.db"
    open_database(db).close()
    now = 1_794_000_030.0

    assert HistoryRecorder(FakeFeed(None), db, clock=lambda: now).record_once() is False
    assert HistoryRecorder(FakeFeed(message(now - 600)), db, clock=lambda: now).record_once() is False
