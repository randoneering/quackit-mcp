from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from quackit._migrations import run_migrations

from quackit.models import (
    ContentType,
    MemoryCreate,
    MemoryRecord,
    MemoryUpdate,
    ProjectRecord,
    SearchResult,
    SessionRecord,
    SessionStatus,
    SkillCreate,
    SkillRecord,
    SkillUpdate,
    build_mem_id,
    build_skill_id,
)

log = logging.getLogger(__name__)


class PostgresStorage:
    def __init__(self, database_url: str) -> None:
        log.info("Creating Postgres connection pool")
        try:
            self._pool = ConnectionPool(
                conninfo=database_url,
                open=False,
                min_size=1,
                max_size=4,
                kwargs={"autocommit": True, "row_factory": dict_row},
            )
            self._pool.open()
            with self._pool.connection() as conn:
                conn.execute("SET timezone TO 'UTC'")
        except Exception:
            log.exception("Failed to initialize Postgres pool")
            raise
        self._initialize_schema()
        with self._pool.connection() as conn:
            run_migrations(conn, "postgres")
        log.debug("Postgres schema initialized")

    def close(self) -> None:
        self._pool.close()
        log.info("Postgres connection pool closed")

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _row_to_session(row: dict) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            project_id=row["project_id"],
            status=SessionStatus(row["status"]),
            summary=row["summary"],
            started_at=PostgresStorage._as_utc(row["started_at"]),
            ended_at=PostgresStorage._as_utc(row["ended_at"]),
            last_heartbeat=PostgresStorage._as_utc(row["last_heartbeat"]),
        )

    def _initialize_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    status TEXT NOT NULL,
                    summary TEXT,
                    started_at TIMESTAMPTZ NOT NULL,
                    ended_at TIMESTAMPTZ,
                    last_heartbeat TIMESTAMPTZ NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    source TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    mem_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    project_id TEXT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
            """)

    def create_project(self, name: str, description: str | None = None) -> ProjectRecord:
        now = datetime.now(UTC)
        project_id = str(uuid4())
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, description, created_at) VALUES (%s, %s, %s, %s)",
                [project_id, name, description, now],
            )
        return ProjectRecord(id=project_id, name=name, description=description, created_at=now)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, name, description, created_at FROM projects WHERE id = %s",
                [project_id],
            ).fetchone()
        if row is None:
            return None
        return ProjectRecord(**row)

    def consolidate_projects(self, source_ids: list[str], target_id: str) -> ProjectRecord:
        with self._pool.connection() as conn:
            try:
                conn.execute("BEGIN")
                target_row = conn.execute(
                    "SELECT id, name, description, created_at FROM projects WHERE id = %s",
                    [target_id],
                ).fetchone()
                if target_row is None:
                    raise RuntimeError(f"Target project not found: {target_id}")
                for sid in source_ids:
                    exists = conn.execute(
                        "SELECT 1 FROM projects WHERE id = %s", [sid],
                    ).fetchone()
                    if exists is None:
                        raise RuntimeError(f"Source project not found: {sid}")
                placeholders = ",".join("%s" for _ in source_ids)
                conn.execute(
                    f"UPDATE sessions SET project_id = %s WHERE project_id IN ({placeholders})",
                    [target_id, *source_ids],
                )
                conn.execute(
                    f"UPDATE memories SET project_id = %s WHERE project_id IN ({placeholders})",
                    [target_id, *source_ids],
                )
                conn.execute(
                    f"DELETE FROM projects WHERE id IN ({placeholders})",
                    source_ids,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return ProjectRecord(**target_row)

    def list_projects(self) -> list[ProjectRecord]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, description, created_at FROM projects ORDER BY created_at DESC"
            ).fetchall()
        return [ProjectRecord(**row) for row in rows]

    def create_session(self, project_id: str | None = None) -> SessionRecord:
        now = datetime.now(UTC)
        session_id = str(uuid4())
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, project_id, status, summary, started_at, ended_at, last_heartbeat) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [session_id, project_id, SessionStatus.OPEN.value, None, now, None, now],
            )
        return SessionRecord(
            id=session_id,
            project_id=project_id,
            status=SessionStatus.OPEN,
            summary=None,
            started_at=now,
            ended_at=None,
            last_heartbeat=now,
        )

    def list_recent_sessions(self, limit: int = 10) -> list[SessionRecord]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, project_id, status, summary, started_at, ended_at, last_heartbeat FROM sessions ORDER BY started_at DESC LIMIT %s",
                [limit],
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, project_id, status, summary, started_at, ended_at, last_heartbeat FROM sessions WHERE id = %s",
                [session_id],
            ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def update_session_heartbeat(self, session_id: str) -> None:
        now = datetime.now(UTC)
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE sessions SET last_heartbeat = %s WHERE id = %s",
                [now, session_id],
            )

    def list_stale_open_sessions(self, since: datetime) -> list[SessionRecord]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, project_id, status, summary, started_at, ended_at, last_heartbeat FROM sessions WHERE status = %s AND last_heartbeat < %s",
                [SessionStatus.OPEN.value, since],
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def orphan_session(self, session_id: str, summary: str) -> SessionRecord:
        now = datetime.now(UTC)
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE sessions SET status = %s, summary = %s, ended_at = %s, last_heartbeat = %s WHERE id = %s",
                [SessionStatus.ORPHANED.value, summary, now, now, session_id],
            )
        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")
        return session

    def end_session(self, session_id: str, summary: str) -> SessionRecord:
        ended_at = datetime.now(UTC)
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE sessions SET status = %s, summary = %s, ended_at = %s, last_heartbeat = %s WHERE id = %s",
                [SessionStatus.CLOSED.value, summary, ended_at, ended_at, session_id],
            )
        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")
        return session

    def save_memory(self, session_id: str, memory: MemoryCreate) -> MemoryRecord:
        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")
        if session.status is SessionStatus.CLOSED:
            raise RuntimeError(f"Session is closed: {session_id}; cannot save memory")

        now = datetime.now(UTC)
        record = MemoryRecord(
            id=str(uuid4()),
            mem_id=build_mem_id(),
            session_id=session_id,
            project_id=session.project_id,
            type=memory.type,
            content=memory.content,
            tags=memory.tags,
            title=memory.title,
            content_type=memory.content_type,
            metadata=memory.metadata,
            created_at=now,
        )
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO memories (id, mem_id, session_id, project_id, type, content, tags, title, content_type, metadata, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    record.id,
                    record.mem_id,
                    record.session_id,
                    record.project_id,
                    record.type.value,
                    record.content,
                    json.dumps(record.tags),
                    record.title,
                    record.content_type.value if record.content_type else None,
                    json.dumps(record.metadata),
                    record.created_at,
                ],
            )
        return record

    def get_memory(self, mem_id: str) -> MemoryRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, mem_id, session_id, project_id, type, content, tags, title, content_type, metadata, created_at FROM memories WHERE mem_id = %s",
                [mem_id],
            ).fetchone()
        if row is None:
            return None
        content_type_val = row["content_type"]
        metadata_raw = row.get("metadata", "{}")
        return MemoryRecord(
            id=row["id"],
            mem_id=row["mem_id"],
            session_id=row["session_id"],
            project_id=row["project_id"],
            type=row["type"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            title=row["title"],
            content_type=ContentType(content_type_val) if content_type_val else None,
            metadata=json.loads(metadata_raw) if metadata_raw else {},
            created_at=self._as_utc(row["created_at"]),
        )

    def update_memory(self, mem_id: str, update: MemoryUpdate) -> MemoryRecord:
        existing = self.get_memory(mem_id)
        if existing is None:
            raise RuntimeError(f"Memory not found: {mem_id}")

        set_clauses: list[str] = []
        params: list[object] = []
        if update.content is not None:
            set_clauses.append("content = %s")
            params.append(update.content)
        if update.tags is not None:
            set_clauses.append("tags = %s")
            params.append(json.dumps(update.tags))
        if update.title is not None:
            set_clauses.append("title = %s")
            params.append(update.title)
        if update.content_type is not None:
            set_clauses.append("content_type = %s")
            params.append(update.content_type.value)
        if update.metadata is not None:
            set_clauses.append("metadata = %s")
            params.append(json.dumps(update.metadata))

        if not set_clauses:
            return existing

        params.append(mem_id)
        with self._pool.connection() as conn:
            conn.execute(
                f"UPDATE memories SET {', '.join(set_clauses)} WHERE mem_id = %s",
                params,
            )
        updated = self.get_memory(mem_id)
        assert updated is not None
        return updated

    def _row_to_search_result(self, row) -> SearchResult:
        metadata_raw = row.get("metadata", "{}") if isinstance(row, dict) else "{}"
        return SearchResult(
            mem_id=row["mem_id"],
            type=row["type"],
            snippet=row["content"] if len(row["content"]) <= 120 else f"{row['content'][:120]}...",
            tags=json.loads(row["tags"]),
            title=row["title"],
            content_type=ContentType(row["content_type"]) if row["content_type"] else None,
            metadata=json.loads(metadata_raw) if metadata_raw else {},
            created_at=self._as_utc(row["created_at"]).isoformat(),
        )

    def search_memories(
        self,
        session_id: str,
        query: str,
        memory_type: str | None,
        content_type: str | None = None,
    ) -> list[SearchResult]:
        sql = "SELECT mem_id, type, content, tags, title, content_type, metadata, created_at FROM memories WHERE session_id = %s AND (lower(content) LIKE %s OR lower(tags) LIKE %s)"
        params: list[object] = [session_id, f"%{query.lower()}%", f"%{query.lower()}%"]
        if memory_type is not None:
            sql += " AND type = %s"
            params.append(memory_type)
        if content_type is not None:
            sql += " AND content_type = %s"
            params.append(content_type)
        sql += " ORDER BY created_at DESC"
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_search_result(row) for row in rows]

    def _skill_from_row(self, row: dict) -> SkillRecord:
        return SkillRecord(
            skill_id=row["skill_id"],
            name=row["name"],
            description=row["description"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            source=row["source"],
            created_at=self._as_utc(row["created_at"]),
            updated_at=self._as_utc(row["updated_at"]),
        )

    def save_skill(self, skill: SkillCreate) -> SkillRecord:
        now = datetime.now(UTC)
        skill_id = build_skill_id()
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO skills (skill_id, name, description, content, tags, source, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [skill_id, skill.name, skill.description, skill.content, json.dumps(skill.tags), skill.source, now, now],
            )
        return SkillRecord(
            skill_id=skill_id,
            name=skill.name,
            description=skill.description,
            content=skill.content,
            tags=skill.tags,
            source=skill.source,
            created_at=now,
            updated_at=now,
        )

    def get_skill(self, skill_id: str) -> SkillRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT skill_id, name, description, content, tags, source, created_at, updated_at FROM skills WHERE skill_id = %s",
                [skill_id],
            ).fetchone()
        if row is None:
            return None
        return self._skill_from_row(row)

    def update_skill(self, skill_id: str, update: SkillUpdate) -> SkillRecord:
        existing = self.get_skill(skill_id)
        if existing is None:
            raise RuntimeError(f"Skill not found: {skill_id}")

        set_clauses: list[str] = []
        params: list[object] = []
        if update.name is not None:
            set_clauses.append("name = %s")
            params.append(update.name)
        if update.description is not None:
            set_clauses.append("description = %s")
            params.append(update.description)
        if update.content is not None:
            set_clauses.append("content = %s")
            params.append(update.content)
        if update.tags is not None:
            set_clauses.append("tags = %s")
            params.append(json.dumps(update.tags))
        if update.source is not None:
            set_clauses.append("source = %s")
            params.append(update.source)

        if not set_clauses:
            return existing

        now = datetime.now(UTC)
        set_clauses.append("updated_at = %s")
        params.append(now)
        params.append(skill_id)
        with self._pool.connection() as conn:
            conn.execute(
                f"UPDATE skills SET {', '.join(set_clauses)} WHERE skill_id = %s",
                params,
            )
        updated = self.get_skill(skill_id)
        assert updated is not None
        return updated

    def delete_skill(self, skill_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM skills WHERE skill_id = %s", [skill_id])

    def list_skills(self, query: str = "", tag: str | None = None) -> list[SkillRecord]:
        sql = "SELECT skill_id, name, description, content, tags, source, created_at, updated_at FROM skills"
        params: list[object] = []
        conditions: list[str] = []
        if query:
            conditions.append("(lower(name) LIKE %s OR lower(description) LIKE %s OR lower(content) LIKE %s)")
            q = f"%{query.lower()}%"
            params.extend([q, q, q])
        if tag is not None:
            conditions.append("lower(tags) LIKE %s")
            params.append(f"%{tag.lower()}%")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY updated_at DESC"
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._skill_from_row(row) for row in rows]

    def search_memories_by_project(
        self,
        project_id: str,
        query: str,
        memory_type: str | None,
        content_type: str | None = None,
    ) -> list[SearchResult]:
        sql = "SELECT mem_id, type, content, tags, title, content_type, metadata, created_at FROM memories WHERE project_id = %s AND (lower(content) LIKE %s OR lower(tags) LIKE %s)"
        params: list[object] = [project_id, f"%{query.lower()}%", f"%{query.lower()}%"]
        if memory_type is not None:
            sql += " AND type = %s"
            params.append(memory_type)
        if content_type is not None:
            sql += " AND content_type = %s"
            params.append(content_type)
        sql += " ORDER BY created_at DESC"
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_search_result(row) for row in rows]

    def list_sessions_by_project(self, project_id: str) -> list[SessionRecord]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, project_id, status, summary, started_at, ended_at, last_heartbeat FROM sessions WHERE project_id = %s ORDER BY started_at DESC",
                [project_id],
            ).fetchall()
        return [self._row_to_session(row) for row in rows]
