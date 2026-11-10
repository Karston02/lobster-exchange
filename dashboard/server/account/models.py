"""What the server knows about the account, as plain records.

Amounts are integer cents. Share quantities stay as Schwab sends them
(fractional shares exist); they are only displayed, never used for matching.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    symbol: str
    description: str  # Schwab leaves this out for some positions
    asset_type: str  # EQUITY, COLLECTIVE_INVESTMENT (ETFs), ...
    quantity: float  # negative when short
    average_price_cents: int  # what you paid per share, on average
    price_cents: int  # today's price per share: market value / quantity
    market_value_cents: int
    day_change_cents: int  # today's profit or loss on this position
    open_pnl_cents: int  # gain or loss since bought


@dataclass(frozen=True)
class Account:
    last4: str  # "…1234"; the full number is never stored
    name: str  # your name for it (LOBSTER_ACCOUNT_NAMES), else the last four digits
    type: str  # CASH or MARGIN
    total_value_cents: int  # what everything would be worth if sold now
    cash_cents: int
    buying_power_cents: int | None  # for cash accounts, the cash available for trading
    day_change_cents: int
    open_pnl_cents: int
    positions: list[Position]


@dataclass(frozen=True)
class Order:
    order_id: str  # a string: Schwab's ids can exceed what a JavaScript number holds exactly
    account_last4: str
    symbol: str
    side: str  # BUY, SELL, ...
    order_type: str  # LIMIT, MARKET, ...
    quantity: float
    filled_quantity: float
    price_cents: int | None  # None for market orders
    status: str
    is_open: bool  # still waiting to fill
    entered_time: str  # ISO 8601, as Schwab sends it
