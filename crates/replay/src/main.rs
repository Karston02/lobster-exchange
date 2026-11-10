//! Replays a recording: rebuilds Coinbase's order book from it, feeds the same
//! changes into our matching engine as synthetic orders, and checks that the
//! two books agree.
//!
//! ```text
//! cargo run --release -p lobster-replay -- data/coinbase/BTC-USD/<file>.jsonl
//! ```

use std::fs::File;
use std::io::{BufRead, BufReader};
use std::time::Instant;

use lobster_engine::{Price, Quantity, Side};
use lobster_replay::coinbase::{BTC_USD, EventKind, Message, RecordedLine};
use lobster_replay::l2book::{L2Book, LevelUpdate};
use lobster_replay::translate::L2Translator;

/// What we found while replaying, printed at the end.
#[derive(Debug, Default)]
struct Stats {
    lines: u64,
    unparsed_lines: u64,
    l2_messages: u64,
    trade_messages: u64,
    /// Trades in `update` events (the opening snapshot of recent trades is skipped)
    trades: u64,
    snapshots: u64,
    snapshot_levels: u64,
    updates: u64,
    removals: u64,
    bad_numbers: u64,
    sequence_gaps: u64,
    /// Messages after which the book was crossed (bid >= ask): should be zero
    crossed_after: u64,
    /// Messages after which the engine's best bid or ask differed from Coinbase's
    top_mismatches: u64,
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
    let mut translator = L2Translator::new();
    let mut updates: Vec<LevelUpdate> = Vec::new();
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

        let data = match recorded.msg {
            Message::L2Data(data) => data,
            Message::MarketTrades(trades) => {
                stats.trade_messages += 1;
                stats.trades += trades
                    .events
                    .iter()
                    .filter(|event| event.kind == EventKind::Update)
                    .map(|event| event.trades.len() as u64)
                    .sum::<u64>();
                continue;
            }
            Message::Heartbeats(_) | Message::Subscriptions(_) => continue,
        };
        stats.l2_messages += 1;

        for event in &data.events {
            if event.kind == EventKind::Snapshot {
                book.clear();
                translator.reset();
                stats.snapshots += 1;
            }
            updates.clear();
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
                updates.push(update);
            }
            translator.apply(&updates);
        }

        // Checked after the whole message, since a message can briefly cross mid-way
        if book.is_crossed() {
            stats.crossed_after += 1;
        }
        if !tops_match(&book, &translator) {
            stats.top_mismatches += 1;
        }
    }

    let elapsed = started.elapsed().as_secs_f64();
    report(&path, &stats, &book, &translator, elapsed);
    Ok(())
}

/// Returns whether the engine's best bid and ask (price and size) equal Coinbase's.
fn tops_match(book: &L2Book, translator: &L2Translator) -> bool {
    let engine_book = translator.engine().book();
    let engine_top = |side: Side, best: Option<Price>| {
        best.map(|price| (price, engine_book.quantity_at(side, price)))
    };
    book.best_bid() == engine_top(Side::Buy, engine_book.best_bid())
        && book.best_ask() == engine_top(Side::Sell, engine_book.best_ask())
}

/// Compares every level of both books. Returns how many levels differ.
fn full_mismatches(book: &L2Book, translator: &L2Translator) -> usize {
    let engine_book = translator.engine().book();
    let mut mismatches = 0;
    for side in [Side::Buy, Side::Sell] {
        mismatches += book
            .levels(side)
            .filter(|(price, quantity)| engine_book.quantity_at(side, *price) != *quantity)
            .count();
        // Levels the engine has but Coinbase doesn't
        mismatches += engine_book
            .level_count(side)
            .saturating_sub(book.levels(side).count());
    }
    mismatches
}

fn report(path: &str, stats: &Stats, book: &L2Book, translator: &L2Translator, elapsed_secs: f64) {
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
        "  trades:          {} in {} messages",
        stats.trades, stats.trade_messages
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
    println!(
        "    engine vs Coinbase, best bid/ask: {}",
        stats.top_mismatches
    );
    println!(
        "    engine vs Coinbase, all levels:   {}",
        full_mismatches(book, translator)
    );
    println!(
        "    unexpected engine events:         {}",
        translator.unexpected_events()
    );
    println!();
    println!(
        "  engine: {} commands sent, {} orders resting",
        translator.commands_sent(),
        translator.engine().book().order_count()
    );

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
