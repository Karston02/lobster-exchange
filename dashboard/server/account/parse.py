"""Turns Schwab's account and order JSON into our records.

Checked against the field names Schwab really sends (from
`connectors/schwab/account_fields.py`, Nov 2026). Missing fields fall back to
zero or empty rather than crashing.
"""

from .models import Account, Order, Position
from .money import cents, mask

# Order statuses that mean "still waiting", from schwab-py's Client.Order.Status
OPEN_STATUSES = {
    "AWAITING_PARENT_ORDER", "AWAITING_CONDITION", "AWAITING_STOP_CONDITION", "AWAITING_MANUAL_REVIEW",
    "ACCEPTED", "AWAITING_UR_OUT", "PENDING_ACTIVATION", "QUEUED", "WORKING", "NEW",
    "AWAITING_RELEASE_TIME", "PENDING_ACKNOWLEDGEMENT", "PENDING_RECALL", "PENDING_CANCEL", "PENDING_REPLACE",
}  # fmt: skip


def parse_accounts(data: list[dict]) -> list[Account]:
    """The response of GET /accounts?fields=positions: one entry per linked account."""
    return [_account(item.get("securitiesAccount", {})) for item in data]


def _account(raw: dict) -> Account:
    balances = raw.get("currentBalances", {})
    positions = [_position(p) for p in raw.get("positions", [])]
    # Margin accounts report buyingPower; cash accounts only cashAvailableForTrading
    buying_power = balances.get("buyingPower", balances.get("cashAvailableForTrading"))
    last4 = mask(raw.get("accountNumber", ""))
    return Account(
        last4=last4,
        name=last4,  # the service swaps in your name for it
        type=raw.get("type", ""),
        total_value_cents=cents(balances.get("liquidationValue")),
        cash_cents=cents(balances.get("cashBalance", balances.get("cashAvailableForTrading"))),
        buying_power_cents=None if buying_power is None else cents(buying_power),
        day_change_cents=sum(p.day_change_cents for p in positions),
        open_pnl_cents=sum(p.open_pnl_cents for p in positions),
        positions=sorted(positions, key=lambda p: p.market_value_cents, reverse=True),
    )


def _position(raw: dict) -> Position:
    instrument = raw.get("instrument", {})
    quantity = float(raw.get("longQuantity", 0)) - float(raw.get("shortQuantity", 0))
    value = cents(raw.get("marketValue"))
    return Position(
        symbol=instrument.get("symbol", "?"),
        description=instrument.get("description", ""),
        asset_type=instrument.get("assetType", ""),
        quantity=quantity,
        average_price_cents=cents(raw.get("averagePrice")),
        price_cents=round(value / quantity) if quantity else 0,
        market_value_cents=value,
        day_change_cents=cents(raw.get("currentDayProfitLoss")),
        open_pnl_cents=cents(raw.get("longOpenProfitLoss", 0)) + cents(raw.get("shortOpenProfitLoss", 0)),
    )


def parse_orders(data: list[dict]) -> list[Order]:
    """The response of GET /orders, newest first."""
    orders = [_order(item) for item in data]
    return sorted(orders, key=lambda o: o.entered_time, reverse=True)


def _order(raw: dict) -> Order:
    legs = raw.get("orderLegCollection") or [{}]
    leg = legs[0]  # multi-leg orders (options spreads) are out of scope
    status = raw.get("status", "UNKNOWN")
    price = raw.get("price", raw.get("stopPrice"))
    return Order(
        order_id=str(raw.get("orderId", "")),
        account_last4=mask(raw.get("accountNumber", "")),
        symbol=leg.get("instrument", {}).get("symbol", "?"),
        side=leg.get("instruction", ""),
        order_type=raw.get("orderType", ""),
        quantity=float(raw.get("quantity", 0)),
        filled_quantity=float(raw.get("filledQuantity", 0)),
        price_cents=None if price is None else cents(price),
        status=status,
        is_open=status in OPEN_STATUSES,
        entered_time=raw.get("enteredTime", ""),
    )
