from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "sqlite_schema.sql"


class LedgerDB:
    """Small SQLite wrapper for local development.

    Production should use PostgreSQL with the schema in sql/postgres_schema.sql.
    The table names and fields are intentionally kept aligned.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        self.conn.executescript(schema)
        self.conn.commit()

    def execute(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def executemany(self, sql: str, params: Iterable[Iterable[Any] | dict[str, Any]]) -> sqlite3.Cursor:
        cur = self.conn.executemany(sql, params)
        self.conn.commit()
        return cur

    def query(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params))

    def query_one(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> Any:
        row = self.conn.execute(sql, params).fetchone()
        if row is None:
            return None
        return row[0]
