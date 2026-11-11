"""One chart's worth of history: the recorded values, the line they're measured
against, and SPY scaled to start at the same value.

Scaling SPY: "what if this money had been in SPY instead". SPY is multiplied by
(portfolio base / SPY base), so both lines start together and their gap is the
difference in returns. For 1D the base is the previous close, matching
"today's change"; for longer ranges it's the first value in the range.
"""

import sqlite3
from datetime import datetime
from typing import Any

from account import SchwabUnavailable

from .ranges import RANGES, window
from .store import Value, first_time, last_value_before, values_between

BENCHMARK = "SPY"


async def build_history(
    conn: sqlite3.Connection,
    schwab: Any,
    key: str,
    account: str,
    now: datetime,
    live_previous_close: int | None = None,
) -> dict:
    """`account` is 'all' or an account's last four digits. `schwab` provides SPY candles
    (only asked for the whole portfolio). `live_previous_close` is used for 1D when no value
    was recorded before the session (e.g. the first day of recording)."""
    spec = RANGES[key]
    start, end = window(key, now.timestamp(), first_time(conn, account))
    points = values_between(conn, account, start, end, spec.bucket_s)

    if key == "1D":
        before = last_value_before(conn, account, start)
        base = before.value_cents if before else live_previous_close
    else:
        base = points[0].value_cents if points else None
    if base is None and points:
        base = points[0].value_cents

    benchmark: list[Value] = []
    if account == "all" and base is not None:
        benchmark = await _scaled_spy(schwab, spec.spy_timeframe, key, start, end, base)

    return {
        "range": key,
        "start": start,
        "end": end,
        "base_cents": base,
        "points": [v.__dict__ for v in points],
        "benchmark": [v.__dict__ for v in benchmark],
    }


async def _scaled_spy(schwab: Any, timeframe: str, key: str, start: int, end: int, base: int) -> list[Value]:
    try:
        series = await schwab.candles(BENCHMARK, timeframe)
    except SchwabUnavailable:
        return []  # the chart simply shows no SPY line
    inside = [c for c in series.candles if start <= c.time <= end]
    if not inside:
        return []
    if key == "1D":
        earlier = [c for c in series.candles if c.time < start]
        spy_base = earlier[-1].close if earlier else inside[0].open  # yesterday's close
    else:
        spy_base = inside[0].close
    if not spy_base:
        return []
    # Candle prices are whole units of 10^-decimals; the units cancel in the ratio
    return [Value(c.time, round(base * c.close / spy_base)) for c in inside]
