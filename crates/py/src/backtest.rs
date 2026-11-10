//! Python access to `Backtest`: a recording replayed through the engine while
//! a Python strategy trades in it.
//!
//! The strategy loop itself lives in Python. Each call here does a lot of work
//! (e.g. `run_until` can replay thousands of market events), so crossing the
//! Python/Rust boundary stays rare.

use std::collections::HashMap;

use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;

use lobster_engine::{Order, OrderId, Price, Quantity};
use lobster_replay::backtest::{Backtest, BacktestConfig, Fill};
use lobster_replay::recording::{ReadProblems, read_recording};

use crate::{parse_side, side_name};

/// One of the bot's resting orders.
#[pyclass(name = "Order", module = "lobster", frozen, get_all)]
#[derive(Debug, Clone)]
pub struct PyOrder {
    id: u64,
    /// "buy" or "sell".
    side: String,
    /// Price in ticks.
    price: u64,
    /// Unfilled quantity in lots.
    quantity: u64,
}

#[pymethods]
impl PyOrder {
    fn __repr__(&self) -> String {
        format!(
            "Order({}: {} {} @ {})",
            self.id, self.side, self.quantity, self.price
        )
    }
}

impl From<Order> for PyOrder {
    fn from(order: Order) -> Self {
        PyOrder {
            id: order.id.0,
            side: side_name(order.side),
            price: order.price.0,
            quantity: order.quantity.0,
        }
    }
}

/// One fill of a bot order.
#[pyclass(name = "Fill", module = "lobster", frozen, get_all)]
#[derive(Debug, Clone)]
pub struct PyFill {
    /// Exchange time, in nanoseconds since 1970.
    time_ns: u64,
    order_id: u64,
    /// "buy" or "sell".
    side: String,
    /// Price in ticks.
    price: u64,
    /// Quantity in lots.
    quantity: u64,
    /// True if the bot's order was resting (maker), false if it crossed (taker).
    maker: bool,
    /// Fee paid, in tick-lots.
    fee: i128,
}

#[pymethods]
impl PyFill {
    fn __repr__(&self) -> String {
        format!(
            "Fill(order {}: {} {} @ {}, {})",
            self.order_id,
            self.side,
            self.quantity,
            self.price,
            if self.maker { "maker" } else { "taker" }
        )
    }
}

impl From<Fill> for PyFill {
    fn from(fill: Fill) -> Self {
        PyFill {
            time_ns: fill.time_ns,
            order_id: fill.order_id.0,
            side: side_name(fill.side),
            price: fill.price.0,
            quantity: fill.quantity.0,
            maker: fill.maker,
            fee: fill.fee,
        }
    }
}

/// Converts milliseconds from Python into whole nanoseconds.
fn ms_to_ns(name: &str, ms: f64) -> PyResult<u64> {
    if !ms.is_finite() || ms < 0.0 {
        return Err(PyValueError::new_err(format!(
            "{name} must be zero or more, not {ms}"
        )));
    }
    Ok((ms * 1_000_000.0).round() as u64)
}

/// A recording replayed through the engine while a strategy trades in it.
#[pyclass(name = "Backtest", module = "lobster")]
pub struct PyBacktest {
    backtest: Backtest,
    problems: ReadProblems,
    lines: u64,
}

#[pymethods]
impl PyBacktest {
    /// Loads a recording made by `lobster-recorder` and sets up the replay.
    #[new]
    #[pyo3(signature = (path, latency_ms=10.0, maker_fee_bps=0, taker_fee_bps=0, trade_lead_ms=0.0))]
    fn new(
        path: &str,
        latency_ms: f64,
        maker_fee_bps: u32,
        taker_fee_bps: u32,
        trade_lead_ms: f64,
    ) -> PyResult<Self> {
        let config = BacktestConfig {
            latency_ns: ms_to_ns("latency_ms", latency_ms)?,
            maker_fee_bps,
            taker_fee_bps,
            trade_lead_ns: ms_to_ns("trade_lead_ms", trade_lead_ms)?,
        };
        let mut problems = ReadProblems::default();
        let recording = read_recording(path, &mut problems)
            .map_err(|error| PyOSError::new_err(format!("{path}: {error}")))?;
        if recording.snapshot.is_empty() {
            return Err(PyValueError::new_err(format!(
                "{path}: no order book snapshot in this recording"
            )));
        }
        Ok(PyBacktest {
            backtest: Backtest::new(&recording, config),
            problems,
            lines: recording.lines,
        })
    }

    /// Problems found while reading the file. All but "lines" should be zero.
    fn read_summary(&self) -> HashMap<String, u64> {
        HashMap::from([
            ("lines".to_string(), self.lines),
            ("unparsed_lines".to_string(), self.problems.unparsed_lines),
            ("bad_numbers".to_string(), self.problems.bad_numbers),
            ("bad_times".to_string(), self.problems.bad_times),
            ("sequence_gaps".to_string(), self.problems.sequence_gaps),
            ("extra_snapshots".to_string(), self.problems.extra_snapshots),
        ])
    }

    // ---- The clock ----

    /// The current exchange time, in nanoseconds since 1970.
    #[getter]
    fn now_ns(&self) -> u64 {
        self.backtest.now_ns()
    }

    /// Processes everything up to and including `time_ns`.
    fn run_until(&mut self, time_ns: u64) {
        self.backtest.run_until(time_ns);
    }

    /// Processes the next single event. Returns False if nothing was left.
    fn step(&mut self) -> bool {
        self.backtest.step()
    }

    /// When the next thing happens, or None at the end.
    fn next_event_ns(&self) -> Option<u64> {
        self.backtest.next_event_ns()
    }

    /// Whether all the market data has been replayed. Stop the strategy loop here.
    fn market_finished(&self) -> bool {
        self.backtest.market_finished()
    }

    // ---- Orders (each arrives after the latency) ----

    /// Sends a limit order and returns its id.
    fn submit_limit(&mut self, side: &str, price: u64, quantity: u64) -> PyResult<u64> {
        let side = parse_side(side)?;
        let id = self
            .backtest
            .submit_limit(side, Price(price), Quantity(quantity));
        Ok(id.0)
    }

    /// Sends an immediate-or-cancel order and returns its id.
    fn submit_ioc(&mut self, side: &str, price: u64, quantity: u64) -> PyResult<u64> {
        let side = parse_side(side)?;
        let id = self
            .backtest
            .submit_ioc(side, Price(price), Quantity(quantity));
        Ok(id.0)
    }

    /// Sends a market order and returns its id.
    fn submit_market(&mut self, side: &str, quantity: u64) -> PyResult<u64> {
        let side = parse_side(side)?;
        Ok(self.backtest.submit_market(side, Quantity(quantity)).0)
    }

    /// Sends a cancel. It's rejected if the order fills first.
    fn cancel(&mut self, id: u64) {
        self.backtest.cancel(OrderId(id));
    }

    /// The bot's orders resting on the book right now.
    fn open_orders(&self) -> Vec<PyOrder> {
        self.backtest
            .open_orders()
            .into_iter()
            .map(PyOrder::from)
            .collect()
    }

    /// Quantity waiting ahead of a resting order, or None if it isn't resting.
    fn queue_ahead(&self, id: u64) -> Option<u64> {
        self.backtest.queue_ahead(OrderId(id)).map(|q| q.0)
    }

    /// The bot's fills since the last call.
    fn take_fills(&mut self) -> Vec<PyFill> {
        self.backtest
            .take_fills()
            .into_iter()
            .map(PyFill::from)
            .collect()
    }

    // ---- The market (Coinbase's book, without the bot) ----

    /// (price, quantity) of the best bid, or None.
    fn best_bid(&self) -> Option<(u64, u64)> {
        self.backtest.market_best_bid().map(|(p, q)| (p.0, q.0))
    }

    /// (price, quantity) of the best ask, or None.
    fn best_ask(&self) -> Option<(u64, u64)> {
        self.backtest.market_best_ask().map(|(p, q)| (p.0, q.0))
    }

    /// Midpoint of the best bid and ask in ticks (rounded down), or None.
    fn mid(&self) -> Option<u64> {
        self.backtest.market_mid().map(|p| p.0)
    }

    /// The best `n` levels on one side as (price, quantity) pairs, best first.
    fn top(&self, side: &str, n: usize) -> PyResult<Vec<(u64, u64)>> {
        let side = parse_side(side)?;
        Ok(self
            .backtest
            .market_top(side, n)
            .into_iter()
            .map(|(p, q)| (p.0, q.0))
            .collect())
    }

    // ---- Results ----

    /// Position in lots: positive owns BTC, negative is short.
    #[getter]
    fn position(&self) -> i64 {
        self.backtest.position()
    }

    /// Cash in tick-lots (starts at 0).
    #[getter]
    fn cash(&self) -> i128 {
        self.backtest.cash()
    }

    /// Total fees paid, in tick-lots.
    #[getter]
    fn fees_paid(&self) -> i128 {
        self.backtest.fees_paid()
    }

    /// Total number of bot fills.
    #[getter]
    fn fill_count(&self) -> u64 {
        self.backtest.fill_count()
    }

    /// Bot commands that were rejected (e.g. a cancel that arrived after a fill).
    #[getter]
    fn rejections(&self) -> u64 {
        self.backtest.rejections()
    }

    /// Replayed trade volume the engine had no matching quantity for, in lots.
    #[getter]
    fn unfilled_trade_volume(&self) -> u64 {
        self.backtest.unfilled_trade_volume()
    }

    /// Profit and loss with the position valued at `price`, in tick-lots.
    fn pnl_at(&self, price: u64) -> i128 {
        self.backtest.pnl_at(Price(price))
    }

    /// Profit and loss with the position valued at the mid, or None.
    fn pnl_at_mid(&self) -> Option<i128> {
        self.backtest.pnl_at_mid()
    }
}
