"""Fetches candles from Schwab and turns them into our records.

Schwab's response: {"symbol": ..., "empty": bool, "candles": [{"open", "high",
"low", "close", "volume", "datetime" (Unix milliseconds)}]} (field names checked
against a real response, Nov 2026). Only the regular
session is requested, so intraday charts have no pre- or after-hours bars.
"""

from datetime import datetime
from typing import Any

from account.money import cents

from .candles import Candle, combine
from .timeframes import TIMEFRAMES, session_bucket


def parse_candles(data: dict) -> list[Candle]:
    candles = [
        Candle(
            time=int(raw["datetime"]) // 1000,
            open_cents=cents(raw.get("open")),
            high_cents=cents(raw.get("high")),
            low_cents=cents(raw.get("low")),
            close_cents=cents(raw.get("close")),
            volume=int(raw.get("volume") or 0),
        )
        for raw in data.get("candles", [])
        if "datetime" in raw
    ]
    # Charts need ascending, unique times
    unique = {c.time: c for c in candles}
    return [unique[t] for t in sorted(unique)]


async def fetch_candles(client: Any, symbol: str, timeframe: str, now: datetime) -> list[Candle]:
    frame = TIMEFRAMES[timeframe]
    response = await getattr(client, frame.method)(
        symbol,
        start_datetime=now - frame.lookback,
        end_datetime=now,
        need_extended_hours_data=False,
    )
    response.raise_for_status()
    candles = parse_candles(response.json())
    if frame.session_bucket_s:
        candles = combine(candles, session_bucket(frame.session_bucket_s))
    return candles
