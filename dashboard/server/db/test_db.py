"""Tests for the database package. Run from the repo root: pytest dashboard/server/db

Each test uses a fresh database file in a temporary folder.
"""

import sqlite3

import pytest

from db import MigrationError, connect, migrate, open_database, transaction


def write(folder, name, sql):
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(sql)


def tables(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    yield connection
    connection.close()


def test_connect_creates_the_folder_and_turns_on_safety_settings(tmp_path):
    conn = connect(tmp_path / "new" / "folder" / "lobster.db")

    assert (tmp_path / "new" / "folder" / "lobster.db").exists()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_the_real_migrations_apply_to_a_fresh_database(tmp_path):
    conn = open_database(tmp_path / "lobster.db")

    assert "app_settings" in tables(conn)


def test_migrations_apply_in_order_and_only_once(conn, tmp_path):
    folder = tmp_path / "migrations"
    write(folder, "0002_b.sql", "ALTER TABLE a ADD COLUMN extra TEXT;")
    write(folder, "0001_a.sql", "CREATE TABLE a (id INTEGER PRIMARY KEY);")

    assert migrate(conn, folder) == ["0001_a.sql", "0002_b.sql"]
    assert migrate(conn, folder) == []

    write(folder, "0003_c.sql", "CREATE TABLE c (id INTEGER PRIMARY KEY);")
    assert migrate(conn, folder) == ["0003_c.sql"]


def test_a_failing_migration_leaves_no_trace(conn, tmp_path):
    folder = tmp_path / "migrations"
    write(folder, "0001_good.sql", "CREATE TABLE good (id INTEGER);")
    write(folder, "0002_bad.sql", "CREATE TABLE half (id INTEGER);\nTHIS IS NOT SQL;")

    with pytest.raises(sqlite3.OperationalError):
        migrate(conn, folder)

    assert "good" in tables(conn)
    assert "half" not in tables(conn)  # the bad file's first statement was undone too
    applied = [row[0] for row in conn.execute("SELECT name FROM schema_migrations")]
    assert applied == ["0001_good.sql"]


def test_editing_an_applied_migration_is_caught(conn, tmp_path):
    folder = tmp_path / "migrations"
    write(folder, "0001_a.sql", "CREATE TABLE a (id INTEGER);")
    migrate(conn, folder)

    write(folder, "0001_a.sql", "CREATE TABLE a (id INTEGER, sneaky TEXT);")
    with pytest.raises(MigrationError, match="changed"):
        migrate(conn, folder)


def test_a_database_from_newer_code_is_refused(conn, tmp_path):
    folder = tmp_path / "migrations"
    write(folder, "0001_a.sql", "CREATE TABLE a (id INTEGER);")
    write(folder, "0002_b.sql", "CREATE TABLE b (id INTEGER);")
    migrate(conn, folder)

    (folder / "0002_b.sql").unlink()
    with pytest.raises(MigrationError, match="doesn't know"):
        migrate(conn, folder)


@pytest.mark.parametrize("name", ["1_short.sql", "0001-Dashes.sql", "0001_UPPER.sql"])
def test_badly_named_migrations_are_refused(conn, tmp_path, name):
    write(tmp_path / "migrations", name, "SELECT 1;")

    with pytest.raises(MigrationError):
        migrate(conn, tmp_path / "migrations")


def test_two_migrations_with_one_number_are_refused(conn, tmp_path):
    folder = tmp_path / "migrations"
    write(folder, "0001_a.sql", "SELECT 1;")
    write(folder, "0001_b.sql", "SELECT 1;")

    with pytest.raises(MigrationError, match="share a number"):
        migrate(conn, folder)


def test_transaction_saves_everything_or_nothing(conn):
    conn.execute("CREATE TABLE t (x INTEGER)")

    with transaction(conn):
        conn.execute("INSERT INTO t VALUES (1)")
        conn.execute("INSERT INTO t VALUES (2)")

    with pytest.raises(ZeroDivisionError):
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES (3)")
            1 / 0

    assert [row[0] for row in conn.execute("SELECT x FROM t ORDER BY x")] == [1, 2]


def test_a_connection_can_be_used_on_another_thread(tmp_path):
    """FastAPI opens a request's connection on a worker thread and may use it on another
    (this broke /api/history: "SQLite objects created in a thread can only be used in that same thread")."""
    import threading

    made = {}
    worker = threading.Thread(target=lambda: made.setdefault("conn", connect(tmp_path / "t.db")))
    worker.start()
    worker.join()

    assert made["conn"].execute("SELECT 1").fetchone()[0] == 1
