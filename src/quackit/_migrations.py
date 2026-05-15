from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class _Migration:
    version: int
    description: str
    sql_postgres: str
    sql_duckdb: str


_MIGRATIONS: list[_Migration] = []


def register(version: int, description: str, sql_postgres: str, sql_duckdb: str) -> None:
    _MIGRATIONS.append(_Migration(version, description, sql_postgres, sql_duckdb))


register(
    version=5,
    description="Create skills table",
    sql_postgres="""
        CREATE TABLE IF NOT EXISTS skills (
            skill_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            source TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
        CREATE INDEX IF NOT EXISTS idx_skills_updated_at ON skills(updated_at DESC);
    """,
    sql_duckdb="""
        CREATE TABLE IF NOT EXISTS skills (
            skill_id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description VARCHAR,
            content VARCHAR NOT NULL,
            tags VARCHAR NOT NULL DEFAULT '[]',
            source VARCHAR,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
        CREATE INDEX IF NOT EXISTS idx_skills_updated_at ON skills(updated_at DESC);
    """,
)

register(
    version=4,
    description="Add metadata column to memories table",
    sql_postgres="""
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS metadata TEXT DEFAULT '{}';
    """,
    sql_duckdb="""
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS metadata VARCHAR DEFAULT '{}';
    """,
)

register(
    version=3,
    description="Add title and content_type columns to memories table",
    sql_postgres="""
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS title TEXT;
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS content_type TEXT;
    """,
    sql_duckdb="""
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS title VARCHAR;
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS content_type VARCHAR;
    """,
)

register(
    version=2,
    description="Add indexes for session_id, project_id, type, created_at, content/tags search",
    sql_postgres="""
        CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories(session_id);
        CREATE INDEX IF NOT EXISTS idx_memories_project_id ON memories(project_id);
        CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
        CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_last_heartbeat ON sessions(last_heartbeat);
    """,
    sql_duckdb="""
        CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories(session_id);
        CREATE INDEX IF NOT EXISTS idx_memories_project_id ON memories(project_id);
        CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
        CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_last_heartbeat ON sessions(last_heartbeat);
    """,
)


def run_migrations(conn: Any, backend_type: str) -> None:
    placeholder = "%s" if backend_type == "postgres" else "?"
    conn.execute("CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL)")
    row = conn.execute("SELECT MAX(version) AS v FROM _schema_version").fetchone()
    if row:
        val = row["v"] if isinstance(row, dict) else row[0]
        current = val if val is not None else 0
    else:
        current = 0

    for m in sorted(_MIGRATIONS, key=lambda x: x.version):
        if m.version > current:
            sql = m.sql_postgres if backend_type == "postgres" else m.sql_duckdb
            conn.execute(sql)
            conn.execute(
                f"INSERT INTO _schema_version (version, applied_at) VALUES ({placeholder}, {placeholder})",
                [m.version, datetime.now(UTC)],
            )
