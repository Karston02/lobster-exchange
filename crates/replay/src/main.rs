//! Replays a recording: rebuilds Coinbase's order book, feeds the same
//! changes and trades into our matching engine, and checks that they agree.
//!
//! ```text
//! cargo run --release -p lobster-replay -- <recording.jsonl> [--trade-lead-ms N]
//! ```
//!
//! Book changes and trades are put back in exchange-time order before being
//! applied (see `timeline.rs`). `--trade-lead-ms` moves trades earlier in that
//! order, for experimenting; the default is 0.

use std::time::Instant;

use lobster_engine::{Price, Quantity, Side};
use lobster_replay::l2book::L2Book;
use lobster_replay::recording::{ReadProblems, Recording, read_recording};
use lobster_replay::timeline::{Step, Timed, TradePrint, merge};
use lobster_replay::translate::L2Translator;

/// What happened during the replay.
#[derive(Debug, Default)]
struct ReplayStats {
    level_steps: u64,
    level_sets: u64,
    level_removals: u64,
    trades: u64,
    trade_volume: u64,
    /// Trades the engine had no matching resting quantity for
    unfilled_trades: u64,
    unfilled_volume: u64,
    /// Trades stamped before the snapshot, which the book doesn't know about yet
    skipped_early_trades: u64,
    /// Level steps after which Coinbase's book was crossed (bid >= ask)
    crossed: u64,
    /// Level steps after which the engine's best bid or ask differed from Coinbase's
    top_mismatches: u64,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let Some(path) = args.first() else {
        eprintln!("usage: lobster-replay <recording.jsonl> [--trade-lead-ms N]");
        std::process::exit(2);
    };
    let trade_lead_ms: u64 = match args.iter().position(|a| a == "--trade-lead-ms") {
        Some(i) => args
            .get(i + 1)
            .ok_or("--trade-lead-ms needs a number")?
            .parse()?,
        None => 0,
    };

    let started = Instant::now();
    let mut problems = ReadProblems::default();
    let recording = read_recording(path, &mut problems)?;
    let read_secs = started.elapsed().as_secs_f64();

    let started = Instant::now();
    let mut book = L2Book::new();
    let mut translator = L2Translator::new();
    let stats = replay(&recording, trade_lead_ms, &mut book, &mut translator);
    let replay_secs = started.elapsed().as_secs_f64();

    report(
        path,
        &recording,
        &problems,
        &stats,
        &book,
        &translator,
        (read_secs, replay_secs),
        trade_lead_ms,
    );
    Ok(())
}

/// Applies the snapshot, then every book change and trade in exchange-time order.
fn replay(
    recording: &Recording,
    trade_lead_ms: u64,
    book: &mut L2Book,
    translator: &mut L2Translator,
) -> ReplayStats {
    let mut stats = ReplayStats::default();

    for update in &recording.snapshot {
        book.apply(*update);
    }
    translator.apply(&recording.snapshot);

    // Trades from before the snapshot already happened in the book we started with
    let trades: Vec<Timed<TradePrint>> = recording
        .trades
        .iter()
        .filter(|trade| trade.exchange_ns >= recording.snapshot_ns)
        .copied()
        .collect();
    stats.skipped_early_trades = (recording.trades.len() - trades.len()) as u64;

    for step in merge(&recording.levels, &trades, trade_lead_ms * 1_000_000) {
        match step.item {
            Step::Levels(updates) => {
                stats.level_steps += 1;
                for update in &updates {
                    if update.quantity.0 == 0 {
                        stats.level_removals += 1;
                    } else {
                        stats.level_sets += 1;
                    }
                    book.apply(*update);
                }
                translator.apply(&updates);

                if book.is_crossed() {
                    stats.crossed += 1;
                }
                if !tops_match(book, translator) {
                    stats.top_mismatches += 1;
                }
            }
            Step::Trade(trade) => {
                stats.trades += 1;
                stats.trade_volume += trade.quantity.0;
                let unfilled = translator.apply_trade(trade);
                if unfilled.0 > 0 {
                    stats.unfilled_trades += 1;
                    stats.unfilled_volume += unfilled.0;
                }
            }
        }
    }
    stats
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

/// `part` as a percentage of `whole`.
fn percent(part: u64, whole: u64) -> f64 {
    part as f64 * 100.0 / whole.max(1) as f64
}

#[allow(clippy::too_many_arguments)]
fn report(
    path: &str,
    recording: &Recording,
    problems: &ReadProblems,
    stats: &ReplayStats,
    book: &L2Book,
    translator: &L2Translator,
    (read_secs, replay_secs): (f64, f64),
    trade_lead_ms: u64,
) {
    let recorded_secs = match (recording.first_recv_ns, recording.last_recv_ns) {
        (Some(first), Some(last)) => (last - first) as f64 / 1e9,
        _ => 0.0,
    };
    let changes = stats.level_sets + stats.level_removals;

    println!("{path}");
    println!(
        "  recorded:      {recorded_secs:.0} s, {} lines",
        recording.lines
    );
    println!("  read in:       {read_secs:.2} s");
    println!(
        "  replayed in:   {replay_secs:.2} s ({:.0}x real time)",
        recorded_secs / replay_secs.max(1e-9)
    );
    println!("  snapshot:      {} levels", recording.snapshot.len());
    println!(
        "  level changes: {changes} ({} set, {} removed) in {} steps, {:.0}/s",
        stats.level_sets,
        stats.level_removals,
        stats.level_steps,
        changes as f64 / recorded_secs.max(1e-9)
    );
    println!(
        "  trades:        {} ({:.8} BTC), trade lead {trade_lead_ms} ms",
        stats.trades,
        stats.trade_volume as f64 / 1e8
    );
    println!();
    println!("  checks (should be 0):");
    println!("    unparsed lines:      {}", problems.unparsed_lines);
    println!("    bad numbers:         {}", problems.bad_numbers);
    println!("    bad timestamps:      {}", problems.bad_times);
    println!("    sequence gaps:       {}", problems.sequence_gaps);
    println!("    extra snapshots:     {}", problems.extra_snapshots);
    println!("    crossed book:        {}", stats.crossed);
    println!(
        "    engine vs Coinbase, all levels at the end: {}",
        full_mismatches(book, translator)
    );
    println!(
        "    unexpected engine events:                  {}",
        translator.unexpected_events()
    );
    println!();
    println!("  model quality (lower is better, see ARCHITECTURE.md #11):");
    println!(
        "    engine vs Coinbase, best bid/ask: {:.2}% of steps ({} of {})",
        percent(stats.top_mismatches, stats.level_steps),
        stats.top_mismatches,
        stats.level_steps
    );
    println!(
        "    trade volume the engine couldn't fill: {:.2}% ({} trades)",
        percent(stats.unfilled_volume, stats.trade_volume),
        stats.unfilled_trades
    );
    println!(
        "    trades before the snapshot (skipped): {}",
        stats.skipped_early_trades
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
