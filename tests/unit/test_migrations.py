from __future__ import annotations

from pathlib import Path

from quackit._migrations import run_migrations
from quackit.storage.duckdb import DuckDBStorage


def test_migration_v2_creates_indexes(duckdb_path: Path) -> None:
    storage = DuckDBStorage(duckdb_path)

    indexes = storage._connection.execute(
        "SELECT index_name FROM duckdb_indexes WHERE table_name = 'memories'"
    ).fetchall()
    index_names = {row[0] for row in indexes}
    assert "idx_memories_session_id" in index_names
    assert "idx_memories_project_id" in index_names
    assert "idx_memories_type" in index_names
    assert "idx_memories_created_at" in index_names
    storage.close()


def test_migration_idempotent(duckdb_path: Path) -> None:
    storage = DuckDBStorage(duckdb_path)
    storage.close()

    storage2 = DuckDBStorage(duckdb_path)
    run_migrations(storage2._connection, "duckdb")
    storage2.close()


def test_schema_version_tracked(duckdb_path: Path) -> None:
    storage = DuckDBStorage(duckdb_path)
    row = storage._connection.execute(
        "SELECT MAX(version) FROM _schema_version"
    ).fetchone()
    assert row is not None
    assert row[0] >= 2
    storage.close()
