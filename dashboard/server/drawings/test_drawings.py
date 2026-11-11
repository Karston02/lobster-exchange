"""Tests for saving drawings. Run: pytest dashboard/server/drawings"""

import pytest
from pydantic import ValidationError

from db import open_database
from drawings import Drawing, delete_drawing, list_drawings, save_drawing


@pytest.fixture
def conn(tmp_path):
    connection = open_database(tmp_path / "lobster.db")  # runs the real migrations, 0002 included
    yield connection
    connection.close()


def trend(id="t1", symbol="AAPL", prices=(190.0, 195.5)):
    return Drawing(id=id, symbol=symbol, kind="trend", points=[{"time": 1000, "price": prices[0]}, {"time": 2000, "price": prices[1]}])


def test_drawings_are_saved_per_symbol(conn):
    save_drawing(conn, trend("a", "AAPL"))
    save_drawing(conn, Drawing(id="b", symbol="AAPL", kind="hline", points=[{"time": 1500, "price": 192.0}]))
    save_drawing(conn, trend("c", "BTC-USD"))

    assert [d.id for d in list_drawings(conn, "AAPL")] == ["a", "b"]
    assert [d.id for d in list_drawings(conn, "BTC-USD")] == ["c"]
    assert list_drawings(conn, "MSFT") == []


def test_saving_again_moves_the_points(conn):
    save_drawing(conn, trend())
    save_drawing(conn, trend(prices=(180.0, 185.0)))

    (moved,) = list_drawings(conn, "AAPL")
    assert [p.price for p in moved.points] == [180.0, 185.0]


def test_delete(conn):
    save_drawing(conn, trend())

    assert delete_drawing(conn, "t1") is True
    assert delete_drawing(conn, "t1") is False
    assert list_drawings(conn, "AAPL") == []


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "trend", "points": [{"time": 1, "price": 1.0}]},  # a trend line needs two points
        {"kind": "hline", "points": []},
        {"kind": "circle", "points": [{"time": 1, "price": 1.0}]},
        {"kind": "channel", "points": [{"time": 1, "price": 1.0}, {"time": 2, "price": 2.0}]},  # needs three
        {"kind": "text", "points": [{"time": 1, "price": 1.0}], "text": "x" * 201},
    ],
)
def test_badly_shaped_drawings_are_refused(bad):
    with pytest.raises(ValidationError):
        Drawing(id="x", symbol="AAPL", **bad)


def test_text_and_lock_are_saved_and_updated(conn):
    note = Drawing(id="n", symbol="AAPL", kind="text", points=[{"time": 1, "price": 190.0}], text="earnings")
    save_drawing(conn, note)
    save_drawing(conn, note.model_copy(update={"text": "earnings beat", "locked": True}))

    (saved,) = list_drawings(conn, "AAPL")
    assert saved.text == "earnings beat" and saved.locked is True


def test_every_kind_round_trips(conn):
    from drawings.store import POINTS

    for i, (kind, count) in enumerate(POINTS.items()):
        points = [{"time": 1000 + j, "price": 100.0 + j} for j in range(count)]
        save_drawing(conn, Drawing(id=f"d{i}", symbol="SPY", kind=kind, points=points))

    assert [d.kind for d in list_drawings(conn, "SPY")] == list(POINTS)


def test_drawings_saved_before_the_new_columns_still_load(tmp_path):
    """A database at migration 0002, with a drawing in it, then upgraded to 0003."""
    from db import connect, migrate
    from db.migrate import MIGRATIONS

    old = tmp_path / "old"
    old.mkdir()
    for name in ("0001_app_settings.sql", "0002_drawings.sql"):
        (old / name).write_text((MIGRATIONS / name).read_text())
    conn = connect(tmp_path / "lobster.db")
    migrate(conn, old)
    conn.execute(
        "INSERT INTO drawings (id, symbol, kind, points, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("old", "AAPL", "hline", '[{"time": 1, "price": 5.0}]', "2026-11-10", "2026-11-10"),
    )

    assert "0003_drawing_text_and_lock.sql" in migrate(conn)  # plus any later migrations
    (drawing,) = list_drawings(conn, "AAPL")
    assert drawing.text == "" and drawing.locked is False
