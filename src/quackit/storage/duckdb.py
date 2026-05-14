from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import duckdb

log = logging.getLogger(__name__)

_POSTGRES_ENV_VARS = ("QUACKIT_DATABASE_URL", "AGENT_MEMORY_DATABASE_URL")

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


class DuckDBStorage:
    def __init__(self, database_path: Path) -> None:
        for var in _POSTGRES_ENV_VARS:
            if os.environ.get(var):
                log.warning(
                    "%s is set (%s...) but DuckDB storage was requested at %s — data will NOT be visible to Postgres consumers",
                    var, os.environ[var][:40], database_path,
                )
                break
        resolved = database_path.resolve()
        if ".." in str(database_path):
            log.warning("Database path contains '..', resolved to %s", resolved)
        self._database_path = resolved
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        log.info("Connecting to DuckDB at %s", self._database_path)
        try:
            self._connection = duckdb.connect(str(self._database_path))
        except Exception:
            log.exception("Failed to connect to DuckDB at %s", self._database_path)
            raise
        self._initialize_schema()
        run_migrations(self._connection, "duckdb")
        log.debug("DuckDB schema initialized")

    def close(self) -> None:
        self._connection.close()
        log.debug("DuckDB connection closed")

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _initialize_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description VARCHAR,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR PRIMARY KEY,
                project_id VARCHAR,
                status VARCHAR NOT NULL,
                summary VARCHAR,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                last_heartbeat TIMESTAMP NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                skill_id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description VARCHAR,
                content VARCHAR NOT NULL,
                tags VARCHAR NOT NULL DEFAULT '[]',
                source VARCHAR,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id VARCHAR PRIMARY KEY,
                mem_id VARCHAR NOT NULL UNIQUE,
                session_id VARCHAR NOT NULL,
                project_id VARCHAR,
                type VARCHAR NOT NULL,
                content VARCHAR NOT NULL,
                tags VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )

    def create_project(self, name: str, description: str | None = None) -> ProjectRecord:
        now = datetime.now(UTC)
        project_id = str(uuid4())
        self._connection.execute(
            "INSERT INTO projects (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            [project_id, name, description, now],
        )
        return ProjectRecord(id=project_id, name=name, description=description, created_at=now)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        row = self._connection.execute(
            "SELECT id, name, description, created_at FROM projects WHERE id = ?",
            [project_id],
        ).fetchone()
        if row is None:
            return None
        return ProjectRecord(id=row[0], name=row[1], description=row[2], created_at=row[3])

    def consolidate_projects(self, source_ids: list[str], target_id: str) -> ProjectRecord:
        self._connection.execute("BEGIN TRANSACTION")
        try:
            target = self.get_project(target_id)
            if target is None:
                raise RuntimeError(f"Target project not found: {target_id}")
            missing = [sid for sid in source_ids if self.get_project(sid) is None]
            if missing:
                raise RuntimeError(f"Source project(s) not found: {missing}")
            placeholders = ",".join("?" for _ in source_ids)
            self._connection.execute(
                f"UPDATE sessions SET project_id = ? WHERE project_id IN ({placeholders})",
                [target_id, *source_ids],
            )
            self._connection.execute(
                f"UPDATE memories SET project_id = ? WHERE project_id IN ({placeholders})",
                [target_id, *source_ids],
            )
            self._connection.execute(
                f"DELETE FROM projects WHERE id IN ({placeholders})",
                source_ids,
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return target

    def list_projects(self) -> list[ProjectRecord]:
        rows = self._connection.execute(
            "SELECT id, name, description, created_at FROM projects ORDER BY created_at DESC"
        ).fetchall()
        return [
            ProjectRecord(id=row[0], name=row[1], description=row[2], created_at=row[3])
            for row in rows
        ]

    def create_session(self, project_id: str | None = None) -> SessionRecord:
        now = datetime.now(UTC)
        session_id = str(uuid4())
        self._connection.execute(
            "INSERT INTO sessions (id, project_id, status, summary, started_at, ended_at, last_heartbeat) VALUES (?, ?, ?, ?, ?, ?, ?)",
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
        rows = self._connection.execute(
            "SELECT id, project_id, status, summary, started_at, ended_at, last_heartbeat FROM sessions ORDER BY started_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        return [
            SessionRecord(
                id=row[0],
                project_id=row[1],
                status=SessionStatus(row[2]),
                summary=row[3],
                started_at=self._as_utc(row[4]),
                ended_at=self._as_utc(row[5]),
                last_heartbeat=self._as_utc(row[6]),
            )
            for row in rows
        ]

    def get_session(self, session_id: str) -> SessionRecord | None:
        row = self._connection.execute(
            "SELECT id, project_id, status, summary, started_at, ended_at, last_heartbeat FROM sessions WHERE id = ?",
            [session_id],
        ).fetchone()
        if row is None:
            return None
        return SessionRecord(
            id=row[0],
            project_id=row[1],
            status=SessionStatus(row[2]),
            summary=row[3],
            started_at=self._as_utc(row[4]),
            ended_at=self._as_utc(row[5]),
            last_heartbeat=self._as_utc(row[6]),
        )

    def update_session_heartbeat(self, session_id: str) -> None:
        now = datetime.now(UTC)
        self._connection.execute(
            "UPDATE sessions SET last_heartbeat = ? WHERE id = ?",
            [now, session_id],
        )

    def list_stale_open_sessions(self, since: datetime) -> list[SessionRecord]:
        rows = self._connection.execute(
            "SELECT id, project_id, status, summary, started_at, ended_at, last_heartbeat FROM sessions WHERE status = ? AND last_heartbeat < ?",
            [SessionStatus.OPEN.value, since],
        ).fetchall()
        return [
            SessionRecord(
                id=row[0],
                project_id=row[1],
                status=SessionStatus(row[2]),
                summary=row[3],
                started_at=self._as_utc(row[4]),
                ended_at=self._as_utc(row[5]),
                last_heartbeat=self._as_utc(row[6]),
            )
            for row in rows
        ]

    def orphan_session(self, session_id: str, summary: str) -> SessionRecord:
        now = datetime.now(UTC)
        self._connection.execute(
            "UPDATE sessions SET status = ?, summary = ?, ended_at = ?, last_heartbeat = ? WHERE id = ?",
            [SessionStatus.ORPHANED.value, summary, now, now, session_id],
        )
        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")
        return session

    def end_session(self, session_id: str, summary: str) -> SessionRecord:
        ended_at = datetime.now(UTC)
        self._connection.execute(
            "UPDATE sessions SET status = ?, summary = ?, ended_at = ?, last_heartbeat = ? WHERE id = ?",
            [SessionStatus.CLOSED.value, summary, ended_at, ended_at, session_id],
        )
        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")
        return session

    def _insert_memory(self, record: MemoryRecord) -> None:
        self._connection.execute(
            "INSERT INTO memories (id, mem_id, session_id, project_id, type, content, tags, title, content_type, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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

    def _row_to_memory(self, row) -> MemoryRecord:
        tags = json.loads(row[6])
        content_type_val = row[8]
        metadata_raw = row[9]
        return MemoryRecord(
            id=row[0],
            mem_id=row[1],
            session_id=row[2],
            project_id=row[3],
            type=row[4],
            content=row[5],
            tags=tags,
            title=row[7],
            content_type=ContentType(content_type_val) if content_type_val else None,
            metadata=json.loads(metadata_raw) if metadata_raw else {},
            created_at=self._as_utc(row[10]),
        )

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
        self._insert_memory(record)
        return record

    def get_memory(self, mem_id: str) -> MemoryRecord | None:
        row = self._connection.execute(
            "SELECT id, mem_id, session_id, project_id, type, content, tags, title, content_type, metadata, created_at FROM memories WHERE mem_id = ?",
            [mem_id],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def update_memory(self, mem_id: str, update: MemoryUpdate) -> MemoryRecord:
        existing = self.get_memory(mem_id)
        if existing is None:
            raise RuntimeError(f"Memory not found: {mem_id}")

        set_clauses: list[str] = []
        params: list[object] = []
        if update.content is not None:
            set_clauses.append("content = ?")
            params.append(update.content)
        if update.tags is not None:
            set_clauses.append("tags = ?")
            params.append(json.dumps(update.tags))
        if update.title is not None:
            set_clauses.append("title = ?")
            params.append(update.title)
        if update.content_type is not None:
            set_clauses.append("content_type = ?")
            params.append(update.content_type.value)
        if update.metadata is not None:
            set_clauses.append("metadata = ?")
            params.append(json.dumps(update.metadata))

        if not set_clauses:
            return existing

        params.append(mem_id)
        self._connection.execute(
            f"UPDATE memories SET {', '.join(set_clauses)} WHERE mem_id = ?",
            params,
        )
        updated = self.get_memory(mem_id)
        assert updated is not None
        return updated

    def _row_to_search_result(self, row) -> SearchResult:
        metadata_raw = row[6]
        return SearchResult(
            mem_id=row[0],
            type=row[1],
            snippet=row[2] if len(row[2]) <= 120 else f"{row[2][:120]}...",
            tags=json.loads(row[3]),
            title=row[4],
            content_type=ContentType(row[5]) if row[5] else None,
            metadata=json.loads(metadata_raw) if metadata_raw else {},
            created_at=self._as_utc(row[7]).isoformat(),
        )

    def search_memories(
        self,
        session_id: str,
        query: str,
        memory_type: str | None,
        content_type: str | None = None,
    ) -> list[SearchResult]:
        sql = "SELECT mem_id, type, content, tags, title, content_type, metadata, created_at FROM memories WHERE session_id = ? AND (lower(content) LIKE ? OR lower(tags) LIKE ?)"
        params: list[object] = [session_id, f"%{query.lower()}%", f"%{query.lower()}%"]
        if memory_type is not None:
            sql += " AND type = ?"
            params.append(memory_type)
        if content_type is not None:
            sql += " AND content_type = ?"
            params.append(content_type)
        sql += " ORDER BY created_at DESC"
        rows = self._connection.execute(sql, params).fetchall()
        return [self._row_to_search_result(row) for row in rows]

    def _skill_from_row(self, row) -> SkillRecord:
        return SkillRecord(
            skill_id=row[0],
            name=row[1],
            description=row[2],
            content=row[3],
            tags=json.loads(row[4]),
            source=row[5],
            created_at=self._as_utc(row[6]),
            updated_at=self._as_utc(row[7]),
        )

    def save_skill(self, skill: SkillCreate) -> SkillRecord:
        now = datetime.now(UTC)
        skill_id = build_skill_id()
        self._connection.execute(
            "INSERT INTO skills (skill_id, name, description, content, tags, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
        row = self._connection.execute(
            "SELECT skill_id, name, description, content, tags, source, created_at, updated_at FROM skills WHERE skill_id = ?",
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
            set_clauses.append("name = ?")
            params.append(update.name)
        if update.description is not None:
            set_clauses.append("description = ?")
            params.append(update.description)
        if update.content is not None:
            set_clauses.append("content = ?")
            params.append(update.content)
        if update.tags is not None:
            set_clauses.append("tags = ?")
            params.append(json.dumps(update.tags))
        if update.source is not None:
            set_clauses.append("source = ?")
            params.append(update.source)

        if not set_clauses:
            return existing

        now = datetime.now(UTC)
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(skill_id)
        self._connection.execute(
            f"UPDATE skills SET {', '.join(set_clauses)} WHERE skill_id = ?",
            params,
        )
        updated = self.get_skill(skill_id)
        assert updated is not None
        return updated

    def delete_skill(self, skill_id: str) -> None:
        self._connection.execute("DELETE FROM skills WHERE skill_id = ?", [skill_id])

    def list_skills(self, query: str = "", tag: str | None = None) -> list[SkillRecord]:
        sql = "SELECT skill_id, name, description, content, tags, source, created_at, updated_at FROM skills"
        params: list[object] = []
        conditions: list[str] = []
        if query:
            conditions.append("(lower(name) LIKE ? OR lower(description) LIKE ? OR lower(content) LIKE ?)")
            q = f"%{query.lower()}%"
            params.extend([q, q, q])
        if tag is not None:
            conditions.append("lower(tags) LIKE ?")
            params.append(f"%{tag.lower()}%")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY updated_at DESC"
        rows = self._connection.execute(sql, params).fetchall()
        return [self._skill_from_row(row) for row in rows]

    def search_memories_by_project(
        self,
        project_id: str,
        query: str,
        memory_type: str | None,
        content_type: str | None = None,
    ) -> list[SearchResult]:
        sql = "SELECT mem_id, type, content, tags, title, content_type, metadata, created_at FROM memories WHERE project_id = ? AND (lower(content) LIKE ? OR lower(tags) LIKE ?)"
        params: list[object] = [project_id, f"%{query.lower()}%", f"%{query.lower()}%"]
        if memory_type is not None:
            sql += " AND type = ?"
            params.append(memory_type)
        if content_type is not None:
            sql += " AND content_type = ?"
            params.append(content_type)
        sql += " ORDER BY created_at DESC"
        rows = self._connection.execute(sql, params).fetchall()
        return [self._row_to_search_result(row) for row in rows]

    def list_sessions_by_project(self, project_id: str) -> list[SessionRecord]:
        rows = self._connection.execute(
            "SELECT id, project_id, status, summary, started_at, ended_at, last_heartbeat FROM sessions WHERE project_id = ? ORDER BY started_at DESC",
            [project_id],
        ).fetchall()
        return [
            SessionRecord(
                id=row[0],
                project_id=row[1],
                status=SessionStatus(row[2]),
                summary=row[3],
                started_at=self._as_utc(row[4]),
                ended_at=self._as_utc(row[5]),
                last_heartbeat=self._as_utc(row[6]),
            )
            for row in rows
        ]
