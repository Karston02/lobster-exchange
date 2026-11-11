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
    ],
)
def test_badly_shaped_drawings_are_refused(bad):
    with pytest.raises(ValidationError):
        Drawing(id="x", symbol="AAPL", **bad)
