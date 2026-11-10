//! # lobster-engine
//!
//! The core matching engine: an in-memory limit order book that accepts
//! orders, matches them by price-time priority, and reports trades.

pub mod types;

pub use types::{Order, OrderId, Price, Quantity, Side, Trade};
