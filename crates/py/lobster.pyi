"""Type hints for the `lobster` module, so editors can autocomplete it.

The real implementation is Rust (crates/py/src/lib.rs); this file only
describes it. Keep the two in sync.
"""

from typing import Literal, Optional

Side = Literal["buy", "sell"]

class Event:
    """Something that happened as a result of a command."""

    kind: Literal["accepted", "trade", "cancelled", "reduced", "rejected"]
    """Which kind of event this is; the other fields depend on it."""
    order_id: Optional[int]
    """The order this is about (accepted, cancelled, rejected)."""
    maker_id: Optional[int]
    """Trades only: the order that was resting on the book."""
    taker_id: Optional[int]
    """Trades only: the incoming order."""
    price: Optional[int]
    """Trades only: the price, in ticks."""
    quantity: Optional[int]
    """Trades only: the amount traded, in lots."""
    remaining: Optional[int]
    """Cancels and reductions: how much is (or was) still unfilled."""
    reason: Optional[str]
    """Cancels: "requested" or "no_liquidity". Rejections: "zero_quantity",
    "zero_price", "duplicate_order_id" or "unknown_order_id"."""

class Engine:
    """A matching engine for one market. Prices are integer ticks and
    quantities are integer lots, never floats."""

    def __init__(self) -> None: ...
    def submit_limit(self, id: int, side: Side, price: int, quantity: int) -> list[Event]:
        """Trade at `price` or better; any remainder rests on the book."""
    def submit_market(self, id: int, side: Side, quantity: int) -> list[Event]:
        """Trade now at any price; any remainder is cancelled."""
    def submit_ioc(self, id: int, side: Side, price: int, quantity: int) -> list[Event]:
        """Immediate-or-cancel: trade now at `price` or better; cancel the rest."""
    def cancel(self, id: int) -> list[Event]:
        """Remove a resting order."""
    def reduce(self, id: int, by: int) -> list[Event]:
        """Shrink a resting order by `by`, keeping its place in line."""
    def best_bid(self) -> Optional[int]: ...
    def best_ask(self) -> Optional[int]: ...
    def spread(self) -> Optional[int]: ...
    def quantity_at(self, side: Side, price: int) -> int:
        """Total resting quantity at one price."""
    def order_count(self) -> int:
        """How many orders are resting, across both sides."""
    def contains(self, id: int) -> bool:
        """Whether an order with this id is resting."""
