//! Benchmarks for the matching engine, run with `cargo bench`.
//!
//! Two kinds of measurement:
//! - Throughput: how many commands per second the engine handles on a
//!   realistic mixed workload.
//! - Latency: how long single operations take on a book that already holds
//!   many orders.

use std::hint::black_box;

use criterion::{BatchSize, BenchmarkId, Criterion, Throughput, criterion_group, criterion_main};
use lobster_engine::{Command, Engine, OrderId, Price, Quantity, Side};

/// The price everything is generated around, in ticks.
const MID: u64 = 10_000;

/// Ids used by the latency benchmarks, far away from the pre-filled orders' ids.
const BENCH_ID: OrderId = OrderId(u64::MAX / 2);

/// A tiny deterministic random number generator (xorshift64*).
///
/// Same seed, same numbers: every run benchmarks exactly the same workload,
/// so results are comparable between runs and between versions of the code.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    /// Returns a number in `0..n`.
    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }
}

/// Generates `count` commands that look roughly like real order flow:
/// mostly limit orders near the mid price (some resting, some crossing),
/// some cancels of earlier orders, and a few market orders.
fn workload(count: usize, seed: u64) -> Vec<Command> {
    let mut rng = Rng(seed);
    let mut commands = Vec::with_capacity(count);

    for i in 0..count as u64 {
        let id = OrderId(i + 1);
        let side = if rng.below(2) == 0 {
            Side::Buy
        } else {
            Side::Sell
        };
        let roll = rng.below(100);

        let command = if roll < 70 {
            // Offset from the mid: positive rests on the book, negative crosses it
            let offset = rng.below(25) as i64 - 5;
            let price = match side {
                Side::Buy => MID as i64 - offset,
                Side::Sell => MID as i64 + offset,
            };
            Command::NewLimit {
                id,
                side,
                price: Price(price as u64),
                quantity: Quantity(1 + rng.below(10)),
            }
        } else if roll < 90 && i > 0 {
            // Cancel a random earlier order (it may already be filled; that's realistic too)
            Command::Cancel {
                id: OrderId(1 + rng.below(i)),
            }
        } else {
            Command::NewMarket {
                id,
                side,
                quantity: Quantity(1 + rng.below(5)),
            }
        };
        commands.push(command);
    }
    commands
}

/// Builds an engine whose book holds `levels` price levels on each side,
/// with `per_level` orders at each one. Bids sit below the mid, asks above,
/// so nothing crosses.
fn filled_engine(levels: u64, per_level: u64) -> Engine {
    let mut engine = Engine::new();
    let mut next_id = 1;
    for level in 0..levels {
        for _ in 0..per_level {
            for (side, price) in [(Side::Buy, MID - 1 - level), (Side::Sell, MID + 1 + level)] {
                engine.process(Command::NewLimit {
                    id: OrderId(next_id),
                    side,
                    price: Price(price),
                    quantity: Quantity(10),
                });
                next_id += 1;
            }
        }
    }
    engine
}

/// Commands per second on the mixed workload, starting from an empty book.
fn throughput(c: &mut Criterion) {
    let mut group = c.benchmark_group("mixed_workload");
    for count in [10_000, 100_000] {
        let commands = workload(count, 42);
        group.throughput(Throughput::Elements(count as u64));
        group.bench_with_input(
            BenchmarkId::from_parameter(count),
            &commands,
            |b, commands| {
                // A fresh engine per run; creating it is excluded from the timing
                b.iter_batched(
                    Engine::new,
                    |mut engine| {
                        for command in commands {
                            black_box(engine.process(*command));
                        }
                        engine
                    },
                    BatchSize::SmallInput,
                );
            },
        );
    }
    group.finish();
}

/// Single-operation latency on books of different sizes.
///
/// Each measurement is a "round trip" that leaves the book exactly as it
/// found it, so the same pre-filled book can be reused for every iteration.
fn latency(c: &mut Criterion) {
    let mut group = c.benchmark_group("latency");
    for (levels, per_level) in [(10, 5), (100, 50)] {
        let mut engine = filled_engine(levels, per_level);
        let resting = levels * per_level * 2;

        // Add an order that rests at the back of the best bid's line, then cancel it
        group.bench_function(BenchmarkId::new("add_then_cancel", resting), |b| {
            b.iter(|| {
                black_box(engine.process(Command::NewLimit {
                    id: BENCH_ID,
                    side: Side::Buy,
                    price: Price(MID - 1),
                    quantity: Quantity(10),
                }));
                black_box(engine.process(Command::Cancel { id: BENCH_ID }));
            });
        });

        // Add a sell just inside the spread, then a market buy that trades with it
        group.bench_function(BenchmarkId::new("add_then_match", resting), |b| {
            b.iter(|| {
                black_box(engine.process(Command::NewLimit {
                    id: BENCH_ID,
                    side: Side::Sell,
                    price: Price(MID),
                    quantity: Quantity(10),
                }));
                black_box(engine.process(Command::NewMarket {
                    id: OrderId(BENCH_ID.0 + 1),
                    side: Side::Buy,
                    quantity: Quantity(10),
                }));
            });
        });
    }
    group.finish();
}

criterion_group!(benches, throughput, latency);
criterion_main!(benches);
