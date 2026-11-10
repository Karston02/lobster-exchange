//! # lobster-engine
//!
//! The core matching engine: an in-memory limit order book that accepts
//! orders, matches them by price-time priority, and reports trades.
//!
//! Nothing here yet — the core types (`Order`, `Side`, `Trade`) come next.

/// Returns the crate version. Exists so the starter test has something to check.
pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crate_builds() {
        assert_eq!(version(), "0.1.0");
    }
}
