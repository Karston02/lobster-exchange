# Dashboard

A web page that replays a recording with a strategy trading in it, live:
order book ladder (with the bot's orders and queue position), price chart
with fills, position, PnL, and recent fills.

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

Open the URL it prints (usually http://localhost:5173), pick a recording and a
strategy, and press Start. Speed is market seconds per real second.

## Layout

- `server/session.py`: one replay (backtest + strategy), advanced a tick at a time. No networking.
- `server/app.py`: FastAPI routes: `/api/recordings`, `/api/strategies`, and the `/ws/replay` websocket.
- `web/src/useReplay.ts`: the websocket connection, turned into React state.
- `web/src/types.ts`: the message formats, mirroring `session.py`.
- `web/src/components/`: `Controls`, `OrderBook`, `LineChart` (plain SVG, no chart library), `Stats`, `Fills`.

Prices travel as integer ticks and sizes as integer lots, the same as in the
engine. Two values don't: time is sent as seconds since the start, and order
ids as strings, because nanosecond timestamps and bot ids (from 2^62) are
too large for a JavaScript number to hold exactly.
