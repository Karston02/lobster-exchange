# Architecture

lobster-exchange is a simulated exchange plus a market-making bot. Real market data gets recorded, replayed through our own matching engine, and a strategy trades against it. A dashboard shows everything live.

## The big picture

```
 Coinbase websocket ──► Recorder ──► data/*.bin (recorded order book updates)
                                          │
                                          ▼
                                      Replayer ──► Commands ──┐
                                                              ▼
 Strategy (Python) ──► Commands ──────────────────────► Matching Engine (Rust)
        ▲                                                     │
        └──────────────────── Events (fills, book updates) ◄──┘
                                                              │
                                                              ▼
                                              Server ──► Dashboard (React)
```

## Components

| Component                       | Language         | Crate / folder  | Phase |
| ------------------------------- | ---------------- | --------------- | ----- |
| Matching engine                 | Rust             | `crates/engine` | 2     |
| Market data recorder           | Rust             | `crates/recorder` | 3     |
| Market data replayer            | Rust             | `crates/replay` | 3     |
| Python bindings                 | Rust (PyO3)      | `crates/py`     | 4     |
| Strategies + backtests          | Python           | `strategies/`   | 4     |
| Live server                     | Rust (axum)      | `crates/server` | 5     |
| Dashboard                       | TypeScript/React | `dashboard/`    | 5     |

## The engine's contract

The engine is a pure state machine: **commands go in, events come out.** `Engine::process(command)` is the only way to change its state. The types live in `crates/engine/src/messages.rs`.

**Commands**

- `NewLimit { id, side, price, quantity }`: trade at `price` or better; any remainder rests.
- `NewMarket { id, side, quantity }`: trade now at any price; any remainder is cancelled.
- `Cancel { id }`: remove a resting order.

**Events**, in the order they happen:

- `Accepted { id }`: a new order passed validation. Always first, before its trades.
- `Trade(Trade)`: two orders matched, at the maker's price.
- `Cancelled { id, remaining, reason }`: an order left the book unfilled. `reason` is `Requested` (a `Cancel` command) or `NoLiquidity` (a market order ran out of opposite orders).
- `Rejected { id, reason }`: the command was refused and nothing changed. `reason` is `ZeroQuantity`, `ZeroPrice`, `DuplicateOrderId` or `UnknownOrderId`.

It does no I/O, no networking, no clocks, and no randomness. Everything else in the system talks to it through this one interface.

## Code layout (`crates/engine`)

| File              | Responsibility                                                              | Depends on                  |
| ----------------- | --------------------------------------------------------------------------- | --------------------------- |
| `src/types.rs`    | Domain vocabulary: `Side`, `Price`, `Quantity`, `OrderId`, `Order`, `Trade` | nothing                     |
| `src/book.rs`     | `OrderBook`: storing orders and matching them                               | `types`                     |
| `src/messages.rs` | The contract: `Command`, `Event`, reasons                                   | `types`                     |
| `src/engine.rs`   | `Engine`: validation, rejections, turning book results into events          | `book`, `messages`, `types` |
| `src/lib.rs`      | Declares modules and re-exports the public API                              | everything                  |
| `tests/engine.rs` | Integration tests that use only the public API                              | the crate                   |

Dependencies only point "down" this table, never in a cycle. The modules themselves are private (`mod book;`, not `pub mod book;`), so the re-exports in `lib.rs` are the only public paths: users write `lobster_engine::Engine`, and internal file names can change without breaking anyone. Unit tests live next to the code they test (`#[cfg(test)] mod tests`); integration tests live in `tests/`.

## Key design decisions

Each entry says what we chose and why. These are the questions an interviewer is likely to ask.

### 1. Prices and quantities are integers, never floats

Prices are stored as an integer number of **ticks** (the smallest allowed price increment), e.g. `$64,231.57` → `6_423_157` cents. Quantities are integer **lots**.
_Why:_ floating-point math is inexact (`0.1 + 0.2 != 0.3`). Two orders at the "same" price could fail to match, and books could drift. Every real exchange uses integers.

### 2. Price-time priority

Better price fills first; at the same price, the order that arrived first fills first (FIFO).
_Why:_ it's the most common rule on real exchanges (Nasdaq, CME futures mostly, Coinbase) and it's what makes queue position matter for a market maker.

### 3. Book structure: `BTreeMap<Price, VecDeque<Order>>` per side, plus a `HashMap<OrderId, …>` index

- `BTreeMap` keeps price levels **sorted**, so the best bid/ask is always at one end: O(log n) to find a level.
- `VecDeque` (a double-ended queue) at each level gives FIFO order: push new orders on the back, fill from the front.
- The `HashMap` lets `Cancel(order_id)` find an order directly instead of scanning the whole book. It maps each resting order's id to its `(side, price)`, so cancel jumps to the right level and only scans that one queue. True O(1) cancel (no scan at all) needs an arena + linked list per level, which is a Phase 2 optimization.

_Why:_ simple, correct, and fast enough to start. It's v1 on purpose: once we have benchmarks, we'll replace parts with faster structures (arena/slab allocation, array-indexed price levels) and measure the speedup. That before/after comparison is a resume bullet.

### 4. Single-threaded and deterministic

One thread processes commands in order. Same inputs → same outputs, every time.
_Why:_ real matching engines (LMAX, most exchanges) do this. Locks would slow things down, and determinism means we can replay a recorded day and get identical results, which makes testing and debugging much easier.

### 5. Engine in Rust, strategies in Python

_Why:_ the engine needs raw speed and correctness, which Rust gives. Strategies need fast iteration and data tools (numpy, pandas), which Python gives. PyO3 connects them with little overhead.

### 6. The book is mechanism, the engine is policy

`OrderBook` only knows _how_ to store and match orders, and assumes its inputs are valid. `Engine` decides _what is allowed_ (rejections) and reports results as events. The book's mutating methods are `pub(crate)`, so outside code can only change state through `Engine::process`; it can still read the book through `engine.book()`.
_Why:_ each part has one job and can be tested on its own, the matching loop stays small and fast, and there is exactly one door into the engine, which keeps the deterministic replay guarantee easy to uphold.

### 7. A custom hasher for the order index

The `HashMap<OrderId, (Side, Price)>` index uses `IdHasher` (`src/id_hash.rs`), a multiply-and-rotate hash in the style of FxHash, instead of Rust's default SipHash.
_Why:_ profiling showed the index's hashing was the biggest single engine cost. SipHash protects against hash-flooding attacks (an attacker choosing keys that collide), which matters for maps keyed by untrusted input. Our ids come from our own replayer and bot, so we trade that protection for speed. If the engine ever accepted ids from untrusted clients, we'd assign our own internal ids instead.

### 8. The recorder saves raw messages, one file per connection

`lobster-recorder` writes every Coinbase message untouched, wrapped as `{"recv_ns": <our receive time>, "msg": <original>}`, one per line. Each connection gets its own file, and a missed `sequence_num` ends the connection on purpose.
_Why:_ "record raw, parse later": if the parser has a bug, we fix it and re-parse instead of losing the data. Each new connection starts with a full book snapshot, so every file can be replayed on its own, and a file is never silently corrupted by a gap. Our receive time is kept for measuring feed latency later.

### 9. Parsing Coinbase's decimal strings by hand, into the engine's integer types

`lobster-replay` converts `"73232.08"` into `Price(7_323_208)` (cents) and `"0.3404195"` into `Quantity(34_041_950)` (satoshis) with `parse_fixed`, digit by digit. The number of decimal places comes from a per-product `ProductSpec` (BTC-USD: 2 for prices, 8 for sizes).
_Why:_ going through `f64` would reintroduce the rounding errors decision #1 avoids. Parsing digits directly is exact, rejects anything more precise than the product allows, and catches overflow. The level2 book (`L2Book`, price → total size) is kept separate from the engine's per-order `OrderBook`, because level2 data has no individual orders.

### 10. Level2 → engine: synthetic orders, cancels taken from the back

`L2Translator` (`crates/replay/src/translate.rs`) keeps a line of synthetic orders at every price in the engine so each level's total always equals Coinbase's. A level that grows gets a new order for the difference at the back of the line. A level that shrinks loses orders from the back (a partly removed order is cancelled and its remainder re-added, which keeps it last). Within a message, shrinking levels are applied before growing ones, so a price that flips from ask to bid never makes the engine trade.
_Why:_ new orders really do join the back. Cancels can come from anywhere, and assuming "from the back" is pessimistic for a bot waiting in line: orders ahead of it never disappear, so backtests won't overstate how fast it gets filled. Trades (from `market_trades`) will consume from the front once the bot is in the loop (Phase 4); the assumption can become a setting (back / front / proportional) to compare.
_Checked:_ on a real 15,882-message recording, the engine's book matched Coinbase's at the top after every message and at every level at the end, with zero unexpected trades or rejections (361,872 commands, 0.24 s).

### 11. Trades replay in exchange-time order, as immediate-or-cancel orders

Coinbase sends book changes as they happen but batches trades every 250 ms, so a fill's book change usually arrives before the trade that caused it. The replayer reads the whole file, then sorts book changes (`event_time`) and trades (`time`) by Coinbase's timestamps (`timeline.rs`). Each trade becomes an immediate-or-cancel order on the taker's side at the trade's price, which fills the front of the line and never rests. Coinbase's `side` on a trade is the maker's side; the data confirms it (1,732 of 1,736 trades had a matching bid/offer change within 250 ms).
_Why:_ processed in arrival order, a fill would be counted twice (once as a cancel from the back, once as a trade). In exchange-time order the trade comes first, takes the front of the line, and the following book change finds the level already at the right total.
_Measured_ on a 2,224-trade recording: a fill's book change is stamped a median 16 ms after its trade (93% after, some up to ~30 ms before). Moving trades earlier (`--trade-lead-ms`) made things worse at every value tried, so the default is 0:

| Trade lead | Trade volume the engine couldn't fill | Steps with top-of-book mismatch |
|---|---|---|
| 0 ms | 20.8% | 0.38% |
| 10 ms | 21.6% | 1.74% |
| 50 ms | 21.7% | 9.89% |
| 250 ms | 32.1% | 31.0% |

The ~21% unfilled volume breaks down as: the engine's level already drained by earlier trades or cancels (~12%), levels smaller than the trade (~4%), prices that never appeared in the level2 feed at all (~5%, liquidity added and taken between updates), and better prices resting (~0.3%). The book itself stays exact: 0 level mismatches at the end. For a bot, unfilled trade volume means missed fills, which errs on the pessimistic side.

### 12. Python bindings are a thin layer over the engine

`crates/py` (`import lobster`) wraps `Engine` with PyO3 0.30. Each method converts Python values into engine types, calls the engine, and converts the events back. Sides are the strings `"buy"`/`"sell"`; prices and quantities stay integers. Events are one flat `Event` class with a `kind` field. `crates/py/lobster.pyi` describes the module for editors. The crate is a workspace member but not a default member, because it's built by `maturin` rather than `cargo build`.
_Why:_ all logic stays in Rust where it's tested; the bindings can't drift from the engine's behavior. Plain strings and ints keep Python strategy code simple, and the integer-only rule (decision #1) holds across the language boundary.

## Known limitations (to address later)

- **Coinbase's public feed is "Level 2":** it shows total size at each price, not individual orders. So we can't know exactly where our order sits in a queue, and we'll have to _estimate_ queue position. This becomes a modeling problem in Phase 4.
- **Duplicate ids are only checked against resting orders:** an id from an order that already filled or was cancelled can be reused. Tracking every id ever seen would grow memory forever; we'll revisit if the replayer needs stricter checks.
- **Trade reconciliation is ~79% by volume:** see decision #11. A smarter matcher (e.g. re-classifying a shrink at the touch as a fill when a matching trade follows within a few ms) could raise it.
- **No latency yet:** in reality, our orders reach the exchange a few milliseconds late. We'll add simulated latency so the backtest isn't unrealistically optimistic.
