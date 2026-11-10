//! Reading a recording file made by `lobster-recorder` into memory.
//!
//! Every price, size and timestamp is converted into exact integers here, so
//! the replay itself never touches text.

use std::fs::File;
use std::io::{BufRead, BufReader};

use lobster_engine::{Price, Quantity};

use crate::coinbase::{BTC_USD, EventKind, Message, RecordedLine};
use crate::decimal::parse_fixed;
use crate::l2book::LevelUpdate;
use crate::time::parse_utc_ns;
use crate::timeline::{Timed, TradePrint};

/// Everything read from a recording file, ready to replay.
#[derive(Debug, Default)]
pub struct Recording {
    /// The opening snapshot: every level of the book when recording started.
    pub snapshot: Vec<LevelUpdate>,
    /// Coinbase's time for the snapshot.
    pub snapshot_ns: u64,
    pub levels: Vec<Timed<LevelUpdate>>,
    pub trades: Vec<Timed<TradePrint>>,
    /// Our receive times of the first and last lines.
    pub first_recv_ns: Option<u64>,
    pub last_recv_ns: Option<u64>,
    pub lines: u64,
}

/// Problems found while reading. All should be zero.
#[derive(Debug, Default)]
pub struct ReadProblems {
    pub unparsed_lines: u64,
    pub bad_numbers: u64,
    pub bad_times: u64,
    pub sequence_gaps: u64,
    /// More than one snapshot in a file; only the first is used
    pub extra_snapshots: u64,
}

/// Reads a recording into memory, converting every number and timestamp.
pub fn read_recording(path: &str, problems: &mut ReadProblems) -> std::io::Result<Recording> {
    let mut recording = Recording::default();
    let mut last_sequence: Option<u64> = None;
    let mut have_snapshot = false;

    for line in BufReader::new(File::open(path)?).lines() {
        let line = line?;
        recording.lines += 1;
        let line_number = recording.lines;

        let recorded: RecordedLine = match serde_json::from_str(&line) {
            Ok(recorded) => recorded,
            Err(error) => {
                problems.unparsed_lines += 1;
                eprintln!("line {line_number}: could not parse ({error})");
                continue;
            }
        };
        recording.first_recv_ns.get_or_insert(recorded.recv_ns);
        recording.last_recv_ns = Some(recorded.recv_ns);

        // Every message on a connection is numbered; a jump means we missed some
        let sequence = recorded.msg.sequence_num();
        if let Some(last) = last_sequence
            && sequence != last + 1
        {
            problems.sequence_gaps += 1;
            eprintln!("line {line_number}: sequence jumped from {last} to {sequence}");
        }
        last_sequence = Some(sequence);

        match recorded.msg {
            Message::L2Data(data) => {
                for event in &data.events {
                    let is_snapshot = event.kind == EventKind::Snapshot;
                    if is_snapshot {
                        if have_snapshot {
                            problems.extra_snapshots += 1;
                            continue;
                        }
                        have_snapshot = true;
                        match parse_utc_ns(&data.timestamp) {
                            Ok(ns) => recording.snapshot_ns = ns,
                            Err(_) => problems.bad_times += 1,
                        }
                    }
                    for raw in &event.updates {
                        let Ok(update) = raw.to_level_update(BTC_USD) else {
                            problems.bad_numbers += 1;
                            continue;
                        };
                        if is_snapshot {
                            recording.snapshot.push(update);
                            continue;
                        }
                        match parse_utc_ns(&raw.event_time) {
                            Ok(exchange_ns) => recording.levels.push(Timed {
                                exchange_ns,
                                item: update,
                            }),
                            Err(_) => problems.bad_times += 1,
                        }
                    }
                }
            }
            Message::MarketTrades(trades) => {
                // The first trades message is a snapshot of trades from before we connected
                for event in trades.events.iter().filter(|e| e.kind == EventKind::Update) {
                    for raw in &event.trades {
                        let price = parse_fixed(&raw.price, BTC_USD.price_decimals);
                        let quantity = parse_fixed(&raw.size, BTC_USD.quantity_decimals);
                        let (Ok(price), Ok(quantity)) = (price, quantity) else {
                            problems.bad_numbers += 1;
                            continue;
                        };
                        let Ok(exchange_ns) = parse_utc_ns(&raw.time) else {
                            problems.bad_times += 1;
                            continue;
                        };
                        recording.trades.push(Timed {
                            exchange_ns,
                            item: TradePrint {
                                maker_side: raw.side.into(),
                                price: Price(price),
                                quantity: Quantity(quantity),
                            },
                        });
                    }
                }
            }
            Message::Heartbeats(_) | Message::Subscriptions(_) => {}
        }
    }
    Ok(recording)
}
