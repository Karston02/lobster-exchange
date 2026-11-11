"""Reading and writing recorded values."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Value:
    time: int  # Unix seconds
    value_cents: int


def record_values(conn: sqlite3.Connection, time: int, totals: dict[str, int]) -> None:
    """Saves each account's total at `time` (recording the same minute twice keeps the later one)."""
    conn.executemany(
        "INSERT OR REPLACE INTO value_history (account, time, total_cents) VALUES (?, ?, ?)",
        [(account, time, cents) for account, cents in totals.items()],
    )


def values_between(conn: sqlite3.Connection, account: str, start: int, end: int, bucket_s: int) -> list[Value]:
    """Recorded values from `start` to `end`, thinned to the last value in each `bucket_s` period.

    SQLite has a handy rule: in a GROUP BY with MAX(), the other columns come from the
    row that had the maximum, so this picks each bucket's latest row in one query."""
    rows = conn.execute(
        """SELECT MAX(time) AS time, total_cents FROM value_history
           WHERE account = ? AND time >= ? AND time <= ?
           GROUP BY time / ? ORDER BY time""",
        (account, start, end, bucket_s),
    ).fetchall()
    return [Value(r["time"], r["total_cents"]) for r in rows]


def last_value_before(conn: sqlite3.Connection, account: str, time: int) -> Value | None:
    row = conn.execute(
        "SELECT time, total_cents FROM value_history WHERE account = ? AND time < ? ORDER BY time DESC LIMIT 1",
        (account, time),
    ).fetchone()
    return Value(row["time"], row["total_cents"]) if row else None


def first_time(conn: sqlite3.Connection, account: str) -> int | None:
    row = conn.execute("SELECT MIN(time) AS t FROM value_history WHERE account = ?", (account,)).fetchone()
    return row["t"]
