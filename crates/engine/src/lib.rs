//! # lobster-engine
//!
//! The core matching engine: an in-memory limit order book that accepts
//! orders, matches them by price-time priority, and reports trades.
//!
//! Start with [`Engine`]: send it [`Command`]s and it returns [`Event`]s.

mod book;
mod engine;
mod messages;
mod types;

pub use book::OrderBook;
pub use engine::Engine;
pub use messages::{CancelReason, Command, Event, RejectReason};
pub use types::{Order, OrderId, Price, Quantity, Side, Trade};
