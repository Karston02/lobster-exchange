"""Lobster's database: SQLite, with numbered SQL migrations.

    from db import open_database, transaction

The database file's location is a setting (LOBSTER_DB_PATH); this package
only ever receives it as an argument.
"""

from .connection import connect, open_database, transaction
from .migrate import MigrationError, migrate

__all__ = ["connect", "open_database", "transaction", "MigrationError", "migrate"]
