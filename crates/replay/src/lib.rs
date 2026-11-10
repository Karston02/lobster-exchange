//! # lobster-replay
//!
//! Reads recordings made by `lobster-recorder`, parses Coinbase's level2
//! messages into exact integer prices and sizes, rebuilds the order book in
//! the matching engine, and runs backtests against it.

pub mod backtest;
pub mod coinbase;
pub mod decimal;
pub mod l2book;
pub mod recording;
pub mod time;
pub mod timeline;
pub mod translate;
