//! The order book: every resting order, organized by side and price.

use std::collections::{BTreeMap, VecDeque};

use crate::types::{Order, Price, Quantity, Side, Trade};

/// represents all of the price leves (tree so they're kept sorted).
type Levels = BTreeMap<Price, VecDeque<Order>>;

/// A limit order book with a bid (buy) side and an ask (sell) side.
#[derive(Debug, Default)]
pub struct OrderBook {
    bids: Levels,
    asks: Levels,
}

impl OrderBook {
    /// An empty book.
    pub fn new() -> Self {
        Self::default()
    }

    /**
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

    /**
     * Submit a new limit order. It trades against the opposite side for as long
     * as it crosses: best price first, and oldest order first at each price.
     * Whatever is left over rests on the book. Returns the trades that happened.
     */
    pub fn submit(&mut self, mut order: Order) -> Vec<Trade> {
        let mut trades = Vec::new();

        // a buy trades against asks, a sell trades against bids
        let opposite = match order.side {
            Side::Buy => &mut self.asks,
            Side::Sell => &mut self.bids,
        };

        // keep going until the order is fully filled or stops crossing
        while order.quantity.0 > 0 {
            // best opposite price: lowest ask for a buy, highest bid for a sell
            let best_level = match order.side {
                Side::Buy => opposite.first_entry(),
                Side::Sell => opposite.last_entry(),
            };

            // other side is empty, nothing left to trade against
            let Some(mut level) = best_level else {
                break;
            };

            // best price is too expensive (or too cheap), so stop matching
            let level_price = *level.key();
            if !order.crosses(level_price) {
                break;
            }

            // fill against the orders at this price, front of the line first
            let queue = level.get_mut();
            while order.quantity.0 > 0 {
                let Some(resting) = queue.front_mut() else {
                    break;
                };

                // trade the smaller of the two remaining quantities
                let fill = order.quantity.0.min(resting.quantity.0);
                trades.push(Trade {
                    maker_order_id: resting.id,
                    taker_order_id: order.id,
                    price: level_price, // always the maker's price
                    quantity: Quantity(fill),
                });
                order.quantity.0 -= fill;
                resting.quantity.0 -= fill;

                // resting order fully filled, so it leaves the line
                if resting.quantity.0 == 0 {
                    queue.pop_front();
                }
            }

            // price level is now empty, so remove it from the book
            if queue.is_empty() {
                level.remove();
            }
        }

        // whatever didn't fill waits on the book at its own price
        if order.quantity.0 > 0 {
            self.rest(order);
        }

        trades
    }

    /// The highest price anyone is willing to buy at, or `None` if there are no bids.
    pub fn best_bid(&self) -> Option<Price> {
        // Bids: higher is better, so the best is the LAST (largest) key.
        self.bids.last_key_value().map(|(price, _)| *price)
    }

    /// The lowest price anyone is willing to sell at, or `None` if there are no asks.
    pub fn best_ask(&self) -> Option<Price> {
        // Asks: lower is better, so the best is the FIRST (smallest) key.
        self.asks.first_key_value().map(|(price, _)| *price)
    }

    /// The gap between best ask and best bid, in ticks. `None` if either side is empty.
    pub fn spread(&self) -> Option<u64> {
        let bid = self.best_bid()?;
        let ask = self.best_ask()?;
        Some(ask.0 - bid.0)
    }

    /// Total quantity waiting at one price on one side (0 if nothing is there).
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

    /// The queue of orders at one price, front of the line first.
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

    /// shorthand for checking a trade: (maker id, taker id, price, quantity)
    fn summary(trades: &[Trade]) -> Vec<(u64, u64, u64, u64)> {
        trades
            .iter()
            .map(|t| {
                (
                    t.maker_order_id.0,
                    t.taker_order_id.0,
                    t.price.0,
                    t.quantity.0,
                )
            })
            .collect()
    }

    #[test]
    fn order_that_does_not_cross_rests() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 101, 5));
        let trades = book.submit(order(2, Side::Buy, 100, 5));

        assert!(trades.is_empty());
        assert_eq!(book.best_bid(), Some(Price(100)));
        assert_eq!(book.best_ask(), Some(Price(101)));
    }

    #[test]
    fn exact_match_fills_both_and_clears_the_level() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 5));
        let trades = book.submit(order(2, Side::Buy, 100, 5));

        assert_eq!(summary(&trades), vec![(1, 2, 100, 5)]);
        assert_eq!(book.best_ask(), None); // seller is gone
        assert_eq!(book.best_bid(), None); // buyer didn't rest
    }

    #[test]
    fn trade_happens_at_the_makers_price() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 5));
        // willing to pay 105, but the seller only asked 100
        let trades = book.submit(order(2, Side::Buy, 105, 5));

        assert_eq!(summary(&trades), vec![(1, 2, 100, 5)]);
    }

    #[test]
    fn taker_partially_fills_and_the_rest_rests() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 4));
        let trades = book.submit(order(2, Side::Buy, 100, 10));

        assert_eq!(summary(&trades), vec![(1, 2, 100, 4)]);
        assert_eq!(book.quantity_at(Side::Buy, Price(100)), Quantity(6));
    }

    #[test]
    fn maker_partially_fills_and_keeps_its_place() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 10));
        let trades = book.submit(order(2, Side::Buy, 100, 3));

        assert_eq!(summary(&trades), vec![(1, 2, 100, 3)]);
        assert_eq!(book.quantity_at(Side::Sell, Price(100)), Quantity(7));
    }

    #[test]
    fn time_priority_oldest_order_fills_first() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 5));
        book.submit(order(2, Side::Sell, 100, 5));
        let trades = book.submit(order(3, Side::Buy, 100, 7));

        // order 1 arrived first, so it fills completely before order 2 gets anything
        assert_eq!(summary(&trades), vec![(1, 3, 100, 5), (2, 3, 100, 2)]);
        assert_eq!(book.quantity_at(Side::Sell, Price(100)), Quantity(3));
    }

    #[test]
    fn buy_walks_up_through_several_price_levels() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 5));
        book.submit(order(2, Side::Sell, 101, 5));
        book.submit(order(3, Side::Sell, 102, 5));
        let trades = book.submit(order(4, Side::Buy, 101, 12));

        // takes all of 100 and 101, but 102 is above our limit
        assert_eq!(summary(&trades), vec![(1, 4, 100, 5), (2, 4, 101, 5)]);
        assert_eq!(book.best_bid(), Some(Price(101))); // leftover 2 rests
        assert_eq!(book.quantity_at(Side::Buy, Price(101)), Quantity(2));
        assert_eq!(book.best_ask(), Some(Price(102)));
    }
}
