"""Brings the database's tables up to date by applying migrations in order.

A migration is a SQL file in `migrations/` named `NNNN_what_it_does.sql`. Each
runs once, inside a transaction, and is recorded in `schema_migrations` with a
checksum. Rules:

- Never edit a migration that has been applied; add a new one instead.
  (Editing one is caught: its checksum no longer matches.)
- A database that has migrations this code doesn't know about is refused,
  since it was made by newer code.
"""

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS = Path(__file__).parent / "migrations"
NAME = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    """The database and the migration files disagree."""


def migrate(conn: sqlite3.Connection, folder: Path = MIGRATIONS) -> list[str]:
    """Applies every migration not yet applied. Returns the names it applied."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    files = _migration_files(folder)
    applied = {row[0]: row[1] for row in conn.execute("SELECT name, checksum FROM schema_migrations")}

    unknown = sorted(set(applied) - {path.name for path in files})
    if unknown:
        raise MigrationError(f"the database has migrations this code doesn't know: {unknown}; is the code out of date?")

    done = []
    for path in files:
        sql = path.read_text()
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        if path.name in applied:
            if applied[path.name] != checksum:
                raise MigrationError(f"{path.name} changed after it was applied; add a new migration instead")
            continue
        _apply(conn, path.name, sql, checksum)
        done.append(path.name)
    return done


def _migration_files(folder: Path) -> list[Path]:
    files = sorted(folder.glob("*.sql"))
    for path in files:
        if not NAME.match(path.name):
            raise MigrationError(f"{path.name}: migrations are named like 0001_create_things.sql")
    numbers = [path.name[:4] for path in files]
    if len(numbers) != len(set(numbers)):
        raise MigrationError(f"two migrations share a number in {folder}")
    return files


def _apply(conn: sqlite3.Connection, name: str, sql: str, checksum: str) -> None:
    """Runs one migration and records it, all in one transaction."""
    # executescript runs many statements but can't take parameters, so the
    # transaction is opened in the script and the record is inserted after.
    try:
        conn.executescript(f"BEGIN;\n{sql}")
        conn.execute(
            "INSERT INTO schema_migrations (name, checksum, applied_at) VALUES (?, ?, ?)",
            (name, checksum, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
