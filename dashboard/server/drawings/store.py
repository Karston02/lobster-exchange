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
POINTS = {"hline": 1, "trend": 2}


class Point(BaseModel):
    time: int  # Unix seconds
    price: float


class Drawing(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=15)
    kind: Literal["hline", "trend"]
    points: list[Point]

    @model_validator(mode="after")
    def _right_number_of_points(self) -> "Drawing":
        if len(self.points) != POINTS[self.kind]:
            raise ValueError(f"a {self.kind} has {POINTS[self.kind]} point(s), not {len(self.points)}")
        return self


def list_drawings(conn: sqlite3.Connection, symbol: str) -> list[Drawing]:
    rows = conn.execute(
        "SELECT id, symbol, kind, points FROM drawings WHERE symbol = ? ORDER BY created_at", (symbol,)
    ).fetchall()
    return [Drawing(id=r["id"], symbol=r["symbol"], kind=r["kind"], points=json.loads(r["points"])) for r in rows]


def save_drawing(conn: sqlite3.Connection, drawing: Drawing) -> None:
    """Creates the drawing, or replaces its points if it exists (an "upsert")."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    points = json.dumps([p.model_dump() for p in drawing.points])
    conn.execute(
        """INSERT INTO drawings (id, symbol, kind, points, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT (id) DO UPDATE SET points = excluded.points, updated_at = excluded.updated_at""",
        (drawing.id, drawing.symbol, drawing.kind, points, now, now),
    )


def delete_drawing(conn: sqlite3.Connection, drawing_id: str) -> bool:
    """True if there was such a drawing."""
    return conn.execute("DELETE FROM drawings WHERE id = ?", (drawing_id,)).rowcount > 0
