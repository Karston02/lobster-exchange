# Lobster web app

The app shell (top bar, six pages, connection status) and, under Backtests for
now, the original order book replay: a recording with a strategy trading in it.

```
recording ──► Python server (FastAPI + lobster.Backtest) ──websocket──► React page
```

## Run it

Two terminals, both from the repo root.

**1. The server** (venv active):

```sh
uv pip install fastapi "uvicorn[standard]"
maturin develop --release -m crates/py/Cargo.toml   # if the Rust code changed
python dashboard/server/app.py
```

**2. The page:**

```sh
cd dashboard/web
npm install        # first time only
npm run dev
```

Open the URL it prints (usually http://localhost:5173). For the replay, go to
Backtests, pick a recording and a strategy, and press Start. Speed is market seconds per real second.

## Layout

- `server/app.py`: FastAPI routes: `/api/status` (connection facts for the top bar), `/api/account`, `/api/portfolio`, `/api/quotes?symbols=SPY` and `/api/orders` (Schwab), `/api/recordings`, `/api/strategies`, and the `/ws/replay` websocket. Host and port come from the settings (`config/`).
- `server/account/`: your Schwab account on the server. `login_runner.py` runs `connectors/schwab/login.py` for the Log in button (`POST /api/schwab/login`), reading only its result line. `service.py` (one client from the saved token, 10-second cache, clear `SchwabUnavailable` reasons), `parse.py` (Schwab JSON to records, money in integer cents, account numbers masked to the last four), `token.py` (login age from the token file). Tests use a fake client.
- `server/live/`: live updates. `prices.py` (latest price per symbol from Schwab's level one stream), `revalue.py` (positions move by shares x price move, on top of Schwab's own numbers), `feed.py` (one stream for held symbols + SPY, account refresh every minute, push at most once a second). For charts, `ticks.py` (`TickHub`: who watches which symbol) and `coinbase_trades.py` (Coinbase's public trade feed); stocks a chart watches join the Schwab stream. Route `/ws/ticks?symbol=`. Tests use fake streams.
- `server/market/`: chart candles. `timeframes.py` (which Schwab call each timeframe uses; 1h and 4h are built from 30-minute candles, starting at the 9:30 open), `candles.py` (`Candle`, `combine`), `history.py` (Schwab stocks), `coinbase.py` (crypto, public API, pages backwards 300 candles at a time), `symbols.py` (a dash means crypto). Route `/api/candles?symbol=AAPL&timeframe=1h` returns prices as whole numbers with `decimals`.
- `server/drawings/`: chart drawings per symbol (`store.py`: pydantic-checked `Drawing` with kinds hline, trend, ray, rect, fib, channel and text, plus `text` and `locked`; list, upsert, delete). Table from `db/migrations/0002_drawings.sql`, extended by `0003_drawing_text_and_lock.sql`. Routes `GET /api/drawings?symbol=`, `PUT` and `DELETE /api/drawings/{id}`.
- `server/history/`: the portfolio's value over time. `recorder.py` (every minute, from the live feed's latest numbers, for the whole portfolio and each account; skips stale numbers), `store.py` (thinned reads), `ranges.py` (1D is the latest session, 9:30 to 4:00 Eastern; 1W, 1M, 1Y, All), `service.py` (SPY scaled to start at the same value). Table from `db/migrations/0004_value_history.sql`. Route `/api/history?range=1D&account=all`.
- `server/db/`: the SQLite database. `connect`, `transaction`, and `migrate`, which applies the numbered `.sql` files in `db/migrations/` once each, at server start. The file lives at LOBSTER_DB_PATH (`~/.lobster/lobster.db` by default). Tests: `pytest dashboard/server/db`.
- `server/session.py`: one replay (backtest + strategy), advanced a tick at a time. No networking.
- `web/src/App.tsx`: the shell: top bar, then the page the URL names.
- `web/src/router.tsx`: a tiny router (`usePath`, `navigate`, `Link`); `routes.ts` lists the pages.
- `web/src/shell/`: `TopBar`, `ConnectionStatus` (the status dot) and `SettingsPanel`.
- `web/src/pages/charts/`: the Charts page. `lightweight.ts` holds every call into TradingView's Lightweight Charts (v5); `CandleChart`, `Legend`, `Toolbar`, `FullScreenButton`, `useCandles`, `useTicks` (live trades update the last candle via `applyTick` in `bars.ts`). `drawing/`: the SVG drawing layer (`DrawingLayer`; `Shape` picks a component from `shapes/` per kind; `MeasureBox`; `TextEditor`), left toolbar (`DrawingTools`, `icons.tsx`), `useDrawings` (load, save, undo and redo), `coords.ts` (time to bar position and back), `geometry.ts` (rays, channels, Fibonacci levels, measuring), `snap.ts` (magnet to open, high, low or close). Symbol and timeframe live in the URL (`/charts?symbol=AAPL&tf=1h`).
- `web/src/components/valueChart/`: the value chart on Home and Portfolio (`ValueChart` with range buttons and a hover readout; `lightweightValue.ts` holds its library calls). `web/src/chartLabels.ts`: time labels shared with the Charts page.
- `web/src/live/useLive.ts`: the `/ws/live` connection, reconnecting with growing waits. Home and Portfolio use it, and fall back to polling while it's down.
- `web/src/api.ts`, `usePolling.ts`: fetch JSON with explainable errors; re-fetch on a timer, paused while the tab is hidden.
- `web/src/money.ts`: cents to `$1,234.56`, signed changes and percents. `account/types.ts` mirrors the server's account records.
- `web/src/components/Fold.tsx`: the design's collapsed section (`<details>`), whose label says what's inside. `format.ts`: shares, times, Schwab's ALL_CAPS words.
- `web/src/pages/`: one file per page. Pages not built yet are one quiet line in `placeholders.tsx`.
- `web/src/replay/`: the order book replay (`ReplayView`, its components, `useReplay`, message `types`). Its styles are nested under `.replay` so they stay out of the rest of the app.
- `web/src/styles.css`: the theme (colors as CSS variables, Inter for text, JetBrains Mono for numbers via `.num`).

Prices travel as integer ticks and sizes as integer lots, the same as in the
engine. Two values don't: time is sent as seconds since the start, and order
ids as strings, because nanosecond timestamps and bot ids (from 2^62) are
too large for a JavaScript number to hold exactly.
