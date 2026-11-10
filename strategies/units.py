"""Converting the engine's integer units into dollars and BTC, for display.

The engine never uses floats: prices are ticks, sizes are lots, and money is
tick-lots (one tick times one lot). These helpers turn those into human
numbers at the very end, when printing or plotting. For BTC-USD:

- 1 tick = $0.01
- 1 lot  = 0.00000001 BTC (one satoshi)
- 1 tick-lot = $0.0000000001
"""

TICKS_PER_DOLLAR = 100
LOTS_PER_BTC = 100_000_000
NS_PER_SECOND = 1_000_000_000


def usd(tick_lots: int) -> float:
    """Money (cash, fees, PnL) in dollars."""
    return tick_lots / (TICKS_PER_DOLLAR * LOTS_PER_BTC)


def price_usd(ticks: int) -> float:
    """A price in dollars."""
    return ticks / TICKS_PER_DOLLAR


def btc(lots: int) -> float:
    """A size or position in BTC."""
    return lots / LOTS_PER_BTC


def lots(btc_amount: float) -> int:
    """A BTC amount as a whole number of lots (for placing orders)."""
    return round(btc_amount * LOTS_PER_BTC)
