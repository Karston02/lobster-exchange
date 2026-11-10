"""Which data source a symbol belongs to."""


def is_crypto(symbol: str) -> bool:
    """Coinbase products are written BASE-QUOTE (BTC-USD, ETH-USDC). US stock
    tickers never contain a dash at Schwab (class shares use a dot: BRK.B)."""
    return "-" in symbol
