"""All linked accounts rolled into one portfolio, for the Home page.

The server does this sum so every page (and later, alerts) agrees on the
numbers. The browser only formats them.
"""

from dataclasses import dataclass

from .models import Account


@dataclass(frozen=True)
class Holding:
    """One symbol across every account."""

    symbol: str
    description: str
    quantity: float
    market_value_cents: int
    day_change_cents: int


@dataclass(frozen=True)
class Portfolio:
    total_value_cents: int
    day_change_cents: int
    previous_value_cents: int  # at yesterday's close: total minus today's change
    cash_cents: int
    account_count: int
    holdings: list[Holding]  # biggest first


def summarize(accounts: list[Account]) -> Portfolio:
    holdings: dict[str, Holding] = {}
    for account in accounts:
        for p in account.positions:
            seen = holdings.get(p.symbol)
            holdings[p.symbol] = Holding(
                symbol=p.symbol,
                description=(seen.description if seen else "") or p.description,
                quantity=(seen.quantity if seen else 0) + p.quantity,
                market_value_cents=(seen.market_value_cents if seen else 0) + p.market_value_cents,
                day_change_cents=(seen.day_change_cents if seen else 0) + p.day_change_cents,
            )
    total = sum(a.total_value_cents for a in accounts)
    change = sum(a.day_change_cents for a in accounts)
    return Portfolio(
        total_value_cents=total,
        day_change_cents=change,
        previous_value_cents=total - change,
        cash_cents=sum(a.cash_cents for a in accounts),
        account_count=len(accounts),
        holdings=sorted(holdings.values(), key=lambda h: h.market_value_cents, reverse=True),
    )
