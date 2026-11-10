"""Candles (open, high, low, close, volume over one period), and joining them into longer ones."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    time: int  # when the period starts, in Unix seconds (UTC)
    open_cents: int
    high_cents: int
    low_cents: int
    close_cents: int
    volume: int


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
                open_cents=last.open_cents,
                high_cents=max(last.high_cents, c.high_cents),
                low_cents=min(last.low_cents, c.low_cents),
                close_cents=c.close_cents,
                volume=last.volume + c.volume,
            )
        else:
            out.append(Candle(start, c.open_cents, c.high_cents, c.low_cents, c.close_cents, c.volume))
    return out
