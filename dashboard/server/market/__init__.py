"""Market data for charts: candles for any symbol and timeframe.

    from market import TIMEFRAMES, CoinbaseMarket, fetch_candles, is_crypto

Stocks come from Schwab (history.py), crypto from Coinbase (coinbase.py),
picked by the symbol's shape (symbols.py).

Prices are whole numbers (never floats) in units of 10^-decimals, with the
decimals given per series: see candles.py.
"""

from .candles import Candle, CandleSeries
from .coinbase import CoinbaseMarket, SourceUnavailable, UnknownSymbol
from .history import fetch_candles
from .symbols import is_crypto
from .timeframes import TIMEFRAMES

__all__ = [
    "Candle",
    "CandleSeries",
    "CoinbaseMarket",
    "SourceUnavailable",
    "TIMEFRAMES",
    "UnknownSymbol",
    "fetch_candles",
    "is_crypto",
]
