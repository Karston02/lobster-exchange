//! Putting book changes and trades back in the order they happened.
//!
//! Coinbase sends level2 changes as they happen, but batches trades every
//! 250 ms, so a trade usually arrives after the book change it caused. A
//! replay can read ahead, so we sort everything by Coinbase's own timestamps
//! instead of by arrival.
//!
//! In real recordings, a fill's level2 change is stamped a few milliseconds
//! after its trade most of the time, but not always. `trade_lead_ns` moves
//! every trade that much earlier when sorting, so trades are applied before
//! the book changes they explain. See ARCHITECTURE.md, decision #11.

use lobster_engine::{Price, Quantity, Side};

use crate::l2book::LevelUpdate;

/// A trade that happened on the exchange.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TradePrint {
    /// The side of the order that was resting on the book.
    pub maker_side: Side,
    pub price: Price,
    pub quantity: Quantity,
}

/// One thing to apply, in replay order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Step {
    /// Book changes stamped with the same time, applied together.
    Levels(Vec<LevelUpdate>),
    Trade(TradePrint),
}

/// Something with a Coinbase timestamp, in nanoseconds since 1970.
#[derive(Debug, Clone, Copy)]
pub struct Timed<T> {
    pub exchange_ns: u64,
    pub item: T,
}

/// Merges level changes and trades into replay order.
///
/// Sorted by timestamp, with trades moved `trade_lead_ns` earlier. Ties keep
/// trades first, and otherwise keep the original order. Consecutive level
/// changes with the same sort time become one `Step::Levels`. Each step is
/// stamped with its sort time.
pub fn merge(
    levels: &[Timed<LevelUpdate>],
    trades: &[Timed<TradePrint>],
    trade_lead_ns: u64,
) -> Vec<Timed<Step>> {
    enum Item {
        Level(LevelUpdate),
        Trade(TradePrint),
    }

    // (sort time, 0 for trades and 1 for levels, item)
    let mut items: Vec<(u64, u8, Item)> = Vec::with_capacity(levels.len() + trades.len());
    for trade in trades {
        let time = trade.exchange_ns.saturating_sub(trade_lead_ns);
        items.push((time, 0, Item::Trade(trade.item)));
    }
    for level in levels {
        items.push((level.exchange_ns, 1, Item::Level(level.item)));
    }
    // `sort_by_key` is stable: equal keys keep the order they were pushed in
    items.sort_by_key(|(time, rank, _)| (*time, *rank));

    let mut steps = Vec::new();
    let mut batch: Vec<LevelUpdate> = Vec::new();
    let mut batch_time = 0;
    let flush = |steps: &mut Vec<Timed<Step>>, batch: &mut Vec<LevelUpdate>, time: u64| {
        if !batch.is_empty() {
            steps.push(Timed {
                exchange_ns: time,
                item: Step::Levels(std::mem::take(batch)),
            });
        }
    };
    for (time, _, item) in items {
        match item {
            Item::Level(update) => {
                if batch_time != time {
                    flush(&mut steps, &mut batch, batch_time);
                }
                batch_time = time;
                batch.push(update);
            }
            Item::Trade(trade) => {
                flush(&mut steps, &mut batch, batch_time);
                steps.push(Timed {
                    exchange_ns: time,
                    item: Step::Trade(trade),
                });
            }
        }
    }
    flush(&mut steps, &mut batch, batch_time);
    steps
}

#[cfg(test)]
mod tests {
    use super::*;

    fn level(ns: u64, price: u64) -> Timed<LevelUpdate> {
        Timed {
            exchange_ns: ns,
            item: LevelUpdate {
                side: Side::Buy,
                price: Price(price),
                quantity: Quantity(1),
            },
        }
    }

    fn trade(ns: u64, price: u64) -> Timed<TradePrint> {
        Timed {
            exchange_ns: ns,
            item: TradePrint {
                maker_side: Side::Buy,
                price: Price(price),
                quantity: Quantity(1),
            },
        }
    }

    /// Summarizes steps as e.g. "L100,101 T50"
    fn shape(steps: &[Timed<Step>]) -> String {
        steps
            .iter()
            .map(|step| match &step.item {
                Step::Levels(updates) => {
                    let prices: Vec<String> =
                        updates.iter().map(|u| u.price.0.to_string()).collect();
                    format!("L{}", prices.join(","))
                }
                Step::Trade(trade) => format!("T{}", trade.price.0),
            })
            .collect::<Vec<_>>()
            .join(" ")
    }

    #[test]
    fn sorts_by_time_not_arrival() {
        // The trade arrived last but happened between the two book changes
        let steps = merge(&[level(10, 100), level(30, 101)], &[trade(20, 50)], 0);
        assert_eq!(shape(&steps), "L100 T50 L101");
    }

    #[test]
    fn same_time_levels_are_one_batch() {
        let steps = merge(&[level(10, 100), level(10, 101), level(11, 102)], &[], 0);
        assert_eq!(shape(&steps), "L100,101 L102");
    }

    #[test]
    fn ties_put_trades_first() {
        let steps = merge(&[level(10, 100)], &[trade(10, 50)], 0);
        assert_eq!(shape(&steps), "T50 L100");
    }

    #[test]
    fn lead_moves_trades_earlier() {
        // Without a lead the trade comes after the book change; a 5 ns lead puts it before
        let levels = [level(10, 100)];
        let trades = [trade(12, 50)];
        assert_eq!(shape(&merge(&levels, &trades, 0)), "L100 T50");
        assert_eq!(shape(&merge(&levels, &trades, 5)), "T50 L100");
    }

    #[test]
    fn steps_carry_their_sort_time() {
        let steps = merge(&[level(10, 100), level(30, 101)], &[trade(20, 50)], 5);
        let times: Vec<u64> = steps.iter().map(|step| step.exchange_ns).collect();
        assert_eq!(times, vec![10, 15, 30]);
    }

    #[test]
    fn trades_split_level_batches() {
        let steps = merge(&[level(10, 100), level(10, 101)], &[trade(10, 50)], 0);
        assert_eq!(shape(&steps), "T50 L100,101");
    }
}
