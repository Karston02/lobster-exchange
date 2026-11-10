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

class Order:
    """One of the bot's resting orders."""

    id: int
    side: Side
    price: int
    """In ticks."""
    quantity: int
    """Unfilled quantity, in lots."""

class Fill:
    """One fill of a bot order."""

    time_ns: int
    """Exchange time, in nanoseconds since 1970."""
    order_id: int
    side: Side
    price: int
    """In ticks."""
    quantity: int
    """In lots."""
    maker: bool
    """True if the bot's order was resting, False if it crossed the book."""
    fee: int
    """In tick-lots."""

class Backtest:
    """A recording replayed through the engine while a strategy trades in it.

    Money (cash, fees, PnL) is integer tick-lots: one price tick times one
    size lot. For BTC-USD that's $0.01 x 0.00000001 BTC = $1e-10.
    """

    def __init__(
        self,
        path: str,
        latency_ms: float = 10.0,
        maker_fee_bps: int = 0,
        taker_fee_bps: int = 0,
        trade_lead_ms: float = 0.0,
    ) -> None: ...
    def read_summary(self) -> dict[str, int]:
        """Problems found while reading the file. All but "lines" should be zero."""

    @property
    def now_ns(self) -> int:
        """The current exchange time, in nanoseconds since 1970."""
    def run_until(self, time_ns: int) -> None:
        """Process everything up to and including `time_ns`."""
    def step(self) -> bool:
        """Process the next single event. False if nothing was left."""
    def next_event_ns(self) -> Optional[int]: ...
    def market_finished(self) -> bool:
        """Whether all market data has been replayed. Stop the strategy loop here."""

    def submit_limit(self, side: Side, price: int, quantity: int) -> int:
        """Send a limit order; returns its id. It arrives after the latency."""
    def submit_ioc(self, side: Side, price: int, quantity: int) -> int: ...
    def submit_market(self, side: Side, quantity: int) -> int: ...
    def cancel(self, id: int) -> None:
        """Send a cancel. It's rejected if the order fills first."""
    def open_orders(self) -> list[Order]: ...
    def queue_ahead(self, id: int) -> Optional[int]:
        """Quantity waiting ahead of a resting order, or None if it isn't resting."""
    def take_fills(self) -> list[Fill]:
        """The bot's fills since the last call."""

    def best_bid(self) -> Optional[tuple[int, int]]:
        """(price, quantity) of Coinbase's best bid."""
    def best_ask(self) -> Optional[tuple[int, int]]: ...
    def mid(self) -> Optional[int]:
        """Midpoint in ticks, rounded down."""
    def top(self, side: Side, n: int) -> list[tuple[int, int]]: ...

    @property
    def position(self) -> int:
        """In lots: positive owns BTC, negative is short."""
    @property
    def cash(self) -> int:
        """In tick-lots, starting at 0."""
    @property
    def fees_paid(self) -> int: ...
    @property
    def fill_count(self) -> int: ...
    @property
    def rejections(self) -> int: ...
    @property
    def unfilled_trade_volume(self) -> int: ...
    def pnl_at(self, price: int) -> int: ...
    def pnl_at_mid(self) -> Optional[int]: ...
