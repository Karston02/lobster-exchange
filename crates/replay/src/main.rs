//! Replays a recording and rebuilds Coinbase's order book from it, checking
//! the data along the way.
//!
//! ```text
//! cargo run --release -p lobster-replay -- data/coinbase/BTC-USD/<file>.jsonl
//! ```

use std::fs::File;
use std::io::{BufRead, BufReader};
use std::time::Instant;

use lobster_engine::{Price, Quantity, Side};
use lobster_replay::coinbase::{BTC_USD, EventKind, Message, RecordedLine};
use lobster_replay::l2book::L2Book;

/// What we found while replaying, printed at the end.
#[derive(Debug, Default)]
struct Stats {
    lines: u64,
    unparsed_lines: u64,
    l2_messages: u64,
    snapshots: u64,
    snapshot_levels: u64,
    updates: u64,
    removals: u64,
    bad_numbers: u64,
    sequence_gaps: u64,
    /// Messages after which the book was crossed (bid >= ask): should be zero
    crossed_after: u64,
    first_recv_ns: Option<u64>,
    last_recv_ns: Option<u64>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let Some(path) = std::env::args().nth(1) else {
        eprintln!("usage: lobster-replay <recording.jsonl>");
        std::process::exit(2);
    };

    let started = Instant::now();
    let reader = BufReader::new(File::open(&path)?);
    let mut book = L2Book::new();
    let mut stats = Stats::default();
    let mut last_sequence: Option<u64> = None;

    for line in reader.lines() {
        let line = line?;
        stats.lines += 1;

        let recorded: RecordedLine = match serde_json::from_str(&line) {
            Ok(recorded) => recorded,
            Err(error) => {
                stats.unparsed_lines += 1;
                eprintln!("line {}: could not parse ({error})", stats.lines);
                continue;
            }
        };
        stats.first_recv_ns.get_or_insert(recorded.recv_ns);
        stats.last_recv_ns = Some(recorded.recv_ns);

        // Every message on a connection is numbered; a jump means we missed some
        let sequence = recorded.msg.sequence_num();
        if let Some(last) = last_sequence
            && sequence != last + 1
        {
            stats.sequence_gaps += 1;
            eprintln!(
                "line {}: sequence jumped from {last} to {sequence}",
                stats.lines
            );
        }
        last_sequence = Some(sequence);

        let Message::L2Data(data) = recorded.msg else {
            continue;
        };
        stats.l2_messages += 1;

        for event in &data.events {
            if event.kind == EventKind::Snapshot {
                book.clear();
                stats.snapshots += 1;
            }
            for raw in &event.updates {
                let update = match raw.to_level_update(BTC_USD) {
                    Ok(update) => update,
                    Err(error) => {
                        stats.bad_numbers += 1;
                        eprintln!("line {}: bad number in {raw:?} ({error})", stats.lines);
                        continue;
                    }
                };
                match event.kind {
                    EventKind::Snapshot => stats.snapshot_levels += 1,
                    EventKind::Update if update.quantity.0 == 0 => stats.removals += 1,
                    EventKind::Update => stats.updates += 1,
                }
                book.apply(update);
            }
        }

        // Checked after the whole message, since a message can briefly cross mid-way
        if book.is_crossed() {
            stats.crossed_after += 1;
        }
    }

    report(&path, &stats, &book, started.elapsed().as_secs_f64());
    Ok(())
}

fn report(path: &str, stats: &Stats, book: &L2Book, elapsed_secs: f64) {
    let recorded_secs = match (stats.first_recv_ns, stats.last_recv_ns) {
        (Some(first), Some(last)) => (last - first) as f64 / 1e9,
        _ => 0.0,
    };
    let changes = stats.updates + stats.removals;

    println!("{path}");
    println!(
        "  recorded:        {recorded_secs:.0} s, {} lines",
        stats.lines
    );
    println!(
        "  replayed in:     {elapsed_secs:.2} s ({:.0}x real time)",
        recorded_secs / elapsed_secs.max(1e-9)
    );
    println!(
        "  l2 messages:     {} ({} snapshots, {} levels in snapshots)",
        stats.l2_messages, stats.snapshots, stats.snapshot_levels
    );
    println!(
        "  level changes:   {changes} ({} set, {} removed), {:.0}/s",
        stats.updates,
        stats.removals,
        changes as f64 / recorded_secs.max(1e-9)
    );
    println!();
    println!("  checks (all should be 0):");
    println!("    unparsed lines:   {}", stats.unparsed_lines);
    println!("    bad numbers:      {}", stats.bad_numbers);
    println!("    sequence gaps:    {}", stats.sequence_gaps);
    println!("    crossed book:     {}", stats.crossed_after);
    println!();

    let (bid_levels, ask_levels) = book.depth();
    println!("  final book: {bid_levels} bid levels, {ask_levels} ask levels");
    if let (Some((bid, _)), Some((ask, _))) = (book.best_bid(), book.best_ask()) {
        println!(
            "  spread: {} ({} ticks)",
            dollars(Price(ask.0 - bid.0)),
            ask.0 - bid.0
        );
    }
    println!("       bid size      bid price |  ask price      ask size");
    let bids = book.top(Side::Buy, 5);
    let asks = book.top(Side::Sell, 5);
    for i in 0..bids.len().max(asks.len()) {
        let left = bids
            .get(i)
            .map(|(p, q)| format!("{:>14} {:>14}", btc(*q), dollars(*p)))
            .unwrap_or_else(|| " ".repeat(29));
        let right = asks
            .get(i)
            .map(|(p, q)| format!("{:>10} {:>13}", dollars(*p), btc(*q)))
            .unwrap_or_default();
        println!("  {left} | {right}");
    }
}

/// Formats integer cents as dollars, e.g. 7323208 -> "$73232.08".
fn dollars(price: Price) -> String {
    format!("${}.{:02}", price.0 / 100, price.0 % 100)
}

/// Formats integer satoshis as BTC, e.g. 34041950 -> "0.34041950".
fn btc(quantity: Quantity) -> String {
    format!(
        "{}.{:08}",
        quantity.0 / 100_000_000,
        quantity.0 % 100_000_000
    )
}
