"""Reading and writing drawings. Pydantic checks every drawing before it's saved.

A drawing's points are positions on the chart (a time and a price), not money,
so prices here are plain numbers in dollars.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# How many points each kind of drawing has
POINTS = {
    "hline": 1,  # horizontal line: a price
    "trend": 2,  # segment between two points
    "ray": 2,  # from the first point through the second, on to the edge
    "rect": 2,  # opposite corners
    "fib": 2,  # Fibonacci retracement: start (level 1) and end (level 0) of a move
    "channel": 3,  # a line through the first two, and a parallel one through the third
    "text": 1,  # where the words sit
}

Kind = Literal["hline", "trend", "ray", "rect", "fib", "channel", "text"]


class Point(BaseModel):
    time: int  # Unix seconds
    price: float


class Drawing(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=15)
    kind: Kind
    points: list[Point]
    text: str = Field(default="", max_length=200)  # only text drawings use it
    locked: bool = False  # can't be moved or deleted until unlocked

    @model_validator(mode="after")
    def _right_number_of_points(self) -> "Drawing":
        if len(self.points) != POINTS[self.kind]:
            raise ValueError(f"a {self.kind} has {POINTS[self.kind]} point(s), not {len(self.points)}")
        return self


def list_drawings(conn: sqlite3.Connection, symbol: str) -> list[Drawing]:
    rows = conn.execute(
        "SELECT id, symbol, kind, points, text, locked FROM drawings WHERE symbol = ? ORDER BY created_at, rowid",
        (symbol,),
    ).fetchall()
    return [
        Drawing(
            id=r["id"],
            symbol=r["symbol"],
            kind=r["kind"],
            points=json.loads(r["points"]),
            text=r["text"],
            locked=bool(r["locked"]),
        )
        for r in rows
    ]


def save_drawing(conn: sqlite3.Connection, drawing: Drawing) -> None:
    """Creates the drawing, or replaces its points, text and lock if it exists (an "upsert")."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    points = json.dumps([p.model_dump() for p in drawing.points])
    conn.execute(
        """INSERT INTO drawings (id, symbol, kind, points, text, locked, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (id) DO UPDATE SET
               points = excluded.points, text = excluded.text,
               locked = excluded.locked, updated_at = excluded.updated_at""",
        (drawing.id, drawing.symbol, drawing.kind, points, drawing.text, int(drawing.locked), now, now),
    )


def delete_drawing(conn: sqlite3.Connection, drawing_id: str) -> bool:
    """True if there was such a drawing."""
    return conn.execute("DELETE FROM drawings WHERE id = ?", (drawing_id,)).rowcount > 0
