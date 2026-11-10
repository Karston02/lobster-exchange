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
| Market data recorder + replayer | Rust             | `crates/replay` | 3     |
| Python bindings                 | Rust (PyO3)      | `crates/py`     | 4     |
| Strategies + backtests          | Python           | `strategies/`   | 4     |
| Live server                     | Rust (axum)      | `crates/server` | 5     |
| Dashboard                       | TypeScript/React | `dashboard/`    | 5     |

## The engine's contract

The engine is a pure state machine: **commands go in, events come out.**

- **Commands:** `NewOrder`, `Cancel` (later: `Modify`)
- **Events:** `Accepted`, `Trade`, `Cancelled`, `Rejected`

It does no I/O, no networking, no clocks, and no randomness. Everything else in the system talks to it through this one interface.

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
- The `HashMap` lets `Cancel(order_id)` find an order directly instead of scanning the whole book.

_Why:_ simple, correct, and fast enough to start. It's v1 on purpose: once we have benchmarks, we'll replace parts with faster structures (arena/slab allocation, array-indexed price levels) and measure the speedup. That before/after comparison is a resume bullet.

### 4. Single-threaded and deterministic

One thread processes commands in order. Same inputs → same outputs, every time.
_Why:_ real matching engines (LMAX, most exchanges) do this. Locks would slow things down, and determinism means we can replay a recorded day and get identical results, which makes testing and debugging much easier.

### 5. Engine in Rust, strategies in Python

_Why:_ the engine needs raw speed and correctness, which Rust gives. Strategies need fast iteration and data tools (numpy, pandas), which Python gives. PyO3 connects them with little overhead.

## Known limitations (to address later)

- **Coinbase's public feed is "Level 2":** it shows total size at each price, not individual orders. So we can't know exactly where our order sits in a queue, and we'll have to _estimate_ queue position. This becomes a modeling problem in Phase 4.
- **No latency yet:** in reality, our orders reach the exchange a few milliseconds late. We'll add simulated latency so the backtest isn't unrealistically optimistic.
