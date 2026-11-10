// The order book: every resting order, organized by side and price.

use std::collections::{BTreeMap, VecDeque};

use crate::types::{Order, Price, Quantity, Side};


// represents all of the price leves (tree so they're kept sorted).
type Levels = BTreeMap<Price, VecDeque<Order>>;

// A limit order book with a bid (buy) side and an ask (sell) side.
#[derive(Debug, Default)]
pub struct OrderBook {
    bids: Levels,
    asks: Levels,
}

impl OrderBook {
    // An empty book.
    pub fn new() -> Self {
        Self::default()
    }

    /*
     * Put an order on the book to "rest" (or wait) in line at its price.
     * This doesn't check for matches, that's the matching step.
     */
    pub fn rest(&mut self, order: Order) {
        let levels = match order.side {
            Side::Buy => &mut self.bids,
            Side::Sell => &mut self.asks,
        };
        // find queue for this price, creating empty one if it doesn't exist yet.
        levels.entry(order.price).or_default().push_back(order);
    }

    // The highest price anyone is willing to buy at, or `None` if there are no bids.
    pub fn best_bid(&self) -> Option<Price> {
        // Bids: higher is better, so the best is the LAST (largest) key.
        self.bids.last_key_value().map(|(price, _)| *price)
    }

    // The lowest price anyone is willing to sell at, or `None` if there are no asks.
    pub fn best_ask(&self) -> Option<Price> {
        // Asks: lower is better, so the best is the FIRST (smallest) key.
        self.asks.first_key_value().map(|(price, _)| *price)
    }

    // The gap between best ask and best bid, in ticks. `None` if either side is empty.
    pub fn spread(&self) -> Option<u64> {
        let bid = self.best_bid()?;
        let ask = self.best_ask()?;
        Some(ask.0 - bid.0)
    }

    // Total quantity waiting at one price on one side (0 if nothing is there).
    pub fn quantity_at(&self, side: Side, price: Price) -> Quantity {
        let levels = match side {
            Side::Buy => &self.bids,
            Side::Sell => &self.asks,
        };
        let total = levels
            .get(&price)
            .map(|queue| queue.iter().map(|order| order.quantity.0).sum())
            .unwrap_or(0);
        Quantity(total)
    }

    // The queue of orders at one price, front of the line first.
    pub fn orders_at(&self, side: Side, price: Price) -> Vec<&Order> {
        let levels = match side {
            Side::Buy => &self.bids,
            Side::Sell => &self.asks,
        };
        levels
            .get(&price)
            .map(|queue| queue.iter().collect())
            .unwrap_or_default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::OrderId;

    fn order(id: u64, side: Side, price: u64, qty: u64) -> Order {
        Order::new(OrderId(id), side, Price(price), Quantity(qty))
    }

    #[test]
    fn empty_book_has_no_prices() {
        let book = OrderBook::new();
        assert_eq!(book.best_bid(), None);
        assert_eq!(book.best_ask(), None);
        assert_eq!(book.spread(), None);
    }

    #[test]
    fn best_bid_is_highest_buy() {
        let mut book = OrderBook::new();
        book.rest(order(1, Side::Buy, 99, 5));
        book.rest(order(2, Side::Buy, 101, 5));
        book.rest(order(3, Side::Buy, 100, 5));
        assert_eq!(book.best_bid(), Some(Price(101)));
    }

    #[test]
    fn best_ask_is_lowest_sell() {
        let mut book = OrderBook::new();
        book.rest(order(1, Side::Sell, 105, 5));
        book.rest(order(2, Side::Sell, 103, 5));
        book.rest(order(3, Side::Sell, 104, 5));
        assert_eq!(book.best_ask(), Some(Price(103)));
    }

    #[test]
    fn spread_is_ask_minus_bid() {
        let mut book = OrderBook::new();
        book.rest(order(1, Side::Buy, 100, 5));
        book.rest(order(2, Side::Sell, 103, 5));
        assert_eq!(book.spread(), Some(3));
    }

    #[test]
    fn orders_at_same_price_queue_in_arrival_order() {
        let mut book = OrderBook::new();
        book.rest(order(1, Side::Buy, 100, 5));
        book.rest(order(2, Side::Buy, 100, 3));
        book.rest(order(3, Side::Buy, 100, 2));

        let ids: Vec<u64> = book
            .orders_at(Side::Buy, Price(100))
            .iter()
            .map(|o| o.id.0)
            .collect();
        assert_eq!(ids, vec![1, 2, 3]); // first come, first served
        assert_eq!(book.quantity_at(Side::Buy, Price(100)), Quantity(10));
    }
}
