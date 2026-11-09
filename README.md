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
```

## Benchmarks

_Coming soon._

## License

MIT
