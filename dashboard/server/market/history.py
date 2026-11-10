"""Stock candles from Schwab's price history.

Schwab's response: {"symbol": ..., "empty": bool, "candles": [{"open", "high",
"low", "close", "volume", "datetime" (Unix milliseconds)}]} (field names checked
against a real response, Nov 2026). Only the regular session is requested, so
intraday charts have no pre- or after-hours bars.
"""

from datetime import datetime
from typing import Any

from account.money import scaled

from .candles import Candle, CandleSeries, combine, sorted_unique
from .timeframes import TIMEFRAMES, session_bucket

CHEAP_STOCK = 1.0  # under $1, US stocks can trade in $0.0001 steps


def stock_decimals(data: dict) -> int:
    """2 decimals (cents), or 4 for a stock trading under $1."""
    closes = [raw.get("close") for raw in data.get("candles", []) if raw.get("close") is not None]
    return 4 if closes and float(closes[-1]) < CHEAP_STOCK else 2


def parse_candles(data: dict, decimals: int) -> list[Candle]:
    return sorted_unique(
        [
            Candle(
                time=int(raw["datetime"]) // 1000,
                open=scaled(raw.get("open"), decimals),
                high=scaled(raw.get("high"), decimals),
                low=scaled(raw.get("low"), decimals),
                close=scaled(raw.get("close"), decimals),
                volume=float(raw.get("volume") or 0),
            )
            for raw in data.get("candles", [])
            if "datetime" in raw
        ]
    )


async def fetch_candles(client: Any, symbol: str, timeframe: str, now: datetime) -> CandleSeries:
    frame = TIMEFRAMES[timeframe]
    response = await getattr(client, frame.method)(
        symbol,
        start_datetime=now - frame.lookback,
        end_datetime=now,
        need_extended_hours_data=False,
    )
    response.raise_for_status()
    data = response.json()
    decimals = stock_decimals(data)
    candles = parse_candles(data, decimals)
    if frame.session_bucket_s:
        candles = combine(candles, session_bucket(frame.session_bucket_s))
    return CandleSeries(symbol=symbol, timeframe=timeframe, source="schwab", decimals=decimals, candles=candles)
