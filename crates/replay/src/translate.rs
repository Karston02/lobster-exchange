//! Turning level2 changes into engine commands.
//!
//! Coinbase tells us the total size at each price. The engine works with
//! individual orders. So the translator keeps a line of synthetic orders at
//! each price in the engine, sized so their total always equals Coinbase's:
//!
//! - A level grows: a new synthetic order for the difference joins the back.
//! - A level shrinks: synthetic orders are removed from the back of the line.
//!
//! Removing from the back is a pessimistic assumption about cancels. When a
//! market-making bot sits in the line later, orders ahead of it never vanish,
//! so it only moves forward through trades. See ARCHITECTURE.md, decision #10.

use std::collections::HashMap;

use lobster_engine::{Command, Engine, Event, OrderId, Price, Quantity, Side};

use crate::l2book::LevelUpdate;

/// Keeps an engine's book in step with a level2 feed.
#[derive(Debug)]
pub struct L2Translator {
    engine: Engine,
    next_id: u64,
    commands_sent: u64,
    unexpected_events: u64,
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

    /// Returns how many engine events were trades or rejections. Synthetic
    /// orders should only ever rest and be cancelled, so this should be zero.
    pub fn unexpected_events(&self) -> u64 {
        self.unexpected_events
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

    /// The engine's current total at one price.
    fn current(&self, side: Side, price: Price) -> Quantity {
        self.engine.book().quantity_at(side, price)
    }

    /// Makes the engine's total at one price equal `update.quantity`.
    fn set_level(&mut self, update: LevelUpdate) {
        let current = self.current(update.side, update.price).0;
        let target = update.quantity.0;
        if target > current {
            let id = self.new_id();
            self.process(Command::NewLimit {
                id,
                side: update.side,
                price: update.price,
                quantity: Quantity(target - current),
            });
        } else if target < current {
            self.shrink(update.side, update.price, current - target);
        }
    }

    /// Removes `amount` from one price level, taking it from the back of the line.
    fn shrink(&mut self, side: Side, price: Price, mut amount: u64) {
        // Copy the line out first: we can't hold a borrow of the book while changing it
        let line: Vec<(OrderId, u64)> = self
            .engine
            .book()
            .orders_at(side, price)
            .iter()
            .rev()
            .map(|order| (order.id, order.quantity.0))
            .collect();

        for (id, quantity) in line {
            if amount == 0 {
                break;
            }
            self.process(Command::Cancel { id });
            if quantity > amount {
                // Only part of this order goes. It was last in line, so re-adding
                // the rest at the back keeps it in the same place.
                let id = self.new_id();
                self.process(Command::NewLimit {
                    id,
                    side,
                    price,
                    quantity: Quantity(quantity - amount),
                });
                amount = 0;
            } else {
                amount -= quantity;
            }
        }
    }

    /// Sends one command to the engine and checks what came back.
    fn process(&mut self, command: Command) {
        self.commands_sent += 1;
        for event in self.engine.process(command) {
            match event {
                Event::Accepted { .. } | Event::Cancelled { .. } => {}
                Event::Trade(_) | Event::Rejected { .. } => self.unexpected_events += 1,
            }
        }
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
    fn reset_empties_the_book() {
        let mut translator = L2Translator::new();
        translator.apply(&[level(Side::Buy, 100, 5)]);
        translator.reset();
        assert_eq!(translator.engine().book().order_count(), 0);
    }
}
