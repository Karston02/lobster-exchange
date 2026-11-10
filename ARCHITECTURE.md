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

## Known limitations (to address later)

- **Coinbase's public feed is "Level 2":** it shows total size at each price, not individual orders. So we can't know exactly where our order sits in a queue, and we'll have to _estimate_ queue position. This becomes a modeling problem in Phase 4.
- **Duplicate ids are only checked against resting orders:** an id from an order that already filled or was cancelled can be reused. Tracking every id ever seen would grow memory forever; we'll revisit if the replayer needs stricter checks.
- **No latency yet:** in reality, our orders reach the exchange a few milliseconds late. We'll add simulated latency so the backtest isn't unrealistically optimistic.
