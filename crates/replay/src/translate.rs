//! Turning level2 changes into engine commands.
//!
//! Coinbase tells us the total size at each price. The engine works with
//! individual orders. So the translator keeps a line of synthetic orders at
//! each price in the engine, sized so their total always equals Coinbase's:
//!
//! - A level grows: a new synthetic order for the difference joins the back.
//! - A level shrinks: synthetic orders are removed from the back of the line
//!   (or the last one is reduced, which keeps its place).
//! - A trade happens: an immediate-or-cancel order at the trade's price takes
//!   it from the front of the line, the way a real fill does.
//!
//! Other orders can share the engine: a backtested bot's orders, with ids at or
//! above [`FIRST_BOT_ID`]. The translator never cancels those, and doesn't count
//! them toward Coinbase's totals, since they aren't on Coinbase. Events that
//! involve them are kept for the caller ([`L2Translator::take_outside_events`]).
//!
//! Removing from the back is a pessimistic assumption about cancels: orders
//! ahead of a waiting bot never vanish, so it only moves forward through
//! trades. See ARCHITECTURE.md, decision #10.

use std::collections::HashMap;

use lobster_engine::{Command, Engine, Event, OrderId, Price, Quantity, Side};

use crate::l2book::LevelUpdate;
use crate::timeline::TradePrint;

/// Ids from here up belong to orders that aren't synthetic (a bot's).
pub const FIRST_BOT_ID: u64 = 1 << 62;

/// Returns whether an id belongs to a synthetic (Coinbase-replica) order.
pub fn is_synthetic(id: OrderId) -> bool {
    id.0 < FIRST_BOT_ID
}

/// Keeps an engine's book in step with a level2 feed.
#[derive(Debug)]
pub struct L2Translator {
    engine: Engine,
    next_id: u64,
    commands_sent: u64,
    unexpected_events: u64,
    /// Events involving non-synthetic orders, waiting to be collected
    outside_events: Vec<Event>,
}

impl Default for L2Translator {
    fn default() -> Self {
        Self::new()
    }
}

impl L2Translator {
    /// Creates a translator with an empty engine.
    pub fn new() -> Self {
        Self {
            engine: Engine::new(),
            next_id: 1,
            commands_sent: 0,
            unexpected_events: 0,
            outside_events: Vec::new(),
        }
    }

    /// Read-only access to the engine, for checking its book.
    pub fn engine(&self) -> &Engine {
        &self.engine
    }

    /// Returns how many commands have been sent to the engine.
    pub fn commands_sent(&self) -> u64 {
        self.commands_sent
    }

    /// Returns how many engine events made no sense for synthetic orders
    /// (a synthetic order trading with another synthetic one, or a rejection).
    /// Should be zero.
    pub fn unexpected_events(&self) -> u64 {
        self.unexpected_events
    }

    /// Removes and returns the events involving non-synthetic orders that the
    /// market's own activity caused, e.g. a bot's resting order being filled.
    pub fn take_outside_events(&mut self) -> Vec<Event> {
        std::mem::take(&mut self.outside_events)
    }

    /// Sends a non-synthetic order's command (a bot's) and returns its events.
    pub fn submit(&mut self, command: Command) -> Vec<Event> {
        self.commands_sent += 1;
        self.engine.process(command)
    }

    /// Starts over with an empty book, before applying a snapshot.
    pub fn reset(&mut self) {
        self.engine = Engine::new();
    }

    /// Applies every level change from one message.
    pub fn apply(&mut self, updates: &[LevelUpdate]) {
        // Updates are totals, so a later update to the same level replaces an earlier one
        let mut latest: Vec<LevelUpdate> = Vec::with_capacity(updates.len());
        let mut position: HashMap<(Side, Price), usize> = HashMap::with_capacity(updates.len());
        for update in updates {
            match position.get(&(update.side, update.price)) {
                Some(&i) => latest[i] = *update,
                None => {
                    position.insert((update.side, update.price), latest.len());
                    latest.push(*update);
                }
            }
        }

        /*
         * Shrink levels before growing any. If a bid is added at a price where
         * an ask is being removed in the same message, adding the bid first
         * would make the engine match them, which never happened on Coinbase.
         */
        let (shrinking, growing): (Vec<_>, Vec<_>) = latest
            .into_iter()
            .partition(|update| update.quantity < self.current(update.side, update.price));
        for update in shrinking.into_iter().chain(growing) {
            self.set_level(update);
        }
    }

    /// Replays one exchange trade against the front of the line.
    ///
    /// Sends an immediate-or-cancel order on the taker's side at the trade's
    /// price. Returns how much of the trade the engine could not fill: zero
    /// when our book already had the resting quantity the trade consumed.
    pub fn apply_trade(&mut self, trade: TradePrint) -> Quantity {
        let id = self.new_id();
        let events = self.process_synthetic(Command::NewImmediateOrCancel {
            id,
            side: trade.maker_side.opposite(),
            price: trade.price,
            quantity: trade.quantity,
        });
        events
            .iter()
            .find_map(|event| match event {
                Event::Cancelled { remaining, .. } => Some(*remaining),
                _ => None,
            })
            .unwrap_or(Quantity(0))
    }

    /// The synthetic total at one price: Coinbase's quantity as far as we know.
    fn current(&self, side: Side, price: Price) -> Quantity {
        let total = self
            .engine
            .book()
            .orders_at(side, price)
            .iter()
            .filter(|order| is_synthetic(order.id))
            .map(|order| order.quantity.0)
            .sum();
        Quantity(total)
    }

    /// Makes the synthetic total at one price equal `update.quantity`.
    fn set_level(&mut self, update: LevelUpdate) {
        let current = self.current(update.side, update.price).0;
        let target = update.quantity.0;
        if target > current {
            let id = self.new_id();
            self.process_synthetic(Command::NewLimit {
                id,
                side: update.side,
                price: update.price,
                quantity: Quantity(target - current),
            });
        } else if target < current {
            self.shrink(update.side, update.price, current - target);
        }
    }

    /// Removes `amount` of synthetic quantity from one price level, taking it
    /// from the back of the line and skipping orders that aren't synthetic.
    fn shrink(&mut self, side: Side, price: Price, mut amount: u64) {
        // Copy the line out first: we can't hold a borrow of the book while changing it
        let line: Vec<(OrderId, u64)> = self
            .engine
            .book()
            .orders_at(side, price)
            .iter()
            .rev()
            .filter(|order| is_synthetic(order.id))
            .map(|order| (order.id, order.quantity.0))
            .collect();

        for (id, quantity) in line {
            if amount == 0 {
                break;
            }
            if quantity > amount {
                // Only part of this order goes; reducing it keeps its place in line
                self.process_synthetic(Command::Reduce {
                    id,
                    by: Quantity(amount),
                });
                amount = 0;
            } else {
                self.process_synthetic(Command::Cancel { id });
                amount -= quantity;
            }
        }
    }

    /// Sends a synthetic order's command, checks the events, and keeps any
    /// that involve outside orders for the caller.
    fn process_synthetic(&mut self, command: Command) -> Vec<Event> {
        self.commands_sent += 1;
        let events = self.engine.process(command);
        for event in &events {
            match event {
                Event::Accepted { .. } | Event::Cancelled { .. } | Event::Reduced { .. } => {}
                Event::Trade(trade) => {
                    let maker_synthetic = is_synthetic(trade.maker_order_id);
                    let taker_synthetic = is_synthetic(trade.taker_order_id);
                    if !maker_synthetic || !taker_synthetic {
                        self.outside_events.push(*event);
                    } else if !matches!(command, Command::NewImmediateOrCancel { .. }) {
                        // Only replayed trades should match synthetic orders with each other
                        self.unexpected_events += 1;
                    }
                }
                Event::Rejected { .. } => self.unexpected_events += 1,
            }
        }
        events
    }

    fn new_id(&mut self) -> OrderId {
        let id = OrderId(self.next_id);
        self.next_id += 1;
        id
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn level(side: Side, price: u64, quantity: u64) -> LevelUpdate {
        LevelUpdate {
            side,
            price: Price(price),
            quantity: Quantity(quantity),
        }
    }

    fn trade(maker_side: Side, price: u64, quantity: u64) -> TradePrint {
        TradePrint {
            maker_side,
            price: Price(price),
            quantity: Quantity(quantity),
        }
    }

    /// The sizes of the orders waiting at one price, front of the line first.
    fn line(translator: &L2Translator, side: Side, price: u64) -> Vec<u64> {
        translator
            .engine()
            .book()
            .orders_at(side, Price(price))
            .iter()
            .map(|order| order.quantity.0)
            .collect()
    }

    fn bot_limit(id: u64, side: Side, price: u64, quantity: u64) -> Command {
        Command::NewLimit {
            id: OrderId(FIRST_BOT_ID + id),
            side,
            price: Price(price),
            quantity: Quantity(quantity),
        }
    }

    #[test]
    fn snapshot_creates_one_order_per_level() {
        let mut translator = L2Translator::new();
        translator.apply(&[
            level(Side::Buy, 99, 5),
            level(Side::Buy, 100, 3),
            level(Side::Sell, 101, 4),
        ]);
        let book = translator.engine().book();
        assert_eq!(book.best_bid(), Some(Price(100)));
        assert_eq!(book.best_ask(), Some(Price(101)));
        assert_eq!(book.order_count(), 3);
        assert_eq!(translator.unexpected_events(), 0);
    }

    #[test]
    fn growth_joins_the_back_of_the_line() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 100, 5)]);
        translator.apply(&[level(Side::Buy, 100, 8)]);
        assert_eq!(line(&translator, Side::Buy, 100), vec![5, 3]);
    }

    #[test]
    fn shrinking_takes_from_the_back_of_the_line() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Sell, 101, 5)]);
        translator.apply(&[level(Side::Sell, 101, 8)]); // Line: [5, 3]
        translator.apply(&[level(Side::Sell, 101, 4)]); // Remove 4: all of the 3, then 1 of the 5

        assert_eq!(line(&translator, Side::Sell, 101), vec![4]);
        assert_eq!(translator.unexpected_events(), 0);
    }

    #[test]
    fn shrinking_leaves_the_front_of_the_line_alone() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 100, 5)]);
        translator.apply(&[level(Side::Buy, 100, 8)]); // Line: [5, 3]
        translator.apply(&[level(Side::Buy, 100, 6)]); // Remove 2 from the 3

        assert_eq!(line(&translator, Side::Buy, 100), vec![5, 1]);
    }

    #[test]
    fn zero_removes_the_level() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 100, 5)]);
        translator.apply(&[level(Side::Buy, 100, 0)]);
        assert_eq!(translator.engine().book().best_bid(), None);
        assert_eq!(translator.engine().book().order_count(), 0);
    }

    #[test]
    fn price_flipping_sides_in_one_message_never_trades() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 99, 5), level(Side::Sell, 100, 5)]);
        // The ask at 100 goes away and a bid appears at 100, listed bid-first
        translator.apply(&[level(Side::Buy, 100, 2), level(Side::Sell, 100, 0)]);

        assert_eq!(translator.unexpected_events(), 0);
        assert_eq!(translator.engine().book().best_bid(), Some(Price(100)));
        assert_eq!(translator.engine().book().best_ask(), None);
    }

    #[test]
    fn later_update_to_the_same_level_wins() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 100, 5), level(Side::Buy, 100, 2)]);
        assert_eq!(line(&translator, Side::Buy, 100), vec![2]);
    }

    #[test]
    fn trade_takes_from_the_front_of_the_line() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 100, 5)]);
        translator.apply(&[level(Side::Buy, 100, 8)]); // Line: [5, 3]

        let unfilled = translator.apply_trade(trade(Side::Buy, 100, 6));
        assert_eq!(unfilled, Quantity(0));
        assert_eq!(line(&translator, Side::Buy, 100), vec![2]);

        // Coinbase's next update agrees (8 - 6 = 2), so nothing more changes
        let commands = translator.commands_sent();
        translator.apply(&[level(Side::Buy, 100, 2)]);
        assert_eq!(translator.commands_sent(), commands);
        assert_eq!(translator.unexpected_events(), 0);
    }

    #[test]
    fn trade_the_book_cannot_cover_reports_what_is_missing() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Sell, 101, 2)]);
        let unfilled = translator.apply_trade(trade(Side::Sell, 101, 5));
        assert_eq!(unfilled, Quantity(3));
        assert_eq!(translator.engine().book().best_ask(), None);
    }

    #[test]
    fn trade_never_rests_on_the_book() {
        let mut translator = L2Translator::new();
        translator.apply_trade(trade(Side::Buy, 100, 5)); // Nothing to trade against
        assert_eq!(translator.engine().book().order_count(), 0);
    }

    #[test]
    fn reset_empties_the_book() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 100, 5)]);
        translator.reset();
        assert_eq!(translator.engine().book().order_count(), 0);
    }

    #[test]
    fn bot_orders_are_never_cancelled_and_not_counted_as_coinbase_quantity() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 100, 5)]);
        translator.submit(bot_limit(1, Side::Buy, 100, 2)); // Line: [5, bot 2]

        // Coinbase's level drops to 1: only synthetic quantity is removed
        translator.apply(&[level(Side::Buy, 100, 1)]);
        assert_eq!(line(&translator, Side::Buy, 100), vec![1, 2]);

        // Coinbase's level grows to 4: the bot's 2 doesn't count toward it
        translator.apply(&[level(Side::Buy, 100, 4)]);
        assert_eq!(line(&translator, Side::Buy, 100), vec![1, 2, 3]);

        // Even if Coinbase removes the whole level, the bot's order stays
        translator.apply(&[level(Side::Buy, 100, 0)]);
        assert_eq!(line(&translator, Side::Buy, 100), vec![2]);
        assert_eq!(translator.unexpected_events(), 0);
    }

    #[test]
    fn trades_reach_a_bot_order_only_after_the_orders_ahead_of_it() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Sell, 101, 5)]);
        translator.submit(bot_limit(1, Side::Sell, 101, 2)); // Line: [5, bot 2]

        translator.apply_trade(trade(Side::Sell, 101, 4));
        assert!(translator.take_outside_events().is_empty()); // Still 1 ahead of the bot

        translator.apply_trade(trade(Side::Sell, 101, 2));
        let events = translator.take_outside_events();
        let [Event::Trade(fill)] = events.as_slice() else {
            panic!("expected one bot fill, got {events:?}");
        };
        assert_eq!(fill.maker_order_id, OrderId(FIRST_BOT_ID + 1));
        assert_eq!(fill.quantity, Quantity(1));
    }

    #[test]
    fn new_coinbase_liquidity_that_crosses_a_bot_order_fills_it() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 99, 5), level(Side::Sell, 102, 5)]);
        // The bot bids 101, inside the spread; then a Coinbase ask appears at 100
        translator.submit(bot_limit(1, Side::Buy, 101, 3));
        translator.apply(&[level(Side::Sell, 100, 2)]);

        let events = translator.take_outside_events();
        assert!(matches!(events.as_slice(), [Event::Trade(t)] if t.quantity == Quantity(2)));
        assert_eq!(translator.unexpected_events(), 0);
    }
}
