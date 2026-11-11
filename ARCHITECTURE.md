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
| Live server (dashboard backend) | Python (FastAPI) | `dashboard/server` | 5 |
| Dashboard (web page) | TypeScript/React (Vite) | `dashboard/web` | 5 |
| Schwab connector (stocks)       | Python (schwab-py) | `connectors/schwab` | 6 |

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

`L2Translator` (`crates/replay/src/translate.rs`) keeps a line of synthetic orders at every price in the engine so each level's total always equals Coinbase's. A level that grows gets a new order for the difference at the back of the line. A level that shrinks loses orders from the back; a partly removed order is shrunk with `Command::Reduce`, which keeps its place in line, as size decreases do on real exchanges. (An earlier version cancelled and re-added the remainder, which silently moved a bot waiting behind it forward: an optimistic bias.) Within a message, shrinking levels are applied before growing ones, so a price that flips from ask to bid never makes the engine trade.
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
`lobster.Backtest` (in `crates/py/src/backtest.rs`) exposes the backtest the same way. The strategy loop is plain Python (`while not bt.market_finished(): bt.run_until(...)`), but each call does a lot of work in Rust (one `run_until` can replay thousands of market events), so the loop crosses the language boundary once per decision, not once per market event.
_Why:_ all logic stays in Rust where it's tested; the bindings can't drift from the engine's behavior. Plain strings and ints keep Python strategy code simple, and the integer-only rule (decision #1) holds across the language boundary.

### 13. The backtest: the bot shares the engine with the replayed market

`Backtest` (`crates/replay/src/backtest.rs`) replays a recording through `L2Translator` while a bot sends orders into the same engine. Bot orders use ids from `FIRST_BOT_ID` (2^62) up; the translator never cancels them and doesn't count them toward Coinbase's totals. A bot order fills only when a replayed trade reaches it in line, when new Coinbase liquidity crosses it, or when it crosses the book itself. Every bot command arrives `latency_ns` after it's sent (default 10 ms, about the measured feed lag), so a cancel can lose the race to a fill and be rejected, like on a real exchange. Fills pay maker or taker fees in basis points, rounded against the bot. Money is exact: `cash` is in tick-lots ($0.01 × 1 satoshi = $1e-10); PnL is cash plus position valued at the mid.
_Why:_ sharing one engine means queue position, partial fills and price-time priority all come from the same tested matching code as everything else. Latency and fees are the two things that most often make a paper strategy look better than it is.
_Known bias:_ the replayed market can't react to the bot (if the bot takes liquidity, Coinbase's next update may "put it back"), so the bot should trade small relative to the book.

### 14. Strategies are compared one change at a time, with PnL broken down

`strategies/harness.py` runs any strategy (an object with `name` and `on_tick(bt)`) on a fresh backtest of the same recording and computes the same metrics for each: fills, position, max drawdown, markouts at 1/5/30 s, and PnL split into **spread capture** (fill price vs. the mid at the moment of the fill), **inventory** (what the position did afterwards) and **fees**. `strategies/strats.py` holds the strategies, each changing one thing from the previous one (v1 naive → v1b keep queue place → v2 inventory skew); `strategies/compare.py` prints them side by side.
_Why:_ changing one thing at a time tells you what each idea is actually worth. The PnL breakdown separates "earned the spread" from "got lucky or unlucky on price", which a single PnL number hides.

### 15. Walk-forward evaluation: tune on earlier data, test on later data

`strategies/evaluate.py` cuts every recording that has trades into equal windows, puts the earlier ~60% in a training set and the later ~40% in a test set (time order, never shuffled), grid-searches each strategy family's parameters on training only, then runs the chosen settings untouched on the test set. It reports both, with $/hour, Sharpe, spread capture, fees and windows won.
_Why:_ choosing parameters on the same data you report results on is the most common way backtests lie. The gap between train and test is a direct measure of overfitting, and only the test numbers count. Sharpe is annualized over 365 days because crypto trades around the clock; with hours rather than months of data, it's a rough guide.

### 16. The dashboard server is Python, streaming one tick per market second

`dashboard/server/app.py` (FastAPI) runs a `Session` (`session.py`: a `lobster.Backtest` plus a strategy from `strategies/strats.py`) and streams a JSON snapshot per second of market time over a websocket: the top 12 levels per side, the bot's orders with their queue position, new fills, position, PnL and fees. The page (`dashboard/web`, Vite + React + TypeScript, charts in plain SVG) can pause, resume and change speed mid-replay. Prices stay integer ticks on the wire; time goes as seconds since the start and order ids as strings, because nanosecond timestamps and ids from 2^62 exceed what a JavaScript number holds exactly (2^53).
_Why:_ the strategies are Python, so the server that runs them is too (the original plan was a Rust axum server, which could only have replayed the market). The replay logic is kept out of the web layer so it can be tested on its own.

### 17. One strategy, three brokers: backtest, paper, live (Phase 6, in progress)

Strategies already talk only to the `Backtest` methods (`submit_limit`, `cancel`, `open_orders`, `position`, `best_bid`, ...). Phase 6 turns that into a `Broker` interface with three implementations, so the same strategy code runs everywhere:

- `SimBroker`: recorded data replayed through our engine (today's `Backtest`).
- `PaperBroker`: live Schwab data fed into our engine with simulated fills. schwab-py's docs mention no paper-trading or sandbox environment, so our engine is the paper environment.
- `SchwabBroker`: live data and real orders through schwab-py, behind dry-run-by-default, size/position/daily-loss/order-rate limits, a kill switch, regular-hours-only trading, and reconciliation against Schwab's order statuses.

Running paper and live side by side measures how well the simulator predicts real fills.
_First step:_ `connectors/schwab/record.py` records Schwab's level one quotes, NASDAQ/NYSE book snapshots and 1-minute bars (record raw, parse later); `inspect_recording.py` shows their real shape before any parser is written. Credentials live in a gitignored `.env`; the token file lives outside the repo.
_Known differences from Coinbase:_ Schwab's book streams cover single exchanges, not the whole US market; schwab-py documents no trade (time and sales) stream, so trades must be inferred from level one changes; retail orders are routed by the broker, so live queue position isn't visible; latency is a retail API's (hundreds of ms).

### 18. One settings module; nothing assumes the laptop

Every path, key, port and address is read in `config/settings.py`, from environment variables or the gitignored `.env` (environment wins). Everything else calls `get_settings()`.
_Why:_ the app will move from the Mac to an always-on server. If paths and ports are settings, that move is a new `.env`, not a code hunt. Relative paths count from the repo root, so a script behaves the same from any folder.
_Safety built in:_ secrets are wrapped in `Secret`, which prints as stars, so a stray print or log can't leak a key. The host must be local (`127.0.0.1`) until the app has a login (build step 8); anything else is refused at startup.
_Why plain dataclasses, not pydantic-settings:_ no new dependency, and the loader takes the environment as an argument, so tests pass a dict instead of patching the real environment.

### 19. The web app shell: six pages, a tiny router, scoped styles

`dashboard/web` is now the Lobster app: a top bar (logo, Home, Portfolio, Charts, Ideas, Backtests, Forward tests, connection status) above whichever page the URL names. Unbuilt pages are one quiet line saying which step brings them.
_Why our own router:_ six fixed pages need only "read the path, change the path". `router.tsx` does that in about 40 lines with React's `useSyncExternalStore` (the standard way to read state that lives outside React, here the URL). If pages ever need nested routes or loaders, swap in React Router.
_Why the status asks the server:_ the browser never sees keys or tokens. `/api/status` answers yes/no questions (keys set? token saved?), so the top bar can say what's wrong without anything secret crossing the wire.
_Styles:_ theme colors are CSS variables in `styles.css`, taken from the mockup. The old replay's styles are nested under `.replay` (native CSS nesting), so its global `button` look can't leak into new pages.

### 20. SQLite with numbered SQL migrations

The app's own data (settings changed in the app, and later test results, ideas, notes and chart drawings) lives in one SQLite file at LOBSTER_DB_PATH, outside the repo. Tables are created and changed only by numbered files in `dashboard/server/db/migrations/` (`0001_app_settings.sql`, ...), applied in order at server start.
_Why SQLite:_ one user, one server. It's a single file with no database server to run, it's built into Python, and it moves to the always-on server by copying one file. If many processes ever write at once, Postgres is the upgrade.
_Why plain SQL migrations, not an ORM with Alembic:_ the schema stays readable SQL, there's nothing to install, and the runner is about 60 lines Karston can read. Each migration runs in a transaction (SQLite can undo table changes too), so a broken one leaves no half-made tables.
_Guards:_ each applied migration's checksum is stored, so editing one after the fact is refused (add a new one instead). A database with migrations the code doesn't know (made by newer code) is refused too.
_Threads:_ connections are opened with `check_same_thread=False`. FastAPI runs a plain-function dependency (our per-request connection) on a worker thread and an `async` route on the event loop's thread, so a request's connection can cross threads; that's safe because each request has its own connection and uses it one step at a time. Without it, `/api/history` (the first `async` route with a database) failed with "SQLite objects created in a thread can only be used in that same thread". `test_routes.py` now calls routes through FastAPI itself, which the direct unit tests couldn't catch.
_Settings:_ WAL mode (reading doesn't wait for a write in progress), foreign keys on (SQLite's default is off), and autocommit with an explicit `transaction()` helper, so what's saved together is visible in the code.

### 21. The Schwab account service

`dashboard/server/account/` is the only place the server talks to Schwab about your account. Routes: `/api/account` (balances and positions per account), `/api/orders` (open orders, plus the last day's), and `/api/status` (connected, login expiry, masked account numbers).
_The server never logs in:_ it only loads the saved token (`client_from_token_file`). Logging in opens a browser and needs you, so it's a separate script, `connectors/schwab/login.py`. On an always-on server, a browser popping up would hang forever.
_Login expiry:_ schwab-py's token file records when you last logged in (`creation_timestamp`; refreshes don't change it). Schwab ends a login after 7 days, so the server computes the end time and the top bar warns a day ahead. A 401 from Schwab also counts as "log in again".
_Money in integer cents:_ Schwab sends dollars as floats. `cents()` converts at the boundary via `Decimal(str(x))`, the same no-floats rule as the engine. Share quantities stay as sent (fractional shares exist) because they're only displayed.
_Account names:_ LOBSTER_ACCOUNT_NAMES (`4428=Roth IRA,*=Schwab Cash`) gives each account a display name by its last four digits, `*` meaning any other account. The service attaches the name; pages show names, and the digits only appear under Account details. The mapping lives in the gitignored `.env`.
_Account numbers:_ masked to `…1234` inside the parser, so the full number never reaches a record, a log or the browser. Error messages pass on only the HTTP status, because raw HTTP errors can contain URLs with account hashes.
_Caching:_ one client, one Schwab call at a time (an `asyncio.Lock`), answers reused for 10 seconds. Schwab allows about 120 requests a minute; the page and the status dot together stay far below that.
_Checked against reality:_ `connectors/schwab/account_fields.py` lists the field names Schwab really sends (no values). The first run showed that cash accounts have no `buyingPower` (the parser falls back to `cashAvailableForTrading`), that some positions have no `description`, and that times look like `2026-11-10T15:00:00+0000`. The test fixtures now mirror that shape.

### 22. The server adds up the portfolio; the browser only formats

`/api/portfolio` returns every account added together: total value, today's change, the value at yesterday's close, cash, and holdings merged by symbol (`account/portfolio.py`). The page turns cents into text and divides for percentages, nothing more.
_Why:_ Home, Portfolio and later alerts must agree on "today's change". If each page summed it, they'd drift. It also follows the rule that the server does the work.
_Today's change_ is the sum of each position's `currentDayProfitLoss` from Schwab; the percent is that change over yesterday's value (total minus change). SPY's change comes from `/api/quotes`, cached like everything else. It uses Schwab's `regular` block (the 8:30 to 3:00 Central session) rather than `quote`, which after hours includes extended-hours trades; that's the "SPY was up X% today" number.
_No chart yet:_ Schwab doesn't keep your portfolio's value over time, so the Home chart needs the server to record it first (roadmap, step 2).

### 23. Live updates: one Schwab stream, pushed to pages

The server keeps one Schwab level one quote stream open for every stock you hold plus SPY (`dashboard/server/live/`). Pages connect to `/ws/live` and receive repriced accounts, the portfolio and SPY whenever something changed, at most once a second. Polling stays as the fallback while the websocket is down.
_Why the server streams, not the browser:_ one connection serves every open page, the keys never reach the browser, and it keeps running with no tab open (needed later for forward tests and alerts).
_Repricing on top of Schwab's numbers:_ a position moves by shares x (live price - snapshot price). Schwab's own day change and open P&L already handle shares bought today and similar details, so we only add the price move rather than recomputing from scratch. Accounts are reloaded every minute, which also catches trades and cash changes; options aren't in the equity stream and keep their snapshot value.
_Coalescing:_ the stream can send many updates a second. Prices are merged as they arrive and published on a 1-second tick, and each page's queue holds only the newest message, so a slow page can never fall behind.
_Changing symbols:_ when the held symbols change, the feed reconnects with the new list instead of re-subscribing on the open connection, because schwab-py says subscription calls aren't safe to run alongside message handling.
_Regular session first:_ like the REST quotes, `REGULAR_MARKET_LAST_PRICE` is preferred over `LAST_PRICE`, so after-hours trades don't move the day's numbers.

### 24. Charts: Schwab candles, Lightweight Charts, one wrapper file

`/api/candles?symbol=&timeframe=` returns candles in cents from Schwab's price history (`dashboard/server/market/`). The Charts page draws them with TradingView's open-source Lightweight Charts (v5).
_Timeframes:_ Schwab has 1, 5, 15 and 30-minute, daily and weekly candles. 1h and 4h are built on the server from 30-minute candles, with periods starting at the 9:30 AM Eastern open (9:30, 10:30, ...; 4h splits the day at 1:30), as TradingView does for US stocks. Only the regular session is requested. How far back each loads: 1m 10 days (Schwab keeps about 48), 5m 60 days, 15m 120 days, 1h and 4h 270 days (about 9 months), D 10 years, W 20 years.
_One wrapper file:_ every library call lives in `pages/charts/lightweight.ts`. The drawing tools (2d) will sit on top of it, and if the library changes, only that file does.
_Time zones:_ candles keep their real UTC timestamps; only the labels are formatted in a time zone (`tickMarkFormatter` and `localization.timeFormatter`). Intraday labels use your time zone, daily and weekly use the UTC date (right for both Coinbase's 00:00 UTC days and Schwab's midnight-Central days). The first version shifted the timestamps themselves, which crashed on hourly crypto: when daylight saving ended on Nov 1, 1:00 to 2:00 AM happened twice, two candles landed on the same time, and the chart threw. Stocks never trade then, so only crypto hit it.
_Error boundary:_ a page that throws now shows the error in its place (`components/ErrorBoundary.tsx`) instead of blanking the whole app.
_URL as state:_ symbol and timeframe live in the query string, so Home's holding links, bookmarks and the back button all work.
_Attribution:_ the library's license asks for TradingView attribution; its small logo stays on (the default).

### 25. Crypto candles from Coinbase, and per-series decimals

A symbol with a dash (BTC-USD, ETH-USDC) is a Coinbase product; anything else is a Schwab stock. Coinbase candles come from its public Exchange API (`market/coinbase.py`), no login needed.
_Paging:_ Coinbase returns at most 300 candles per request, newest first, so the server walks backwards page by page (4 to 8 pages per timeframe) and stops when a page comes back empty. Answers are cached for 30 seconds, since Coinbase asks that history not be polled often.
_Timeframes:_ Coinbase serves 1m, 5m, 15m, 1h, 6h and 1D. 4h is built from 1h and weekly from daily. Crypto trades around the clock, so periods align to UTC (4h at 00:00, 04:00, ...), and weeks start on Monday.
_Decimals per series, not cents:_ SHIB-USD moves in $0.00000001 steps, so cents would flatten it to $0.00. Candle prices are still whole numbers (never floats), but in units of 10^-decimals, and each series says its `decimals`: Coinbase's `quote_increment` for crypto (2 for BTC-USD, 8 for SHIB-USD), 2 for stocks, 4 for stocks under $1. The chart's price axis and legend show that many places. Account money stays in cents.
_Volume is a float:_ crypto volume is fractional (0.5 BTC). It's only displayed, never used for money.

### 26. The live last candle

While a chart is open, every trade of its symbol reaches the page over `/ws/ticks?symbol=` and updates the newest candle, or starts the next one.
_Sources:_ a `TickHub` counts which symbols pages are watching and tells the sources. Stocks join the existing Schwab quote stream (no second connection). A stock tick is sent when the price changes or `TOTAL_VOLUME` grows, with the volume difference as its size, and only during the regular session, to match the regular-session candles. Crypto comes from Coinbase Advanced Trade's public `market_trades` feed, the one the Rust recorder uses, on one connection for all watched pairs. Its first message is a snapshot of recent trades that the history already contains, so only `update` trades count.
_Which bar a trade belongs to:_ the page doesn't redo the server's alignment rules (9:30 for stock hours, UTC for crypto, the trading day for D). A trade inside the last bar's period updates it; otherwise the new bar starts a whole number of periods after the last one, which keeps whatever grid the server chose. One known gap: across a daylight-saving change, a new daily stock bar can start an hour off until the page reloads.
_Ticks keep every trade:_ unlike account updates (newest only), a tick queue keeps up to 1,000 ticks, since each trade can set the high or low.

### 27. Drawings: an SVG layer anchored to time and price

Drawings are saved per symbol in the database (`drawings` table, `dashboard/server/drawings/`) and shown on every timeframe of that symbol.
_Anchored to (time, price), not pixels:_ a point is a moment and a price, so it stays put through zoom, scroll and timeframe changes. The chart lays bars out by index ("logical" position), with no space for nights or weekends, so `coords.ts` turns a time into a fractional bar index: between two bars it sits proportionally, past either end it continues at one bar per period. The reverse uses the same rule, so dragging round-trips exactly.
_An SVG layer over the canvas, not chart primitives:_ Lightweight Charts can host custom drawings ("series primitives"), but an SVG overlay gives ordinary DOM pointer events, hit areas and CSS, which keeps the code short and readable. It covers only the plotting area (the time scale's width, the height minus the time axis), ignores the pointer except on drawings so the chart still pans, and takes every click while a drawing tool is on. While a drawing is dragged, the chart's own panning is switched off. The chart's container has `z-index: 0` so it forms its own stacking context: the library sets z-indexes on its canvases, and without it the chart's top canvas covered the drawing layer.
_Our own bar-to-pixel math:_ the library's `logicalToCoordinate` returns 0 for fractional positions and `coordinateToLogical` rounds to whole bars (found in its source, not its docs). Drawing points sit between bars, so the wrapper measures the mapping at bars 0 and 1 (it's a straight line) and converts fractional positions itself; checked against the library in a headless browser.
_Following the chart:_ there's no single event for "the price axis was dragged", so the layer reads the viewport every animation frame and re-renders only when it changed. The mappings are straight lines, so two sample points per axis plus the size describe them completely.
_Saving:_ the page makes each drawing's id (a UUID), shows changes at once and saves in the background (`PUT` creates or moves, `DELETE` removes). Pydantic refuses badly shaped drawings (a trend line with one point, an unknown kind).

### 28. More drawing tools, snap, lock, undo and redo

Kinds: horizontal line (1 point), trend line, ray, rectangle and Fibonacci retracement (2 each), parallel channel (3: two for the line, one for the distance) and text (1). Measure is a tool too, but its box isn't saved.
_One click loop for every tool:_ each tool declares how many clicks it takes (`CLICKS`). A draft collects points, with its last point following the pointer, and the drawing is saved when the last click lands. New tools only need a count and a shape component.
_Geometry in pure functions:_ `geometry.ts` (where a ray leaves the chart, the channel's parallel line, Fibonacci prices, the measure readout) has no React or chart in it, so it's checked with plain Node. Shapes do their maths in pixels, which is safe because the price axis is linear.
_Fibonacci convention:_ level 1 at the first click (start of the move), 0 at the second (its end), as TradingView does, so 0.618 reads as "61.8% of the move given back".
_Snap:_ a strong magnet. A point jumps to the nearest bar and to whichever of its open, high, low or close is closest on screen.
_Lock:_ stored per drawing (a new `locked` column). A locked drawing can still be selected, so it can be unlocked, but it can't be dragged or deleted.
_Undo and redo:_ every save or delete records the drawing before and after. Undo writes back "before" (or deletes, if it didn't exist) and redo writes back "after", both through the same save path, so the server always matches. A drag is one change (saved on release). Text is saved once it has words, so a cancelled text box leaves no history. History is per symbol, for the current visit.
_Migrating a live table:_ `0003` adds `text` and `locked` with defaults, so drawings saved before it still load; a test upgrades a 0002 database that already holds a drawing.

### 29. Recording the portfolio's value

Schwab has no "account value over time" API, so the server records it: every minute, a `HistoryRecorder` writes the live feed's latest totals (the whole portfolio as `all`, plus each account by its last four digits) to `value_history`. History therefore starts when recording started, and has gaps while the server is off (for now, while the laptop sleeps; the move to an always-on server in step 8 fixes that).
_Only fresh numbers:_ the feed reloads accounts every minute and publishes right after, so a latest message older than three minutes means Schwab is unreachable, and nothing is written. A gap is more honest than a flat line of stale values.
_Thinning by range:_ 1D shows every minute of the latest session (9:30 to 4:00 Eastern, rolling back over nights and weekends), 1W one point per 15 minutes, 1M per hour, 1Y and All per day. One SQL query picks the last value in each bucket (SQLite's `GROUP BY` with `MAX(time)` takes the other columns from that row).
_Compared with SPY:_ for the whole portfolio, SPY's candles are scaled to start at the same value ("what if this money had been in SPY"). For 1D the start is yesterday's close, the last value recorded before the open (or the live previous close on the first day), so the chart agrees with "today's change"; for longer ranges it's the first value in the range. Single accounts show no SPY line, per the design's "minimal noise".
_Size:_ about 1,440 rows per account per day, a few million rows a year; small for SQLite, and `WITHOUT ROWID` keeps each account's rows stored in time order.
_The chart:_ a calm Lightweight Charts area line with no axes or grid, the dashed base line kept on screen through an `autoscaleInfoProvider`, and a hover readout. On 1D the live value extends the line to the current moment between recordings.

### 30. The Log in button

When Schwab needs a login (none yet, expired, or ending within a day), the Connections panel, Home and Portfolio show a "Log in to Schwab" button. It asks the server to run `connectors/schwab/login.py --no-prompt`, which opens Schwab's page in the browser; you sign in there, the token is saved, and the account service picks up the new token on its next request (it already watches for a new login).
_A separate process:_ schwab-py's login starts a temporary HTTPS server on 127.0.0.1:8182 to catch Schwab's redirect. Running the existing script as a child process keeps that, and anything that goes wrong in it, out of the app server, and the button and the terminal use the same code.
_No key in the logs:_ schwab-py prints the full login URL, which contains the API key. The script's output is discarded; it ends by writing one `LOBSTER-LOGIN: ok | timeout | error <Type>` line, the only thing the server reads.
_Only from our page:_ `POST /api/schwab/login` requires a JSON request. Browsers won't let another website send one to this server without a CORS check, which it never approves, so a page elsewhere can't trigger a login.
_Limits:_ one login at a time, stopped after 5.5 minutes. It assumes the browser and the server are the same machine; the move to a server (step 8) needs a callback URL on the server instead (roadmap).

## Known limitations (to address later)

- **Coinbase's public feed is "Level 2":** it shows total size at each price, not individual orders. So we can't know exactly where our order sits in a queue, and we'll have to _estimate_ queue position. This becomes a modeling problem in Phase 4.
- **Duplicate ids are only checked against resting orders:** an id from an order that already filled or was cancelled can be reused. Tracking every id ever seen would grow memory forever; we'll revisit if the replayer needs stricter checks.
- **Trade reconciliation is ~79% by volume:** see decision #11. A smarter matcher (e.g. re-classifying a shrink at the touch as a fill when a matching trade follows within a few ms) could raise it.
- **No latency yet:** in reality, our orders reach the exchange a few milliseconds late. We'll add simulated latency so the backtest isn't unrealistically optimistic.
