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

- `server/app.py`: FastAPI routes: `/api/status` (yes/no connection facts for the top bar), `/api/recordings`, `/api/strategies`, and the `/ws/replay` websocket. Host and port come from the settings (`config/`).
- `server/session.py`: one replay (backtest + strategy), advanced a tick at a time. No networking.
- `web/src/App.tsx`: the shell: top bar, then the page the URL names.
- `web/src/router.tsx`: a tiny router (`usePath`, `navigate`, `Link`); `routes.ts` lists the pages.
- `web/src/shell/`: `TopBar`, `ConnectionStatus` (the status dot) and `SettingsPanel`.
- `web/src/pages/`: one file per page. Pages not built yet are one quiet line in `placeholders.tsx`.
- `web/src/replay/`: the order book replay (`ReplayView`, its components, `useReplay`, message `types`). Its styles are nested under `.replay` so they stay out of the rest of the app.
- `web/src/styles.css`: the theme (colors as CSS variables, Inter for text, JetBrains Mono for numbers via `.num`).

Prices travel as integer ticks and sizes as integer lots, the same as in the
engine. Two values don't: time is sent as seconds since the start, and order
ids as strings, because nanosecond timestamps and bot ids (from 2^62) are
too large for a JavaScript number to hold exactly.
