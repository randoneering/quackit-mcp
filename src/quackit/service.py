from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from quackit._validation import (
    DEFAULT_LIMIT,
    validate_content,
    validate_limit,
    validate_name,
    validate_query,
    validate_tags,
)
from quackit.models import (
    ContentType,
    MemoryCreate,
    MemoryRecord,
    MemoryType,
    MemoryUpdate,
    ProjectRecord,
    SearchResult,
    SessionRecord,
    SessionStatus,
    SkillCreate,
    SkillRecord,
    SkillUpdate,
)
from quackit.session import ActiveSessionState, HeartbeatManager
from quackit.storage import StorageBackend

log = logging.getLogger(__name__)


class SessionNotFoundError(RuntimeError):
    pass


class MemoryNotFoundError(RuntimeError):
    pass


class ProjectNotFoundError(RuntimeError):
    pass


class SkillNotFoundError(RuntimeError):
    pass


class MemoryService:
    def __init__(self, storage: StorageBackend, heartbeat_interval: int = 30) -> None:
        self._storage = storage
        self._session_state = ActiveSessionState()
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_manager: HeartbeatManager | None = None

    def create_project(self, name: str, description: str | None = None) -> ProjectRecord:
        return self._storage.create_project(name=name, description=description)

    def get_project(self, project_id: str) -> ProjectRecord:
        project = self._storage.get_project(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project not found: {project_id}")
        return project

    def consolidate_projects(self, source_ids: list[str], target_id: str) -> ProjectRecord:
        if not source_ids:
            raise RuntimeError("source_ids must not be empty")
        if target_id in source_ids:
            raise RuntimeError("target project cannot be in source_ids")
        self.get_project(target_id)
        return self._storage.consolidate_projects(source_ids, target_id)

    def list_projects(self) -> list[ProjectRecord]:
        return self._storage.list_projects()

    def start_session(self, project_id: str | None = None) -> SessionRecord:
        if project_id is not None:
            self.get_project(project_id)
        session = self._storage.create_session(project_id=project_id)
        self._session_state.activate(session.id)
        self._start_heartbeat()
        log.info("Started session %s (project=%s)", session.id, project_id)
        return session

    def list_recent_sessions(self, limit: int = 10) -> list[SessionRecord]:
        validate_limit(limit)
        return self._storage.list_recent_sessions(limit=limit)

    def activate_session(self, session_id: str) -> SessionRecord:
        session = self._storage.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        if session.status is SessionStatus.CLOSED:
            raise RuntimeError(f"Session is closed: {session_id}; start a new session")
        self._session_state.activate(session.id)
        self._start_heartbeat()
        log.info("Activated session %s", session_id)
        return session

    def end_session(self, summary: str) -> SessionRecord:
        session_id = self._session_state.require_session_id()
        session = self._storage.end_session(session_id=session_id, summary=summary)
        self._stop_heartbeat()
        self._session_state.clear()
        log.info("Ended session %s", session_id)
        return session

    def save_memory(
        self,
        type: MemoryType,
        content: str,
        tags: list[str],
        title: str | None = None,
        content_type: ContentType | None = None,
        metadata: dict[str, str] | None = None,
    ) -> MemoryRecord:
        session_id = self._session_state.require_session_id()
        validate_content(content)
        validate_tags(tags)
        return self._storage.save_memory(
            session_id=session_id,
            memory=MemoryCreate(
                type=type,
                content=content,
                tags=tags,
                title=title,
                content_type=content_type,
                metadata=metadata or {},
            ),
        )

    def get_memory(self, mem_id: str) -> MemoryRecord:
        memory = self._storage.get_memory(mem_id)
        if memory is None:
            raise MemoryNotFoundError(f"Memory not found: {mem_id}")
        return memory

    def update_memory(
        self,
        mem_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        title: str | None = None,
        content_type: ContentType | None = None,
        metadata: dict[str, str] | None = None,
    ) -> MemoryRecord:
        session_id = self._session_state.require_session_id()
        if content is not None:
            validate_content(content)
        if tags is not None:
            validate_tags(tags)
        existing = self._storage.get_memory(mem_id)
        if existing is None:
            raise MemoryNotFoundError(f"Memory not found: {mem_id}")
        if existing.session_id != session_id:
            raise RuntimeError(f"Memory {mem_id} does not belong to the active session")
        return self._storage.update_memory(
            mem_id=mem_id,
            update=MemoryUpdate(
                content=content,
                tags=tags,
                title=title,
                content_type=content_type,
                metadata=metadata,
            ),
        )

    def search_memory(
        self,
        query: str,
        type: MemoryType | None = None,
        project_scope: bool = False,
        content_type: ContentType | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[SearchResult]:
        session_id = self._session_state.require_session_id()
        validate_query(query)
        validate_limit(limit)
        memory_type = None if type is None else type.value
        ct = None if content_type is None else content_type.value
        if project_scope:
            session = self._storage.get_session(session_id)
            if session is None or session.project_id is None:
                return []
            return self._storage.search_memories_by_project(
                project_id=session.project_id,
                query=query,
                memory_type=memory_type,
                content_type=ct,
                limit=limit,
            )
        return self._storage.search_memories(
            session_id=session_id,
            query=query,
            memory_type=memory_type,
            content_type=ct,
            limit=limit,
        )

    def list_sessions_by_project(self, project_id: str) -> list[SessionRecord]:
        return self._storage.list_sessions_by_project(project_id)

    def save_skill(
        self,
        name: str,
        content: str,
        description: str | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> SkillRecord:
        validate_name(name)
        validate_content(content)
        validate_tags(tags or [])
        return self._storage.save_skill(
            SkillCreate(
                name=name,
                description=description,
                content=content,
                tags=tags or [],
                source=source,
            ),
        )

    def get_skill(self, skill_id: str) -> SkillRecord:
        skill = self._storage.get_skill(skill_id)
        if skill is None:
            raise SkillNotFoundError(f"Skill not found: {skill_id}")
        return skill

    def update_skill(
        self,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> SkillRecord:
        if name is not None:
            validate_name(name)
        if content is not None:
            validate_content(content)
        if tags is not None:
            validate_tags(tags)
        return self._storage.update_skill(
            skill_id=skill_id,
            update=SkillUpdate(
                name=name,
                description=description,
                content=content,
                tags=tags,
                source=source,
            ),
        )

    def delete_skill(self, skill_id: str) -> None:
        self._storage.delete_skill(skill_id)

    def list_skills(self, query: str = "", tag: str | None = None) -> list[SkillRecord]:
        validate_query(query)
        return self._storage.list_skills(query=query, tag=tag)

    def run_orphan_detection(self, threshold_minutes: int = 5) -> list[SessionRecord]:
        since = datetime.now(UTC) - timedelta(minutes=threshold_minutes)
        stale = self._storage.list_stale_open_sessions(since)
        orphans: list[SessionRecord] = []
        for session in stale:
            count = self._storage.count_memories(session.id)
            summary = f"Orphaned session with {count} memories"
            orphans.append(self._storage.orphan_session(session.id, summary))
            log.warning("Orphaned session %s with %d memories", session.id, count)
        if orphans:
            log.info("Orphan detection: %d sessions orphaned", len(orphans))
        return orphans

    def _start_heartbeat(self) -> None:
        self._stop_heartbeat()
        session_id = self._session_state.require_session_id()

        def _beat() -> None:
            self._storage.update_session_heartbeat(session_id)

        self._heartbeat_manager = HeartbeatManager(
            heartbeat_fn=_beat,
            interval=self._heartbeat_interval,
        )
        self._heartbeat_manager.start()
        log.debug(
            "Heartbeat started for session %s (interval=%ds)",
            session_id,
            self._heartbeat_interval,
        )

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_manager is not None:
            self._heartbeat_manager.stop()
            log.debug("Heartbeat stopped")
            self._heartbeat_manager = None

    def close(self) -> None:
        self._stop_heartbeat()
        self._storage.close()
