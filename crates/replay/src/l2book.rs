//! A copy of an exchange's order book, rebuilt from level2 data.
//!
//! Level2 data only gives the total quantity at each price, not individual
//! orders, so this book is just a sorted map from price to quantity. It is a
//! separate thing from the engine's `OrderBook`, which tracks every order.

use std::collections::BTreeMap;

use lobster_engine::{Price, Quantity, Side};

/// One change to the book: "the total at this price on this side is now `quantity`".
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LevelUpdate {
    pub side: Side,
    pub price: Price,
    /// The new total at this price (not a change). Zero removes the level.
    pub quantity: Quantity,
}

/// A level2 order book: total quantity at each price, per side.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct L2Book {
    bids: BTreeMap<Price, Quantity>,
    asks: BTreeMap<Price, Quantity>,
}

impl L2Book {
    /// Creates an empty book.
    pub fn new() -> Self {
        Self::default()
    }

    /// Removes every level, e.g. before applying a fresh snapshot.
    pub fn clear(&mut self) {
        self.bids.clear();
        self.asks.clear();
    }

    /// Applies one update: sets the level's quantity, or removes it if zero.
    pub fn apply(&mut self, update: LevelUpdate) {
        let levels = match update.side {
            Side::Buy => &mut self.bids,
            Side::Sell => &mut self.asks,
        };
        if update.quantity.0 == 0 {
            levels.remove(&update.price);
        } else {
            levels.insert(update.price, update.quantity);
        }
    }

    /// Returns the highest bid and its quantity.
    pub fn best_bid(&self) -> Option<(Price, Quantity)> {
        self.bids.last_key_value().map(|(p, q)| (*p, *q))
    }

    /// Returns the lowest ask and its quantity.
    pub fn best_ask(&self) -> Option<(Price, Quantity)> {
        self.asks.first_key_value().map(|(p, q)| (*p, *q))
    }

    /// Returns whether the best bid is at or above the best ask, which should
    /// never happen on a real exchange and means our copy is wrong.
    pub fn is_crossed(&self) -> bool {
        match (self.best_bid(), self.best_ask()) {
            (Some((bid, _)), Some((ask, _))) => bid >= ask,
            _ => false,
        }
    }

    /// Returns how many price levels each side has: `(bids, asks)`.
    pub fn depth(&self) -> (usize, usize) {
        (self.bids.len(), self.asks.len())
    }

    /// Returns the best `n` levels of one side, best first.
    pub fn top(&self, side: Side, n: usize) -> Vec<(Price, Quantity)> {
        let levels: Box<dyn Iterator<Item = (&Price, &Quantity)>> = match side {
            Side::Buy => Box::new(self.bids.iter().rev()),
            Side::Sell => Box::new(self.asks.iter()),
        };
        levels.take(n).map(|(p, q)| (*p, *q)).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn update(side: Side, price: u64, quantity: u64) -> LevelUpdate {
        LevelUpdate {
            side,
            price: Price(price),
            quantity: Quantity(quantity),
        }
    }

    #[test]
    fn updates_set_the_total_at_a_price() {
        let mut book = L2Book::new();
        book.apply(update(Side::Buy, 100, 5));
        book.apply(update(Side::Buy, 100, 8)); // Replaces, does not add
        assert_eq!(book.best_bid(), Some((Price(100), Quantity(8))));
    }

    #[test]
    fn zero_quantity_removes_the_level() {
        let mut book = L2Book::new();
        book.apply(update(Side::Sell, 101, 5));
        book.apply(update(Side::Sell, 101, 0));
        assert_eq!(book.best_ask(), None);
        assert_eq!(book.depth(), (0, 0));
    }

    #[test]
    fn best_prices_and_top_levels() {
        let mut book = L2Book::new();
        for (side, price) in [
            (Side::Buy, 98),
            (Side::Buy, 100),
            (Side::Buy, 99),
            (Side::Sell, 103),
            (Side::Sell, 101),
            (Side::Sell, 102),
        ] {
            book.apply(update(side, price, 1));
        }
        assert_eq!(book.best_bid().map(|(p, _)| p), Some(Price(100)));
        assert_eq!(book.best_ask().map(|(p, _)| p), Some(Price(101)));
        let top_bids: Vec<u64> = book.top(Side::Buy, 2).iter().map(|(p, _)| p.0).collect();
        let top_asks: Vec<u64> = book.top(Side::Sell, 2).iter().map(|(p, _)| p.0).collect();
        assert_eq!(top_bids, vec![100, 99]);
        assert_eq!(top_asks, vec![101, 102]);
        assert!(!book.is_crossed());
    }

    #[test]
    fn detects_a_crossed_book() {
        let mut book = L2Book::new();
        book.apply(update(Side::Buy, 101, 1));
        book.apply(update(Side::Sell, 101, 1));
        assert!(book.is_crossed());
    }

    #[test]
    fn clear_empties_both_sides() {
        let mut book = L2Book::new();
        book.apply(update(Side::Buy, 100, 1));
        book.apply(update(Side::Sell, 101, 1));
        book.clear();
        assert_eq!(book.depth(), (0, 0));
    }
}
