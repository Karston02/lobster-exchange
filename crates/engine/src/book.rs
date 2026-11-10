//! The order book: every resting order, organized by side and price.

use std::collections::{BTreeMap, HashMap, VecDeque};

use crate::types::{Order, OrderId, Price, Quantity, Side, Trade};

/// One side of the book: every price level, mapped to its queue of orders.
///
/// - `BTreeMap` keeps the prices sorted, so the best price is always at one end.
/// - Each `VecDeque` is the line of orders at that price, oldest at the front
///   (time priority: first in line gets filled first).
type Levels = BTreeMap<Price, VecDeque<Order>>;

/// A limit order book with a bid (buy) side and an ask (sell) side.
#[derive(Debug, Default)]
pub struct OrderBook {
    bids: Levels,
    asks: Levels,
    /// Where each resting order lives (its side and price), so cancel can jump
    /// straight to the right price level instead of searching the whole book.
    index: HashMap<OrderId, (Side, Price)>,
}

impl OrderBook {
    /// Creates an empty book.
    pub fn new() -> Self {
        Self::default()
    }

    /// Puts an order on the book to rest (wait) in line at its price.
    ///
    /// This does not check for matches; use [`OrderBook::submit`] for that.
    fn rest(&mut self, order: Order) {
        self.index.insert(order.id, (order.side, order.price));
        let levels = match order.side {
            Side::Buy => &mut self.bids,
            Side::Sell => &mut self.asks,
        };
        // Find the queue for this price (creating it if needed) and join the back of the line.
        levels.entry(order.price).or_default().push_back(order);
    }

    /// Submits a new limit order and returns the trades it produced.
    ///
    /// The order trades against the opposite side for as long as it crosses:
    /// best price first, and oldest order first at each price. Whatever is
    /// left over rests on the book at the order's own price.
    pub(crate) fn submit(&mut self, mut order: Order) -> Vec<Trade> {
        let trades =
            self.take_liquidity(order.id, order.side, &mut order.quantity, Some(order.price));

        // Whatever didn't fill waits on the book at its own price
        if order.quantity.0 > 0 {
            self.rest(order);
        }

        trades
    }

    /// Submits a market order: trade `quantity` right now at whatever prices
    /// the book offers, and returns the trades it produced.
    ///
    /// A market order has no price limit, so it keeps walking through price
    /// levels until it is filled or the other side runs out. It never rests:
    /// if the book is too thin, the unfilled remainder is dropped.
    pub(crate) fn submit_market(
        &mut self,
        id: OrderId,
        side: Side,
        mut quantity: Quantity,
    ) -> Vec<Trade> {
        self.take_liquidity(id, side, &mut quantity, None)
    }

    /// The matching loop shared by limit and market orders.
    ///
    /// Trades an incoming order against the opposite side, best price first
    /// and oldest order first at each price, shrinking `remaining` as it fills.
    /// `limit` is the worst price the taker will accept, or `None` for a
    /// market order that accepts any price.
    fn take_liquidity(
        &mut self,
        taker_id: OrderId,
        side: Side,
        remaining: &mut Quantity,
        limit: Option<Price>,
    ) -> Vec<Trade> {
        let mut trades = Vec::new();

        // A buy trades against asks, a sell trades against bids
        let opposite = match side {
            Side::Buy => &mut self.asks,
            Side::Sell => &mut self.bids,
        };

        // Keep going until the order is fully filled or hits its limit
        while remaining.0 > 0 {
            // Best opposite price: lowest ask for a buy, highest bid for a sell
            let best_level = match side {
                Side::Buy => opposite.first_entry(),
                Side::Sell => opposite.last_entry(),
            };

            // Other side is empty, nothing left to trade against
            let Some(mut level) = best_level else {
                break;
            };

            // Stop if the best price is past our limit (market orders have none)
            let level_price = *level.key();
            let within_limit = match (side, limit) {
                (_, None) => true,
                (Side::Buy, Some(limit)) => level_price <= limit,
                (Side::Sell, Some(limit)) => level_price >= limit,
            };
            if !within_limit {
                break;
            }

            // Fill against the orders at this price, front of the line first
            let queue = level.get_mut();
            while remaining.0 > 0 {
                let Some(resting) = queue.front_mut() else {
                    break;
                };

                // Trade the smaller of the two remaining quantities
                let fill = remaining.0.min(resting.quantity.0);
                trades.push(Trade {
                    maker_order_id: resting.id,
                    taker_order_id: taker_id,
                    price: level_price, // Always the maker's price
                    quantity: Quantity(fill),
                });
                remaining.0 -= fill;
                resting.quantity.0 -= fill;

                // Resting order fully filled, so it leaves the line
                if resting.quantity.0 == 0 {
                    let filled_id = resting.id;
                    queue.pop_front();
                    self.index.remove(&filled_id);
                }
            }

            // Price level is now empty, so remove it from the book
            if queue.is_empty() {
                level.remove();
            }
        }

        trades
    }

    /// Removes a resting order from the book and returns it.
    ///
    /// Returns `None` if no order with that id is resting: it was already
    /// filled, already cancelled, or never existed.
    pub(crate) fn cancel(&mut self, id: OrderId) -> Option<Order> {
        // Look up where the order lives instead of searching every price level.
        let (side, price) = self.index.remove(&id)?;
        let levels = match side {
            Side::Buy => &mut self.bids,
            Side::Sell => &mut self.asks,
        };
        let queue = levels.get_mut(&price)?;

        // Find the order's place in line. This only scans one price level.
        let position = queue.iter().position(|order| order.id == id)?;
        let order = queue.remove(position)?;

        // That was the last order at this price, so the level goes away.
        if queue.is_empty() {
            levels.remove(&price);
        }
        Some(order)
    }

    /// Returns whether an order with this id is resting on the book.
    pub fn contains(&self, id: OrderId) -> bool {
        self.index.contains_key(&id)
    }

    /// Returns how many orders are resting on the book, across both sides.
    pub fn order_count(&self) -> usize {
        self.index.len()
    }

    /// Returns the highest price anyone is willing to buy at, or `None` if there are no bids.
    pub fn best_bid(&self) -> Option<Price> {
        // Higher is better for bids, so the best is the last (largest) key.
        self.bids.last_key_value().map(|(price, _)| *price)
    }

    /// Returns the lowest price anyone is willing to sell at, or `None` if there are no asks.
    pub fn best_ask(&self) -> Option<Price> {
        // Lower is better for asks, so the best is the first (smallest) key.
        self.asks.first_key_value().map(|(price, _)| *price)
    }

    /// Returns the gap between best ask and best bid, in ticks. `None` if either side is empty.
    pub fn spread(&self) -> Option<u64> {
        let bid = self.best_bid()?;
        let ask = self.best_ask()?;
        Some(ask.0 - bid.0)
    }

    /// Returns the total quantity waiting at one price on one side (0 if nothing is there).
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

    /// Returns the orders waiting at one price, front of the line first.
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
        assert_eq!(ids, vec![1, 2, 3]); // First come, first served
        assert_eq!(book.quantity_at(Side::Buy, Price(100)), Quantity(10));
    }

    /// Flattens trades into `(maker id, taker id, price, quantity)` tuples for easy comparison.
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
        assert_eq!(book.best_ask(), None); // Seller is gone
        assert_eq!(book.best_bid(), None); // Buyer didn't rest
    }

    #[test]
    fn trade_happens_at_the_makers_price() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 5));
        // Willing to pay 105, but the seller only asked 100
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

        // Order 1 arrived first, so it fills completely before order 2 gets anything
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

        // Takes all of 100 and 101, but 102 is above our limit
        assert_eq!(summary(&trades), vec![(1, 4, 100, 5), (2, 4, 101, 5)]);
        assert_eq!(book.best_bid(), Some(Price(101))); // Leftover 2 rests
        assert_eq!(book.quantity_at(Side::Buy, Price(101)), Quantity(2));
        assert_eq!(book.best_ask(), Some(Price(102)));
    }

    #[test]
    fn cancel_removes_the_order_and_returns_it() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Buy, 100, 5));

        let cancelled = book.cancel(OrderId(1));
        assert_eq!(cancelled, Some(order(1, Side::Buy, 100, 5)));
        assert_eq!(book.best_bid(), None); // level emptied, so it's gone
        assert_eq!(book.order_count(), 0);
    }

    #[test]
    fn cancel_unknown_or_already_cancelled_order_returns_none() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Buy, 100, 5));

        assert_eq!(book.cancel(OrderId(99)), None); // never existed
        assert!(book.cancel(OrderId(1)).is_some());
        assert_eq!(book.cancel(OrderId(1)), None); // already cancelled
    }

    #[test]
    fn cancel_from_middle_of_line_keeps_everyone_else_in_order() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 5));
        book.submit(order(2, Side::Sell, 100, 5));
        book.submit(order(3, Side::Sell, 100, 5));

        book.cancel(OrderId(2));

        let ids: Vec<u64> = book
            .orders_at(Side::Sell, Price(100))
            .iter()
            .map(|o| o.id.0)
            .collect();
        assert_eq!(ids, vec![1, 3]);
    }

    #[test]
    fn fully_filled_order_can_no_longer_be_cancelled() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 5));
        book.submit(order(2, Side::Buy, 100, 5)); // fills order 1 completely

        assert_eq!(book.cancel(OrderId(1)), None);
        assert_eq!(book.order_count(), 0);
    }

    #[test]
    fn partially_filled_order_cancels_with_what_is_left() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 10));
        book.submit(order(2, Side::Buy, 100, 4)); // order 1 has 6 left

        let cancelled = book.cancel(OrderId(1)).unwrap();
        assert_eq!(cancelled.quantity, Quantity(6));
    }

    #[test]
    fn leftover_taker_can_be_cancelled() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 4));
        book.submit(order(2, Side::Buy, 100, 10)); // 6 left over, rests as a bid

        let cancelled = book.cancel(OrderId(2)).unwrap();
        assert_eq!(cancelled.quantity, Quantity(6));
        assert_eq!(book.best_bid(), None);
    }

    #[test]
    fn market_buy_walks_the_book_with_no_price_limit() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 5));
        book.submit(order(2, Side::Sell, 105, 5));
        book.submit(order(3, Side::Sell, 200, 5));
        let trades = book.submit_market(OrderId(4), Side::Buy, Quantity(12));

        // Takes every level in order, no matter how expensive
        assert_eq!(
            summary(&trades),
            vec![(1, 4, 100, 5), (2, 4, 105, 5), (3, 4, 200, 2)]
        );
        assert_eq!(book.quantity_at(Side::Sell, Price(200)), Quantity(3));
    }

    #[test]
    fn market_sell_hits_the_highest_bids_first() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Buy, 98, 5));
        book.submit(order(2, Side::Buy, 100, 5));
        let trades = book.submit_market(OrderId(3), Side::Sell, Quantity(7));

        assert_eq!(summary(&trades), vec![(2, 3, 100, 5), (1, 3, 98, 2)]);
    }

    #[test]
    fn market_order_never_rests_on_the_book() {
        let mut book = OrderBook::new();
        book.submit(order(1, Side::Sell, 100, 3));
        let trades = book.submit_market(OrderId(2), Side::Buy, Quantity(10));

        // Only 3 was available; the other 7 is dropped, not left as a bid
        assert_eq!(summary(&trades), vec![(1, 2, 100, 3)]);
        assert_eq!(book.best_bid(), None);
        assert_eq!(book.order_count(), 0);
    }

    #[test]
    fn market_order_on_an_empty_book_does_nothing() {
        let mut book = OrderBook::new();
        let trades = book.submit_market(OrderId(1), Side::Buy, Quantity(5));

        assert!(trades.is_empty());
        assert_eq!(book.order_count(), 0);
    }
}
