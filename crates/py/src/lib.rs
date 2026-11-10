//! Python bindings for the matching engine, built with PyO3.
//!
//! Python sees a module called `lobster` with two classes, `Engine` and
//! `Event`. Sides are the strings `"buy"` and `"sell"`; prices and quantities
//! are plain integers (ticks and lots), the same as in Rust.
//!
//! Each wrapper is thin on purpose: it converts Python values into the
//! engine's types, calls the engine, and converts the results back. All the
//! logic stays in `lobster-engine`, where it's tested.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use lobster_engine::{
    CancelReason, Command, Engine, Event, OrderId, Price, Quantity, RejectReason, Side,
};

/// Converts `"buy"` / `"sell"` into a `Side`, or raises `ValueError`.
fn parse_side(side: &str) -> PyResult<Side> {
    match side {
        "buy" => Ok(Side::Buy),
        "sell" => Ok(Side::Sell),
        other => Err(PyValueError::new_err(format!(
            "side must be \"buy\" or \"sell\", not {other:?}"
        ))),
    }
}

/// Something that happened as a result of a command.
///
/// One flat class instead of one class per kind keeps it simple to use from
/// Python: check `event.kind`, then read the fields that kind fills in.
#[pyclass(name = "Event", module = "lobster", frozen, get_all)]
#[derive(Debug, Clone, Default)]
pub struct PyEvent {
    /// "accepted", "trade", "cancelled" or "rejected".
    kind: String,
    /// The order this is about (accepted, cancelled, rejected).
    order_id: Option<u64>,
    /// Trades only: the resting order.
    maker_id: Option<u64>,
    /// Trades only: the incoming order.
    taker_id: Option<u64>,
    /// Trades only: price in ticks.
    price: Option<u64>,
    /// Trades only: quantity in lots.
    quantity: Option<u64>,
    /// Cancels only: how much was still unfilled.
    remaining: Option<u64>,
    /// Why an order was cancelled or rejected.
    reason: Option<String>,
}

#[pymethods]
impl PyEvent {
    fn __repr__(&self) -> String {
        match self.kind.as_str() {
            "trade" => format!(
                "Event(trade: maker {} / taker {}, {} @ {})",
                self.maker_id.unwrap_or_default(),
                self.taker_id.unwrap_or_default(),
                self.quantity.unwrap_or_default(),
                self.price.unwrap_or_default(),
            ),
            "cancelled" => format!(
                "Event(cancelled: order {}, {} remaining, {})",
                self.order_id.unwrap_or_default(),
                self.remaining.unwrap_or_default(),
                self.reason.as_deref().unwrap_or("")
            ),
            "rejected" => format!(
                "Event(rejected: order {}, {})",
                self.order_id.unwrap_or_default(),
                self.reason.as_deref().unwrap_or("")
            ),
            _ => format!(
                "Event({}: order {})",
                self.kind,
                self.order_id.unwrap_or_default()
            ),
        }
    }
}

impl From<Event> for PyEvent {
    fn from(event: Event) -> Self {
        match event {
            Event::Accepted { id } => PyEvent {
                kind: "accepted".into(),
                order_id: Some(id.0),
                ..Default::default()
            },
            Event::Trade(trade) => PyEvent {
                kind: "trade".into(),
                maker_id: Some(trade.maker_order_id.0),
                taker_id: Some(trade.taker_order_id.0),
                price: Some(trade.price.0),
                quantity: Some(trade.quantity.0),
                ..Default::default()
            },
            Event::Cancelled {
                id,
                remaining,
                reason,
            } => PyEvent {
                kind: "cancelled".into(),
                order_id: Some(id.0),
                remaining: Some(remaining.0),
                reason: Some(
                    match reason {
                        CancelReason::Requested => "requested",
                        CancelReason::NoLiquidity => "no_liquidity",
                    }
                    .into(),
                ),
                ..Default::default()
            },
            Event::Rejected { id, reason } => PyEvent {
                kind: "rejected".into(),
                order_id: Some(id.0),
                reason: Some(
                    match reason {
                        RejectReason::ZeroQuantity => "zero_quantity",
                        RejectReason::ZeroPrice => "zero_price",
                        RejectReason::DuplicateOrderId => "duplicate_order_id",
                        RejectReason::UnknownOrderId => "unknown_order_id",
                    }
                    .into(),
                ),
                ..Default::default()
            },
        }
    }
}

/// A matching engine for one market, usable from Python.
#[pyclass(name = "Engine", module = "lobster")]
pub struct PyEngine {
    engine: Engine,
}

impl PyEngine {
    /// Sends one command and converts the events for Python.
    fn run(&mut self, command: Command) -> Vec<PyEvent> {
        self.engine
            .process(command)
            .into_iter()
            .map(PyEvent::from)
            .collect()
    }
}

#[pymethods]
impl PyEngine {
    #[new]
    fn new() -> Self {
        PyEngine {
            engine: Engine::new(),
        }
    }

    /// Trade at `price` or better; any remainder rests on the book.
    fn submit_limit(
        &mut self,
        id: u64,
        side: &str,
        price: u64,
        quantity: u64,
    ) -> PyResult<Vec<PyEvent>> {
        Ok(self.run(Command::NewLimit {
            id: OrderId(id),
            side: parse_side(side)?,
            price: Price(price),
            quantity: Quantity(quantity),
        }))
    }

    /// Trade now at any price; any remainder is cancelled.
    fn submit_market(&mut self, id: u64, side: &str, quantity: u64) -> PyResult<Vec<PyEvent>> {
        Ok(self.run(Command::NewMarket {
            id: OrderId(id),
            side: parse_side(side)?,
            quantity: Quantity(quantity),
        }))
    }

    /// Immediate-or-cancel: trade now at `price` or better; cancel the rest.
    fn submit_ioc(
        &mut self,
        id: u64,
        side: &str,
        price: u64,
        quantity: u64,
    ) -> PyResult<Vec<PyEvent>> {
        Ok(self.run(Command::NewImmediateOrCancel {
            id: OrderId(id),
            side: parse_side(side)?,
            price: Price(price),
            quantity: Quantity(quantity),
        }))
    }

    /// Remove a resting order.
    fn cancel(&mut self, id: u64) -> Vec<PyEvent> {
        self.run(Command::Cancel { id: OrderId(id) })
    }

    fn best_bid(&self) -> Option<u64> {
        self.engine.book().best_bid().map(|price| price.0)
    }

    fn best_ask(&self) -> Option<u64> {
        self.engine.book().best_ask().map(|price| price.0)
    }

    fn spread(&self) -> Option<u64> {
        self.engine.book().spread()
    }

    /// Total resting quantity at one price.
    fn quantity_at(&self, side: &str, price: u64) -> PyResult<u64> {
        let side = parse_side(side)?;
        Ok(self.engine.book().quantity_at(side, Price(price)).0)
    }

    /// How many orders are resting, across both sides.
    fn order_count(&self) -> usize {
        self.engine.book().order_count()
    }

    /// Whether an order with this id is resting.
    fn contains(&self, id: u64) -> bool {
        self.engine.book().contains(OrderId(id))
    }
}

/// The `lobster` Python module.
#[pymodule]
mod lobster {
    #[pymodule_export]
    use super::{PyEngine, PyEvent};
}
