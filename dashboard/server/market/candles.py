"""Candles (open, high, low, close, volume over one period), and joining them into longer ones.

Prices are whole numbers in units of 10^-decimals of a dollar, where
`decimals` belongs to the whole series: 2 (cents) for most stocks, more for
cheap ones and for coins like SHIB-USD, whose price moves in 0.00000001 steps.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    time: int  # when the period starts, in Unix seconds (UTC)
    open: int
    high: int
    low: int
    close: int
    volume: float  # shares or coins; crypto volume is fractional. Display only.


@dataclass(frozen=True)
class CandleSeries:
    symbol: str
    timeframe: str
    source: str  # "schwab" or "coinbase"
    decimals: int  # prices are in units of 10^-decimals
    candles: list[Candle]


def combine(candles: list[Candle], bucket: Callable[[int], int]) -> list[Candle]:
    """Joins consecutive candles that share a bucket into one.

    `bucket(time)` returns the start time of the longer period a candle belongs
    to; candles must be sorted by time. Open comes from the first, close from
    the last, high and low are the extremes, volumes add up.
    """
    out: list[Candle] = []
    for c in candles:
        start = bucket(c.time)
        if out and out[-1].time == start:
            last = out[-1]
            out[-1] = Candle(
                time=start,
                open=last.open,
                high=max(last.high, c.high),
                low=min(last.low, c.low),
                close=c.close,
                volume=last.volume + c.volume,
            )
        else:
            out.append(Candle(start, c.open, c.high, c.low, c.close, c.volume))
    return out


def sorted_unique(candles: list[Candle]) -> list[Candle]:
    """Ascending by time with one candle per time (the last one seen wins), as charts require."""
    by_time = {c.time: c for c in candles}
    return [by_time[t] for t in sorted(by_time)]
