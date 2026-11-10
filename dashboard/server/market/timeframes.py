"""The chart timeframes, and how each is fetched from Schwab.

Schwab offers 1, 5, 10, 15 and 30-minute, daily and weekly candles. 1h and
4h don't exist there, so they're built from 30-minute candles. Their periods
start at the 9:30 AM Eastern open (9:30, 10:30, ... for 1h; 9:30 and 1:30 for
4h), as TradingView does for US stocks, rather than on the clock hour.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

EXCHANGE_TZ = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)


@dataclass(frozen=True)
class Timeframe:
    method: str  # the schwab-py method that fetches the base candles
    lookback: timedelta  # how much history to load
    session_bucket_s: int | None = None  # join base candles into periods of this length, from the open


TIMEFRAMES = {
    "1m": Timeframe("get_price_history_every_minute", timedelta(days=10)),
    "5m": Timeframe("get_price_history_every_five_minutes", timedelta(days=60)),
    "15m": Timeframe("get_price_history_every_fifteen_minutes", timedelta(days=120)),
    "1h": Timeframe("get_price_history_every_thirty_minutes", timedelta(days=270), session_bucket_s=3600),
    "4h": Timeframe("get_price_history_every_thirty_minutes", timedelta(days=270), session_bucket_s=4 * 3600),
    "D": Timeframe("get_price_history_every_day", timedelta(days=365 * 10)),
    "W": Timeframe("get_price_history_every_week", timedelta(days=365 * 20)),
}


def session_bucket(period_s: int):
    """A bucket function for `combine`: the start of the period, counted from that day's 9:30 open."""

    def bucket(t: int) -> int:
        local = datetime.fromtimestamp(t, EXCHANGE_TZ)
        open_ = datetime.combine(local.date(), SESSION_OPEN, EXCHANGE_TZ)
        offset = int((local - open_).total_seconds())
        return int(open_.timestamp()) + (offset // period_s) * period_s

    return bucket


def in_regular_session(t: float) -> bool:
    """Monday to Friday, 9:30 AM to 4:00 PM Eastern. (Holidays aren't known; nothing trades then anyway.)"""
    local = datetime.fromtimestamp(t, EXCHANGE_TZ)
    return local.weekday() < 5 and SESSION_OPEN <= local.time() < SESSION_CLOSE
