//! The engine: the single entry point that turns commands into events.
//!
//! The engine owns the order book and decides what is allowed (validation and
//! rejections). The book only knows how to store and match orders.

use crate::book::OrderBook;
use crate::messages::{CancelReason, Command, Event, RejectReason};
use crate::types::{Order, OrderId, Price, Quantity, Side};

/// A matching engine for a single market (e.g. BTC-USD).
#[derive(Debug, Default)]
pub struct Engine {
    book: OrderBook,
}

impl Engine {
    /// Creates an engine with an empty book.
    pub fn new() -> Self {
        Self::default()
    }

    /// Processes one command and returns everything that happened, in order.
    ///
    /// This is the only way to change the engine's state, and it is
    /// deterministic: the same commands always produce the same events.
    pub fn process(&mut self, command: Command) -> Vec<Event> {
        match command {
            Command::NewLimit {
                id,
                side,
                price,
                quantity,
            } => self.new_limit(id, side, price, quantity),
            Command::NewMarket { id, side, quantity } => self.new_market(id, side, quantity),
            Command::Cancel { id } => self.cancel(id),
        }
    }

    /// Read-only access to the book, for queries like best bid and ask.
    pub fn book(&self) -> &OrderBook {
        &self.book
    }

    fn new_limit(
        &mut self,
        id: OrderId,
        side: Side,
        price: Price,
        quantity: Quantity,
    ) -> Vec<Event> {
        if price.0 == 0 {
            return vec![Event::Rejected {
                id,
                reason: RejectReason::ZeroPrice,
            }];
        }
        if let Some(reason) = self.check_new_order(id, quantity) {
            return vec![Event::Rejected { id, reason }];
        }

        let mut events = vec![Event::Accepted { id }];
        let trades = self.book.submit(Order::new(id, side, price, quantity));
        events.extend(trades.into_iter().map(Event::Trade));
        events
    }

    fn new_market(&mut self, id: OrderId, side: Side, quantity: Quantity) -> Vec<Event> {
        if let Some(reason) = self.check_new_order(id, quantity) {
            return vec![Event::Rejected { id, reason }];
        }

        let mut events = vec![Event::Accepted { id }];
        let trades = self.book.submit_market(id, side, quantity);
        let filled: u64 = trades.iter().map(|trade| trade.quantity.0).sum();
        events.extend(trades.into_iter().map(Event::Trade));

        // Market orders never rest, so anything unfilled is cancelled
        let remaining = quantity.0 - filled;
        if remaining > 0 {
            events.push(Event::Cancelled {
                id,
                remaining: Quantity(remaining),
                reason: CancelReason::NoLiquidity,
            });
        }
        events
    }

    fn cancel(&mut self, id: OrderId) -> Vec<Event> {
        match self.book.cancel(id) {
            Some(order) => vec![Event::Cancelled {
                id,
                remaining: order.quantity,
                reason: CancelReason::Requested,
            }],
            None => vec![Event::Rejected {
                id,
                reason: RejectReason::UnknownOrderId,
            }],
        }
    }

    /// Checks shared by every new order. Returns why it should be rejected,
    /// or `None` if it is valid.
    fn check_new_order(&self, id: OrderId, quantity: Quantity) -> Option<RejectReason> {
        if quantity.0 == 0 {
            Some(RejectReason::ZeroQuantity)
        } else if self.book.contains(id) {
            Some(RejectReason::DuplicateOrderId)
        } else {
            None
        }
    }
}
