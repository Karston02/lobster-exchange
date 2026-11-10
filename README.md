# lobster-exchange 🦞

A limit order book (**LOB**) exchange built from scratch in Rust, plus a market-making bot that trades against replayed real market data.

## What it is

- **Matching engine** (Rust): a price-time priority order book that matches buy and sell orders, like a real exchange.
- **Market data replay:** records the live Coinbase order book and replays it through the engine.
- **Market-making bot** (Python via PyO3): quotes on both sides of the book and tries to earn the spread without getting run over.
- **Live dashboard** (React): the order book, the bot's quotes, PnL, and inventory in real time.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and the reasoning behind it.

## Running it

Requires [Rust](https://rustup.rs).

```sh
cargo test     # run the test suite
cargo build    # compile
cargo bench    # run the benchmarks
```

## Benchmarks

```sh
cargo bench                      # run the benchmarks (HTML report in target/criterion/report/index.html)
cargo bench -- --baseline v1     # compare against the saved v1 baseline
```

Measured with [criterion](https://github.com/bheisler/criterion.rs) on a MacBook Pro (Apple Silicon), engine v1 (`BTreeMap` + `VecDeque` + `HashMap`):

| Benchmark | What it measures | Result |
|---|---|---|
| `mixed_workload/100000` | Commands per second on generated order flow (70% limits, 20% cancels, 10% market orders) | **11.8M commands/sec** (~85 ns each) |
| `latency/add_then_cancel/10000` | Add a resting order, then cancel it, on a book of 10,000 orders | **76 ns** |
| `latency/add_then_match/10000` | Add a resting sell, then a market buy that fills it, on a book of 10,000 orders | **143 ns** |

## License

MIT
