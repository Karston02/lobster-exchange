"""Reprices accounts from live prices, starting from Schwab's own numbers.

Rather than recomputing everything, each position moves by how far its
price moved since the account snapshot: shares x (live price - snapshot price).
That keeps Schwab's own day change and open P&L (which account for shares
bought today, fees, and so on) and only adds the price move on top.
"""

import dataclasses
from decimal import ROUND_HALF_UP, Decimal

from account.models import Account, Position
from account.quotes import Quote

from .prices import LivePrice, LivePrices


def revalue(accounts: list[Account], prices: LivePrices) -> list[Account]:
    return [_account(a, prices) for a in accounts]


def live_quote(price: LivePrice) -> Quote:
    """A live price in the same shape as a REST quote, for SPY on Home."""
    return Quote(
        symbol=price.symbol,
        last_cents=price.last_cents,
        previous_close_cents=price.close_cents,
        change_cents=price.change_cents,
        change_pct=price.change_pct,
    )


def _account(account: Account, prices: LivePrices) -> Account:
    positions = [_position(p, prices.get(p.symbol)) for p in account.positions]
    moved = sum(new.market_value_cents - old.market_value_cents for new, old in zip(positions, account.positions))
    if moved == 0:
        return account
    return dataclasses.replace(
        account,
        positions=sorted(positions, key=lambda p: p.market_value_cents, reverse=True),
        total_value_cents=account.total_value_cents + moved,
        day_change_cents=account.day_change_cents + moved,
        open_pnl_cents=account.open_pnl_cents + moved,
    )


def _position(position: Position, price: LivePrice | None) -> Position:
    # Options aren't in the equity stream, so they keep their snapshot value
    if price is None or position.asset_type == "OPTION" or price.last_cents == position.price_cents:
        return position
    moved = _times(price.last_cents - position.price_cents, position.quantity)
    return dataclasses.replace(
        position,
        price_cents=price.last_cents,
        market_value_cents=position.market_value_cents + moved,
        day_change_cents=position.day_change_cents + moved,
        open_pnl_cents=position.open_pnl_cents + moved,
    )


def _times(cents_per_share: int, quantity: float) -> int:
    """Cents x shares, rounding halves up (shares can be fractional)."""
    return int((Decimal(cents_per_share) * Decimal(str(quantity))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
