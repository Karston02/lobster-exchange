//! # lobster-engine
//!
//! The core matching engine: an in-memory limit order book that accepts
//! orders, matches them by price-time priority, and reports trades.
//!
//! Start with [`Engine`]: send it [`Command`]s and it returns [`Event`]s.

pub mod book;
pub mod engine;
pub mod messages;
pub mod types;

pub use book::OrderBook;
pub use engine::Engine;
pub use messages::{CancelReason, Command, Event, RejectReason};
pub use types::{Order, OrderId, Price, Quantity, Side, Trade};
