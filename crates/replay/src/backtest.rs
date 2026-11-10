//! A backtest: replay real market data through the engine while a bot trades.
//!
//! The market side comes from a recording (book changes and trades, replayed
//! with [`L2Translator`]). The bot's orders sit in the same engine, in the same
//! lines as the market's synthetic orders, so they only fill when real trades
//! reach them, or when they cross the book themselves.
//!
//! Two things keep results honest:
//!
//! - Latency: a bot's command reaches the engine `latency_ns` after it was
//!   sent, so the market can move in between.
//! - Fees: every fill pays the maker or taker fee.
//!
//! Money is counted exactly in "tick-lots": one price tick times one size lot.
//! For BTC-USD that's $0.01 × 0.00000001 BTC = $0.0000000001.

use std::collections::{HashMap, VecDeque};

use lobster_engine::{Command, Event, Order, OrderId, Price, Quantity, Side};

use crate::l2book::L2Book;
use crate::recording::Recording;
use crate::timeline::{Step, Timed, merge};
use crate::translate::{FIRST_BOT_ID, L2Translator};

/// Settings for one backtest.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BacktestConfig {
    /// How long a bot's command takes to reach the exchange, in nanoseconds.
    pub latency_ns: u64,
    /// Fee for fills where the bot's order was resting, in basis points (1/100 of a percent).
    pub maker_fee_bps: u32,
    /// Fee for fills where the bot's order crossed the book, in basis points.
    pub taker_fee_bps: u32,
    /// Moves trades earlier when ordering the replay (see `timeline.rs`).
    pub trade_lead_ns: u64,
}

impl Default for BacktestConfig {
    /// 10 ms latency (about what the recorder measured to Coinbase), no fees.
    fn default() -> Self {
        Self {
            latency_ns: 10_000_000,
            maker_fee_bps: 0,
            taker_fee_bps: 0,
            trade_lead_ns: 0,
        }
    }
}

/// One fill of a bot order.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Fill {
    /// Exchange time of the fill, in nanoseconds since 1970.
    pub time_ns: u64,
    pub order_id: OrderId,
    pub side: Side,
    pub price: Price,
    pub quantity: Quantity,
    /// True if the bot's order was resting (maker), false if it crossed (taker).
    pub maker: bool,
    /// Fee paid, in tick-lots.
    pub fee: i128,
}

/// A replay of one recording with a bot trading in it.
#[derive(Debug)]
pub struct Backtest {
    config: BacktestConfig,
    translator: L2Translator,
    /// Coinbase's book as recorded, without the bot's orders
    market: L2Book,
    steps: Vec<Timed<Step>>,
    next_step: usize,
    now_ns: u64,
    /// Bot commands still travelling to the exchange, in the order they were sent
    in_flight: VecDeque<Timed<Command>>,
    next_bot_id: u64,
    /// The side of every bot order ever sent, for attributing fills
    bot_sides: HashMap<OrderId, Side>,
    position: i64,
    cash: i128,
    fees_paid: i128,
    fills: Vec<Fill>,
    fill_count: u64,
    rejections: u64,
    unfilled_trade_volume: u64,
}

impl Backtest {
    /// Sets up a backtest: applies the recording's opening snapshot and puts
    /// its book changes and trades in replay order. The clock starts at the
    /// snapshot's time.
    pub fn new(recording: &Recording, config: BacktestConfig) -> Self {
        let mut translator = L2Translator::new();
        let mut market = L2Book::new();
        for update in &recording.snapshot {
            market.apply(*update);
        }
        translator.apply(&recording.snapshot);

        // Trades from before the snapshot are already reflected in it
        let trades: Vec<_> = recording
            .trades
            .iter()
            .filter(|trade| trade.exchange_ns >= recording.snapshot_ns)
            .copied()
            .collect();
        let steps = merge(&recording.levels, &trades, config.trade_lead_ns);

        Self {
            config,
            translator,
            market,
            steps,
            next_step: 0,
            now_ns: recording.snapshot_ns,
            in_flight: VecDeque::new(),
            next_bot_id: FIRST_BOT_ID,
            bot_sides: HashMap::new(),
            position: 0,
            cash: 0,
            fees_paid: 0,
            fills: Vec::new(),
            fill_count: 0,
            rejections: 0,
            unfilled_trade_volume: 0,
        }
    }

    // ---- The clock ----

    /// The current exchange time, in nanoseconds since 1970.
    pub fn now_ns(&self) -> u64 {
        self.now_ns
    }

    /// When the next thing happens (a market step or a bot command arriving),
    /// or `None` if the replay is over.
    pub fn next_event_ns(&self) -> Option<u64> {
        let market = self.steps.get(self.next_step).map(|step| step.exchange_ns);
        let bot = self.in_flight.front().map(|command| command.exchange_ns);
        match (market, bot) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        }
    }

    /// Returns whether everything has been replayed, including bot commands
    /// still in flight.
    pub fn is_finished(&self) -> bool {
        self.next_event_ns().is_none()
    }

    /// Returns whether the recording's market data has all been replayed.
    /// A strategy loop should stop here: after this, nothing new can happen.
    pub fn market_finished(&self) -> bool {
        self.next_step >= self.steps.len()
    }

    /// Processes the next thing that happens. Returns false if there was nothing left.
    pub fn step(&mut self) -> bool {
        let market = self.steps.get(self.next_step).map(|step| step.exchange_ns);
        let bot = self.in_flight.front().map(|command| command.exchange_ns);
        match (market, bot) {
            // A bot command that arrives at the same moment as a market event goes first
            (Some(market), Some(bot)) if bot <= market => self.deliver_bot_command(),
            (None, Some(_)) => self.deliver_bot_command(),
            (Some(_), _) => self.apply_market_step(),
            (None, None) => return false,
        }
        true
    }

    /// Processes everything up to and including `time_ns`, then sets the clock to it.
    pub fn run_until(&mut self, time_ns: u64) {
        while self.next_event_ns().is_some_and(|next| next <= time_ns) {
            self.step();
        }
        self.now_ns = self.now_ns.max(time_ns);
    }

    fn apply_market_step(&mut self) {
        let step = &self.steps[self.next_step];
        self.next_step += 1;
        self.now_ns = self.now_ns.max(step.exchange_ns);
        match &step.item {
            Step::Levels(updates) => {
                for update in updates {
                    self.market.apply(*update);
                }
                self.translator.apply(updates);
            }
            Step::Trade(trade) => {
                self.unfilled_trade_volume += self.translator.apply_trade(*trade).0;
            }
        }
        // The market's moves may have filled bot orders
        let events = self.translator.take_outside_events();
        self.record_events(&events);
    }

    fn deliver_bot_command(&mut self) {
        let Some(command) = self.in_flight.pop_front() else {
            return;
        };
        self.now_ns = self.now_ns.max(command.exchange_ns);
        let events = self.translator.submit(command.item);
        self.record_events(&events);
    }

    // ---- The bot's commands (each arrives after the configured latency) ----

    /// Sends a limit order. Returns its id right away; it reaches the book later.
    pub fn submit_limit(&mut self, side: Side, price: Price, quantity: Quantity) -> OrderId {
        let id = self.new_bot_id(side);
        self.send(Command::NewLimit {
            id,
            side,
            price,
            quantity,
        });
        id
    }

    /// Sends an immediate-or-cancel order (trade now within `price`, cancel the rest).
    pub fn submit_ioc(&mut self, side: Side, price: Price, quantity: Quantity) -> OrderId {
        let id = self.new_bot_id(side);
        self.send(Command::NewImmediateOrCancel {
            id,
            side,
            price,
            quantity,
        });
        id
    }

    /// Sends a market order (trade now at any price, cancel the rest).
    pub fn submit_market(&mut self, side: Side, quantity: Quantity) -> OrderId {
        let id = self.new_bot_id(side);
        self.send(Command::NewMarket { id, side, quantity });
        id
    }

    /// Sends a cancel. If the order fills before the cancel arrives, the
    /// cancel is rejected, just like on a real exchange.
    pub fn cancel(&mut self, id: OrderId) {
        self.send(Command::Cancel { id });
    }

    fn send(&mut self, command: Command) {
        self.in_flight.push_back(Timed {
            exchange_ns: self.now_ns + self.config.latency_ns,
            item: command,
        });
    }

    fn new_bot_id(&mut self, side: Side) -> OrderId {
        let id = OrderId(self.next_bot_id);
        self.next_bot_id += 1;
        self.bot_sides.insert(id, side);
        id
    }

    // ---- Accounting ----

    fn record_events(&mut self, events: &[Event]) {
        for event in events {
            match event {
                Event::Trade(trade) => {
                    for (id, maker) in [(trade.maker_order_id, true), (trade.taker_order_id, false)]
                    {
                        if let Some(&side) = self.bot_sides.get(&id) {
                            self.record_fill(id, side, trade.price, trade.quantity, maker);
                        }
                    }
                }
                Event::Rejected { id, .. } if self.bot_sides.contains_key(id) => {
                    self.rejections += 1;
                }
                _ => {}
            }
        }
    }

    fn record_fill(
        &mut self,
        id: OrderId,
        side: Side,
        price: Price,
        quantity: Quantity,
        maker: bool,
    ) {
        let notional = i128::from(price.0) * i128::from(quantity.0);
        let fee_bps = if maker {
            self.config.maker_fee_bps
        } else {
            self.config.taker_fee_bps
        };
        // Round fees up, never in the bot's favor
        let fee = (notional * i128::from(fee_bps) + 9_999) / 10_000;
        match side {
            Side::Buy => {
                self.position += quantity.0 as i64;
                self.cash -= notional + fee;
            }
            Side::Sell => {
                self.position -= quantity.0 as i64;
                self.cash += notional - fee;
            }
        }
        self.fees_paid += fee;
        self.fill_count += 1;
        self.fills.push(Fill {
            time_ns: self.now_ns,
            order_id: id,
            side,
            price,
            quantity,
            maker,
            fee,
        });
    }

    /// Removes and returns the bot's fills since the last call.
    pub fn take_fills(&mut self) -> Vec<Fill> {
        std::mem::take(&mut self.fills)
    }

    /// The bot's position in lots: positive means it owns BTC, negative means it's short.
    pub fn position(&self) -> i64 {
        self.position
    }

    /// The bot's cash in tick-lots (starts at 0; buying spends, selling earns).
    pub fn cash(&self) -> i128 {
        self.cash
    }

    /// Total fees paid, in tick-lots.
    pub fn fees_paid(&self) -> i128 {
        self.fees_paid
    }

    /// Profit and loss if the position were valued at `price`, in tick-lots.
    pub fn pnl_at(&self, price: Price) -> i128 {
        self.cash + i128::from(self.position) * i128::from(price.0)
    }

    /// Profit and loss valued at the market's mid price (rounded down), or
    /// `None` if one side of the market is empty.
    pub fn pnl_at_mid(&self) -> Option<i128> {
        self.market_mid().map(|mid| self.pnl_at(mid))
    }

    /// How many bot fills there have been in total.
    pub fn fill_count(&self) -> u64 {
        self.fill_count
    }

    /// How many bot commands were rejected (e.g. a cancel that arrived after a fill).
    pub fn rejections(&self) -> u64 {
        self.rejections
    }

    /// Replayed trade volume the engine had no matching quantity for, in lots.
    pub fn unfilled_trade_volume(&self) -> u64 {
        self.unfilled_trade_volume
    }

    // ---- What the bot can see ----

    /// Coinbase's best bid as recorded (not including the bot's orders).
    pub fn market_best_bid(&self) -> Option<(Price, Quantity)> {
        self.market.best_bid()
    }

    /// Coinbase's best ask as recorded (not including the bot's orders).
    pub fn market_best_ask(&self) -> Option<(Price, Quantity)> {
        self.market.best_ask()
    }

    /// The midpoint of Coinbase's best bid and ask, rounded down to a tick.
    pub fn market_mid(&self) -> Option<Price> {
        let (bid, _) = self.market.best_bid()?;
        let (ask, _) = self.market.best_ask()?;
        Some(Price((bid.0 + ask.0) / 2))
    }

    /// Coinbase's best `n` levels on one side, best first.
    pub fn market_top(&self, side: Side, n: usize) -> Vec<(Price, Quantity)> {
        self.market.top(side, n)
    }

    /// The bot's orders currently resting on the book.
    pub fn open_orders(&self) -> Vec<Order> {
        let book = self.translator.engine().book();
        let mut orders: Vec<Order> = self
            .bot_sides
            .keys()
            .filter_map(|id| book.order(*id).cloned())
            .collect();
        orders.sort_by_key(|order| order.id);
        orders
    }

    /// How much quantity is ahead of a resting bot order in its line, or
    /// `None` if the order isn't resting.
    pub fn queue_ahead(&self, id: OrderId) -> Option<Quantity> {
        let book = self.translator.engine().book();
        let order = book.order(id)?;
        let ahead = book
            .orders_at(order.side, order.price)
            .iter()
            .take_while(|other| other.id != id)
            .map(|other| other.quantity.0)
            .sum();
        Some(Quantity(ahead))
    }

    /// Read-only access to the engine-side translator (for checks and stats).
    pub fn translator(&self) -> &L2Translator {
        &self.translator
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::l2book::LevelUpdate;
    use crate::timeline::TradePrint;

    const MS: u64 = 1_000_000;

    fn level(side: Side, price: u64, quantity: u64) -> LevelUpdate {
        LevelUpdate {
            side,
            price: Price(price),
            quantity: Quantity(quantity),
        }
    }

    fn timed_level(ms: u64, side: Side, price: u64, quantity: u64) -> Timed<LevelUpdate> {
        Timed {
            exchange_ns: ms * MS,
            item: level(side, price, quantity),
        }
    }

    fn timed_trade(ms: u64, maker_side: Side, price: u64, quantity: u64) -> Timed<TradePrint> {
        Timed {
            exchange_ns: ms * MS,
            item: TradePrint {
                maker_side,
                price: Price(price),
                quantity: Quantity(quantity),
            },
        }
    }

    /// A market with a 99 bid (10) and 101 ask (10) at time 0.
    fn recording(levels: Vec<Timed<LevelUpdate>>, trades: Vec<Timed<TradePrint>>) -> Recording {
        Recording {
            snapshot: vec![level(Side::Buy, 99, 10), level(Side::Sell, 101, 10)],
            snapshot_ns: 0,
            levels,
            trades,
            ..Default::default()
        }
    }

    fn config(latency_ms: u64) -> BacktestConfig {
        BacktestConfig {
            latency_ns: latency_ms * MS,
            ..Default::default()
        }
    }

    #[test]
    fn replays_the_market_with_no_bot() {
        let recording = recording(
            vec![timed_level(5, Side::Buy, 100, 4)],
            vec![timed_trade(9, Side::Sell, 101, 3)],
        );
        let mut backtest = Backtest::new(&recording, config(0));
        while backtest.step() {}

        assert!(backtest.market_finished());
        assert_eq!(backtest.market_best_bid(), Some((Price(100), Quantity(4))));
        assert_eq!(backtest.now_ns(), 9 * MS);
        assert!(backtest.is_finished());
        assert_eq!(backtest.fill_count(), 0);
    }

    #[test]
    fn orders_arrive_after_the_latency() {
        let mut backtest = Backtest::new(&recording(vec![], vec![]), config(10));
        let id = backtest.submit_limit(Side::Buy, Price(99), Quantity(2));

        backtest.run_until(9 * MS);
        assert!(backtest.open_orders().is_empty()); // Still travelling
        backtest.run_until(10 * MS);
        assert_eq!(backtest.open_orders().len(), 1);
        assert_eq!(backtest.open_orders()[0].id, id);
    }

    #[test]
    fn resting_order_waits_behind_the_line_and_fills_from_trades() {
        // Sells hit the 99 bid: first 6 (all ahead of us), then 6 more (4 ahead + 2 of ours)
        let recording = recording(
            vec![],
            vec![
                timed_trade(20, Side::Buy, 99, 6),
                timed_trade(30, Side::Buy, 99, 6),
            ],
        );
        let mut backtest = Backtest::new(&recording, config(1));
        let id = backtest.submit_limit(Side::Buy, Price(99), Quantity(3));

        backtest.run_until(10 * MS);
        assert_eq!(backtest.queue_ahead(id), Some(Quantity(10)));

        backtest.run_until(20 * MS);
        assert_eq!(backtest.queue_ahead(id), Some(Quantity(4)));
        assert_eq!(backtest.fill_count(), 0);

        backtest.run_until(30 * MS);
        let fills = backtest.take_fills();
        assert_eq!(fills.len(), 1);
        assert_eq!((fills[0].quantity, fills[0].maker), (Quantity(2), true));
        assert_eq!(backtest.position(), 2);
        assert_eq!(backtest.cash(), -(99 * 2));
    }

    #[test]
    fn crossing_order_is_a_taker_and_pays_the_taker_fee() {
        let mut backtest = Backtest::new(
            &recording(vec![], vec![]),
            BacktestConfig {
                latency_ns: 0,
                maker_fee_bps: 0,
                taker_fee_bps: 100, // 1%
                trade_lead_ns: 0,
            },
        );
        backtest.submit_ioc(Side::Buy, Price(101), Quantity(1_000));
        backtest.run_until(0);

        let fills = backtest.take_fills();
        assert_eq!(fills.len(), 1);
        assert!(!fills[0].maker);
        assert_eq!(fills[0].quantity, Quantity(10)); // Only 10 was offered
        assert_eq!(fills[0].fee, 11); // 1% of 101 * 10 = 10.1, rounded up
        assert_eq!(backtest.cash(), -(101 * 10) - 11);
        assert_eq!(backtest.position(), 10);
    }

    #[test]
    fn market_cancels_never_remove_the_bot_order() {
        // The 99 bid shrinks to 2 and then disappears entirely on Coinbase
        let recording = recording(
            vec![
                timed_level(20, Side::Buy, 99, 2),
                timed_level(30, Side::Buy, 99, 0),
            ],
            vec![],
        );
        let mut backtest = Backtest::new(&recording, config(1));
        let id = backtest.submit_limit(Side::Buy, Price(99), Quantity(3));

        backtest.run_until(20 * MS);
        assert_eq!(backtest.queue_ahead(id), Some(Quantity(2)));
        backtest.run_until(30 * MS);
        assert_eq!(backtest.queue_ahead(id), Some(Quantity(0))); // Now first in line
        assert_eq!(backtest.market_best_bid(), None); // Coinbase's view has no bid
    }

    #[test]
    fn cancel_that_arrives_after_a_fill_is_rejected() {
        let recording = recording(vec![], vec![timed_trade(5, Side::Sell, 101, 1)]);
        let mut backtest = Backtest::new(&recording, config(2));
        // The bot improves the ask to 100; a buyer arrives at 5 ms and takes it
        let id = backtest.submit_limit(Side::Sell, Price(100), Quantity(1));
        backtest.run_until(4 * MS);
        backtest.cancel(id); // Arrives at 6 ms, too late

        backtest.run_until(10 * MS);
        assert_eq!(backtest.fill_count(), 1);
        assert_eq!(backtest.rejections(), 1);
        assert_eq!(backtest.position(), -1);
    }

    #[test]
    fn pnl_values_the_position_at_the_mid() {
        let mut backtest = Backtest::new(&recording(vec![], vec![]), config(0));
        backtest.submit_ioc(Side::Buy, Price(101), Quantity(2));
        backtest.run_until(0);

        // Paid 202; mid is (99 + 101) / 2 = 100, so the position is worth 200
        assert_eq!(backtest.market_mid(), Some(Price(100)));
        assert_eq!(backtest.pnl_at_mid(), Some(-2));
    }
}
