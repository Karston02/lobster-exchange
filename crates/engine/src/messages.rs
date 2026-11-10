//! The engine's contract with the outside world: commands go in, events come out.
//!
//! Everything that talks to the engine (tests, the replayer, the trading bot,
//! the dashboard server) only needs the types in this file.

use crate::types::{OrderId, Price, Quantity, Side, Trade};

/// A request sent to the engine.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Command {
    /// Buy or sell up to `quantity` at `price` or better. Any unfilled
    /// remainder rests on the book.
    NewLimit {
        id: OrderId,
        side: Side,
        price: Price,
        quantity: Quantity,
    },
    /// Buy or sell `quantity` right now at whatever prices the book offers.
    /// Any unfilled remainder is cancelled, never rested.
    NewMarket {
        id: OrderId,
        side: Side,
        quantity: Quantity,
    },
    /// Immediate-or-cancel: buy or sell up to `quantity` at `price` or better,
    /// right now. Unlike a limit order, any unfilled remainder is cancelled
    /// instead of resting on the book.
    NewImmediateOrCancel {
        id: OrderId,
        side: Side,
        price: Price,
        quantity: Quantity,
    },
    /// Remove a resting order from the book.
    Cancel { id: OrderId },
}

/// Something that happened as a result of a command.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Event {
    /// A new order passed validation and entered the engine. Always the first
    /// event for a valid new order, before any trades it causes.
    Accepted { id: OrderId },
    /// Two orders matched.
    Trade(Trade),
    /// An order left the book without being fully filled.
    Cancelled {
        id: OrderId,
        /// How much was still unfilled when it was cancelled.
        remaining: Quantity,
        reason: CancelReason,
    },
    /// A command was refused. Nothing about the book changed.
    Rejected { id: OrderId, reason: RejectReason },
}

/// Why an order was cancelled.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CancelReason {
    /// The owner sent a `Cancel` command.
    Requested,
    /// A market or immediate-or-cancel order ran out of opposite orders it
    /// could trade against (at any price, or within its limit).
    NoLiquidity,
}

/// Why a command was rejected.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RejectReason {
    /// The order's quantity was zero.
    ZeroQuantity,
    /// A limit order's price was zero.
    ZeroPrice,
    /// An order with this id is already resting on the book.
    DuplicateOrderId,
    /// A cancel named an order that isn't resting on the book.
    UnknownOrderId,
}
