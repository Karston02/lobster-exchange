//! # lobster-replay
//!
//! Reads recordings made by `lobster-recorder`, parses Coinbase's level2
//! messages into exact integer prices and sizes, and rebuilds the order book.

pub mod coinbase;
pub mod decimal;
pub mod l2book;
