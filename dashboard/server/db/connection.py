"""Opening the database, and transactions."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .migrate import migrate


def connect(path: Path) -> sqlite3.Connection:
    """Opens (creating if needed) the database at `path`.

    Autocommit mode: every statement saves on its own unless it runs inside
    `transaction()`. That keeps "what's saved together" explicit.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI may open a request's connection on a worker
    # thread and use it on the event loop's thread. That's safe as long as one
    # connection is never used by two threads at once, and each request has its own.
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # rows act like dicts: row["name"]
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite leaves these off by default
    conn.execute("PRAGMA journal_mode = WAL")  # readers don't wait for a writer
    conn.execute("PRAGMA busy_timeout = 5000")  # wait up to 5 s for a lock instead of failing
    return conn


def open_database(path: Path) -> sqlite3.Connection:
    """Connects and brings the tables up to date. Call once at server start."""
    conn = connect(path)
    migrate(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Everything inside is saved together, or not at all if an error escapes.

        with transaction(conn):
            conn.execute("INSERT ...")
            conn.execute("UPDATE ...")
    """
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
