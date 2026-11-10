"""The dashboard's web server: lists recordings and strategies, and streams a
replay over a websocket.

Run from the repo root with the venv active (uv pip install fastapi "uvicorn[standard]"):

    python dashboard/server/app.py

Then start the web page (see dashboard/README.md). The server listens on
LOBSTER_HOST:LOBSTER_PORT (http://127.0.0.1:8000 by default).

The websocket at /ws/replay takes its settings as query parameters, then
sends a "hello" message, one "tick" message per second of market time, and
a "done" message at the end. The page can send {"type": "pause"},
{"type": "resume"} or {"type": "speed", "value": 25} at any time.
"""

import asyncio
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# The settings package lives at the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import get_settings  # noqa: E402
from session import STRATEGIES, Session, list_recordings  # noqa: E402

app = FastAPI(title="lobster-exchange dashboard")

MAX_SPEED = 500.0


@app.get("/api/recordings")
def recordings() -> list[dict]:
    return list_recordings()


@app.get("/api/strategies")
def strategies() -> list[dict]:
    return [{"key": key, "name": name, "description": text} for key, (name, text, _) in STRATEGIES.items()]


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
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
