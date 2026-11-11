"""The chart ranges (1D to All): which times each covers, how thinly, and which SPY candles match."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from market.timeframes import EXCHANGE_TZ, SESSION_CLOSE, SESSION_OPEN


@dataclass(frozen=True)
class Range:
    lookback: timedelta | None  # None: 1D (the session) or All (since recording began)
    bucket_s: int  # one point per this many seconds
    spy_timeframe: str  # SPY candles at about the same spacing


RANGES = {
    "1D": Range(None, 60, "1m"),
    "1W": Range(timedelta(days=7), 15 * 60, "15m"),
    "1M": Range(timedelta(days=30), 3600, "1h"),
    "1Y": Range(timedelta(days=365), 86400, "D"),
    "All": Range(None, 86400, "D"),
}


def last_session(now: float) -> tuple[int, int]:
    """The latest regular session that has started: today's from 9:30 AM Eastern on a weekday,
    otherwise the previous weekday's. (Market holidays aren't known; such a day just has no values.)"""
    day = datetime.fromtimestamp(now, EXCHANGE_TZ).date()
    started = datetime.combine(day, SESSION_OPEN, EXCHANGE_TZ).timestamp() <= now
    if day.weekday() >= 5 or not started:
        day -= timedelta(days=1)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
    open_ = datetime.combine(day, SESSION_OPEN, EXCHANGE_TZ)
    close = datetime.combine(day, SESSION_CLOSE, EXCHANGE_TZ)
    return int(open_.timestamp()), int(close.timestamp())


def window(key: str, now: float, first_recorded: int | None) -> tuple[int, int]:
    """(start, end) in Unix seconds for a range."""
    if key == "1D":
        return last_session(now)
    if key == "All":
        return (first_recorded if first_recorded is not None else int(now)), int(now)
    return int(now - RANGES[key].lookback.total_seconds()), int(now)
