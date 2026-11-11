"""The real FastAPI app, called the way the browser calls it. Run: pytest dashboard/server

Unit tests call our code directly; these go through FastAPI too (dependencies on
worker threads, request parsing, JSON), which is where /api/history once failed.
Schwab and the live feed are replaced by fakes, and the app's startup (which
connects to Schwab) isn't run.

Needs FastAPI, httpx and the `lobster` module, all in the venv on the Mac; in
environments without them these tests are skipped.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("lobster")

from fastapi.testclient import TestClient  # noqa: E402

import app as server  # noqa: E402
from account import SchwabUnavailable  # noqa: E402
from db import connect, open_database  # noqa: E402
from history.store import record_values  # noqa: E402


class FakeLive:
    def latest(self):
        return None


class FakeSchwab:
    async def candles(self, symbol, timeframe):
        raise SchwabUnavailable("error", "no Schwab in tests")


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "lobster.db"
    open_database(db).close()
    record_values(conn := connect(db), 1_794_000_000, {"all": 500_00})
    conn.close()

    def database():  # the same shape as app.database: a generator FastAPI runs on a worker thread
        c = connect(db)
        try:
            yield c
        finally:
            c.close()

    server.app.dependency_overrides[server.database] = database
    server.app.state.live = FakeLive()
    server.app.state.schwab = FakeSchwab()
    yield TestClient(server.app)  # no `with`: the startup that connects to Schwab doesn't run
    server.app.dependency_overrides.clear()


def test_history_route(client):
    response = client.get("/api/history?range=All&account=all")

    assert response.status_code == 200
    assert [p["value_cents"] for p in response.json()["points"]] == [500_00]


def test_history_route_refuses_bad_input(client):
    assert client.get("/api/history?range=2D").status_code == 400
    assert client.get("/api/history?account=12345").status_code == 400


def test_drawings_routes(client):
    drawing = {"id": "d1", "symbol": "AAPL", "kind": "hline", "points": [{"time": 1, "price": 190.0}]}

    assert client.put("/api/drawings/d1", json=drawing).status_code == 200
    assert [d["id"] for d in client.get("/api/drawings?symbol=AAPL").json()["drawings"]] == ["d1"]
    assert client.put("/api/drawings/d1", json={**drawing, "points": []}).status_code == 422  # wrong shape
    assert client.delete("/api/drawings/d1").status_code == 200
    assert client.delete("/api/drawings/d1").status_code == 404
