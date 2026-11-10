"""Crypto candles from Coinbase Exchange's public market data (no login needed).

GET /products/{id}/candles?granularity=&start=&end= returns rows of
[time, low, high, open, close, volume], newest first, at most 300 per request,
with granularity one of 60, 300, 900, 3600, 21600, 86400 seconds (checked
against a live response, Nov 2026). Longer histories take several requests,
walking backwards. 4h and weekly don't exist there, so they're built from 1h
and daily candles. Crypto trades around the clock, so periods are aligned to
UTC (4h at 00:00, 04:00, ...; weeks start Monday).

GET /products/{id} gives `quote_increment`, the price step (0.01 for BTC-USD,
0.00000001 for SHIB-USD), which sets the series' decimals.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from account.money import scaled

from .candles import Candle, CandleSeries, combine, sorted_unique

BASE_URL = "https://api.exchange.coinbase.com"
MAX_PER_REQUEST = 300
CACHE_SECONDS = 30.0  # Coinbase asks that historical candles not be polled often
MONDAY_OFFSET_S = 4 * 86400  # 1970-01-01 was a Thursday; the first Monday was 4 days later


class UnknownSymbol(Exception):
    """The exchange doesn't list this symbol."""


class SourceUnavailable(Exception):
    """The exchange couldn't be reached or answered with an error."""


@dataclass(frozen=True)
class Frame:
    granularity_s: int  # the candle size Coinbase serves
    pages: int  # requests of 300 candles each
    bucket_s: int | None = None  # join into periods of this length (UTC)
    bucket_offset_s: int = 0


FRAMES = {
    "1m": Frame(60, pages=5),
    "5m": Frame(300, pages=4),
    "15m": Frame(900, pages=4),
    "1h": Frame(3600, pages=4),
    "4h": Frame(3600, pages=8, bucket_s=4 * 3600),
    "D": Frame(86400, pages=4),
    "W": Frame(86400, pages=6, bucket_s=7 * 86400, bucket_offset_s=MONDAY_OFFSET_S),
}


def utc_bucket(period_s: int, offset_s: int = 0):
    return lambda t: (t - offset_s) // period_s * period_s + offset_s


def decimals_of(increment: str) -> int:
    """'0.01' -> 2, '0.00000001' -> 8, '1' -> 0"""
    return max(0, -Decimal(increment).normalize().as_tuple().exponent)


def parse_rows(rows: list[list], decimals: int) -> list[Candle]:
    return [
        Candle(
            time=int(t),
            open=scaled(open_, decimals),
            high=scaled(high, decimals),
            low=scaled(low, decimals),
            close=scaled(close, decimals),
            volume=float(volume),
        )
        for t, low, high, open_, close, volume in rows
    ]


def _iso(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CoinbaseMarket:
    def __init__(self, http: Any = None, now=lambda: datetime.now(timezone.utc)):
        self._http = http  # an httpx.AsyncClient (or a fake in tests); made on first use
        self._now = now
        self._decimals: dict[str, int] = {}
        self._cache: dict[str, tuple[float, CandleSeries]] = {}
        self._lock = asyncio.Lock()

    async def candles(self, product: str, timeframe: str) -> CandleSeries:
        key = f"{product}:{timeframe}"
        async with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]
            series = await self._fetch(product, timeframe)
            self._cache[key] = (time.monotonic(), series)
            return series

    async def close(self) -> None:
        if self._http is not None and hasattr(self._http, "aclose"):
            await self._http.aclose()

    async def _fetch(self, product: str, timeframe: str) -> CandleSeries:
        frame = FRAMES[timeframe]
        decimals = await self._product_decimals(product)
        g = frame.granularity_s
        end = int(self._now().timestamp()) // g * g
        rows: list[list] = []
        for _ in range(frame.pages):
            start = end - (MAX_PER_REQUEST - 1) * g  # 300 points, counting both ends
            page = await self._get(f"/products/{product}/candles", {"granularity": g, "start": _iso(start), "end": _iso(end)})
            if not page:
                break  # no older history
            rows.extend(page)
            end = start - g
        candles = sorted_unique(parse_rows(rows, decimals))
        if frame.bucket_s:
            candles = combine(candles, utc_bucket(frame.bucket_s, frame.bucket_offset_s))
        return CandleSeries(symbol=product, timeframe=timeframe, source="coinbase", decimals=decimals, candles=candles)

    async def _product_decimals(self, product: str) -> int:
        if product not in self._decimals:
            info = await self._get(f"/products/{product}", {})
            self._decimals[product] = decimals_of(info.get("quote_increment", "0.01"))
        return self._decimals[product]

    async def _get(self, path: str, params: dict) -> Any:
        if self._http is None:
            import httpx  # installed with schwab-py

            self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
        try:
            response = await self._http.get(path, params=params)
        except Exception as error:  # network trouble
            raise SourceUnavailable(f"Coinbase couldn't be reached ({type(error).__name__})") from error
        if response.status_code in (400, 404):
            raise UnknownSymbol(f"Coinbase doesn't list {path.split('/')[2]}")
        if response.status_code >= 400:
            raise SourceUnavailable(f"Coinbase answered HTTP {response.status_code}")
        return response.json()
