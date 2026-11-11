"""The Lobster server: your Schwab account, connection status, and the order
book replay.

Run from the repo root with the venv active:

    uv pip install fastapi "uvicorn[standard]" schwab-py
    python dashboard/server/app.py

Then start the web page (see dashboard/README.md). It listens on
LOBSTER_HOST:LOBSTER_PORT (http://127.0.0.1:8000 by default).

Routes: /api/status, /api/account, /api/portfolio, /api/quotes,
/api/orders (Schwab, see account/), /api/candles (charts, see market/),
/api/drawings (chart drawings, see drawings/),
/ws/live (live account updates, see live/), /ws/ticks (live trades for
a chart), /api/recordings,
/api/strategies and /ws/replay.

The websocket at /ws/replay takes its settings as query parameters, then
sends a "hello" message, one "tick" message per second of market time, and
a "done" message at the end. The page can send {"type": "pause"},
{"type": "resume"} or {"type": "speed", "value": 25} at any time.
"""

import asyncio
import logging
import re
import sys
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect

# The settings package lives at the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from account import SchwabService, SchwabUnavailable  # noqa: E402
from config import get_settings  # noqa: E402
from db import connect, open_database  # noqa: E402
from drawings import Drawing, delete_drawing, list_drawings, save_drawing  # noqa: E402
from live import CoinbaseTrades, LiveFeed, TickHub  # noqa: E402
from market import TIMEFRAMES, CoinbaseMarket, SourceUnavailable, UnknownSymbol, is_crypto  # noqa: E402
from session import STRATEGIES, Session, list_recordings  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup: bring the database up to date and get the Schwab service ready.
    Shutdown: close the Schwab connection."""
    settings = get_settings()
    open_database(settings.db_path).close()
    app.state.schwab = SchwabService(settings.schwab, account_names=settings.account_names)
    app.state.coinbase = CoinbaseMarket()
    app.state.ticks = TickHub()
    app.state.live = LiveFeed(app.state.schwab, on_tick=app.state.ticks.publish)
    app.state.coinbase_trades = CoinbaseTrades(on_tick=app.state.ticks.publish)

    def follow(symbols: frozenset[str]) -> None:
        """Charts changed what they watch: stocks join the Schwab stream, crypto the Coinbase feed."""
        app.state.live.set_extra_symbols({s for s in symbols if not is_crypto(s)})
        app.state.coinbase_trades.set_products({s for s in symbols if is_crypto(s)})

    app.state.ticks.on_change(follow)
    app.state.live.start()  # runs on the server whether or not a page is open
    yield
    await app.state.coinbase_trades.stop()
    await app.state.live.stop()
    await app.state.coinbase.close()
    await app.state.schwab.close()


app = FastAPI(title="lobster", lifespan=lifespan)

MAX_SPEED = 500.0


def schwab() -> SchwabService:
    return app.state.schwab


@app.get("/api/status")
async def status() -> dict:
    """Facts for the top bar's connection status. Never keys, tokens or full account numbers."""
    return {"schwab": await schwab().status()}


@app.get("/api/account")
async def account() -> dict:
    """Every linked account: balances and positions, money in integer cents."""
    try:
        accounts = await schwab().accounts()
    except SchwabUnavailable as error:
        raise HTTPException(503, {"reason": error.reason, "message": error.message}) from None
    fetched = schwab().accounts_fetched_at()
    return {"accounts": [asdict(a) for a in accounts], "fetched_at": fetched.isoformat() if fetched else None}


@app.get("/api/portfolio")
async def portfolio() -> dict:
    """All accounts added together: total, today's change, cash, holdings by symbol."""
    try:
        return asdict(await schwab().portfolio())
    except SchwabUnavailable as error:
        raise HTTPException(503, {"reason": error.reason, "message": error.message}) from None


SYMBOL = re.compile(r"^[A-Z0-9.$/-]{1,15}$")
MAX_SYMBOLS = 20


@app.get("/api/quotes")
async def quotes(symbols: str) -> dict:
    """Today's price and change, e.g. /api/quotes?symbols=SPY,QQQ"""
    wanted = sorted({s.strip().upper() for s in symbols.split(",") if s.strip()})
    if not wanted or len(wanted) > MAX_SYMBOLS or not all(SYMBOL.match(s) for s in wanted):
        raise HTTPException(400, f"symbols: 1 to {MAX_SYMBOLS} tickers, comma separated")
    try:
        found = await schwab().quotes(wanted)
    except SchwabUnavailable as error:
        raise HTTPException(503, {"reason": error.reason, "message": error.message}) from None
    return {"quotes": {symbol: asdict(quote) for symbol, quote in found.items()}}


@app.get("/api/candles")
async def candles(symbol: str, timeframe: str = "D") -> dict:
    """Price history for a chart: stocks from Schwab, crypto (BTC-USD, ...) from Coinbase.
    e.g. /api/candles?symbol=AAPL&timeframe=1h. Prices are whole numbers in units of
    10^-decimals; `decimals` is in the response."""
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol):
        raise HTTPException(400, "symbol: a ticker like AAPL, or a coin pair like BTC-USD")
    if timeframe not in TIMEFRAMES:
        raise HTTPException(400, f"timeframe: one of {', '.join(TIMEFRAMES)}")
    try:
        if is_crypto(symbol):
            series = await app.state.coinbase.candles(symbol, timeframe)
        else:
            series = await schwab().candles(symbol, timeframe)
    except SchwabUnavailable as error:
        raise HTTPException(503, {"reason": error.reason, "message": error.message}) from None
    except UnknownSymbol as error:
        raise HTTPException(404, str(error)) from None
    except SourceUnavailable as error:
        raise HTTPException(503, str(error)) from None
    return asdict(series)


def database() -> Iterator:
    """One short-lived connection per request (SQLite's usual pattern for web servers)."""
    conn = connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


@app.get("/api/drawings")
def drawings(symbol: str, conn=Depends(database)) -> dict:
    """The drawings on one symbol's chart (shared by every timeframe)."""
    return {"drawings": [d.model_dump() for d in list_drawings(conn, symbol.strip().upper())]}


@app.put("/api/drawings/{drawing_id}")
def put_drawing(drawing_id: str, drawing: Drawing, conn=Depends(database)) -> dict:
    """Creates or moves a drawing. FastAPI checks the body against `Drawing` (422 if it's wrong)."""
    if drawing.id != drawing_id:
        raise HTTPException(400, "the id in the path and the body differ")
    save_drawing(conn, drawing)
    return {"saved": drawing_id}


@app.delete("/api/drawings/{drawing_id}")
def remove_drawing(drawing_id: str, conn=Depends(database)) -> dict:
    if not delete_drawing(conn, drawing_id):
        raise HTTPException(404, "no such drawing")
    return {"deleted": drawing_id}


@app.get("/api/orders")
async def orders() -> dict:
    """Orders still waiting to fill, plus any entered in the last day."""
    try:
        recent = await schwab().orders()
    except SchwabUnavailable as error:
        raise HTTPException(503, {"reason": error.reason, "message": error.message}) from None
    return {"orders": [asdict(o) for o in recent]}


@app.get("/api/recordings")
def recordings() -> list[dict]:
    return list_recordings()


@app.get("/api/strategies")
def strategies() -> list[dict]:
    return [{"key": key, "name": name, "description": text} for key, (name, text, _) in STRATEGIES.items()]


@app.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    """Pushes repriced accounts, the portfolio and SPY whenever they change (at most once a second)."""
    await ws.accept()
    feed: LiveFeed = app.state.live
    queue = feed.subscribe()
    try:
        if feed.latest():
            await ws.send_json(feed.latest())
        await send_until_closed(ws, queue, lambda message: message)
    finally:
        feed.unsubscribe(queue)


@app.websocket("/ws/ticks")
async def ticks(ws: WebSocket, symbol: str) -> None:
    """Each trade of one symbol, for the chart's live last candle: {symbol, time, price, volume}."""
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol):
        await ws.close(code=1008)
        return
    await ws.accept()
    hub: TickHub = app.state.ticks
    queue = hub.subscribe(symbol)
    try:
        await send_until_closed(ws, queue, asdict)
    finally:
        hub.unsubscribe(symbol, queue)


async def send_until_closed(ws: WebSocket, queue: asyncio.Queue, encode) -> None:
    """Sends everything that arrives on `queue` until the page goes away."""

    async def page_left() -> None:
        # Pages never send anything; this returns when one closes. Without it, a closed
        # page would only be noticed at the next message, which can be hours later.
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass

    gone = asyncio.create_task(page_left())
    try:
        while True:
            item = asyncio.create_task(queue.get())
            await asyncio.wait({item, gone}, return_when=asyncio.FIRST_COMPLETED)
            if gone.done():
                item.cancel()
                return
            await ws.send_json(encode(item.result()))
    except (WebSocketDisconnect, RuntimeError):
        pass  # closed mid-send
    finally:
        gone.cancel()


@app.websocket("/ws/replay")
async def replay(
    ws: WebSocket,
    recording: str,
    strategy: str = "v2",
    speed: float = 10.0,
    size_btc: float = 0.001,
    latency_ms: float = 10.0,
    maker_fee_bps: int = 0,
    taker_fee_bps: int = 0,
) -> None:
    await ws.accept()
    try:
        # Loading a recording takes a moment; do it off the event loop
        session = await asyncio.to_thread(
            Session, recording, strategy, size_btc, latency_ms, maker_fee_bps, taker_fee_bps
        )
    except (ValueError, OSError) as error:
        await ws.send_json({"type": "error", "message": str(error)})
        await ws.close()
        return

    # Ticks per real second; the page can change it, or pause, while it runs
    state = {"speed": min(max(speed, 0.1), MAX_SPEED), "paused": False}

    async def listen() -> None:
        try:
            while True:
                message = await ws.receive_json()
                if message.get("type") == "pause":
                    state["paused"] = True
                elif message.get("type") == "resume":
                    state["paused"] = False
                elif message.get("type") == "speed":
                    state["speed"] = min(max(float(message["value"]), 0.1), MAX_SPEED)
        except (WebSocketDisconnect, RuntimeError, KeyError, ValueError):
            pass

    listener = asyncio.create_task(listen())
    try:
        await ws.send_json(session.hello())
        while True:
            if state["paused"]:
                await asyncio.sleep(0.05)
                continue
            snapshot = session.tick()
            if snapshot is None:
                await ws.send_json(session.done())
                break
            await ws.send_json(snapshot)
            await asyncio.sleep(1 / state["speed"])
    except WebSocketDisconnect:
        pass
    finally:
        listener.cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
