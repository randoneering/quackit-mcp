from __future__ import annotations

import os

import pytest

from quackit.models import ContentType, MemoryCreate, MemoryType, MemoryUpdate, SessionStatus, SkillCreate, SkillUpdate
from quackit.storage.postgres import PostgresStorage

PG_URL = os.environ.get("QUACKIT_DATABASE_URL") or os.environ.get("AGENT_MEMORY_DATABASE_URL") or "postgresql://test:test@localhost:5433/agent_memory"


@pytest.fixture
def storage() -> PostgresStorage:
    s = PostgresStorage(PG_URL)
    with s._pool.connection() as conn:
        conn.execute("TRUNCATE projects, sessions, memories, skills CASCADE")
    return s


def test_bootstraps_schema_and_creates_session(storage: PostgresStorage) -> None:
    session = storage.create_session()

    assert session.status is SessionStatus.OPEN
    assert session.id
    assert session.project_id is None


def test_create_project(storage: PostgresStorage) -> None:
    project = storage.create_project(name="test", description="desc")

    assert project.name == "test"
    assert project.description == "desc"

    fetched = storage.get_project(project.id)
    assert fetched is not None
    assert fetched.name == "test"


def test_session_with_project_id(storage: PostgresStorage) -> None:
    project = storage.create_project(name="proj")
    session = storage.create_session(project_id=project.id)

    assert session.project_id == project.id

    fetched = storage.get_session(session.id)
    assert fetched is not None
    assert fetched.project_id == project.id


def test_search_memories_by_project(storage: PostgresStorage) -> None:
    project = storage.create_project(name="proj")
    session = storage.create_session(project_id=project.id)
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="project memory", tags=["proj"]),
    )

    results = storage.search_memories_by_project(project.id, query="project", memory_type=None)
    assert len(results) == 1
    assert results[0].tags == ["proj"]


def test_memory_inherits_project_id_from_session(storage: PostgresStorage) -> None:
    project = storage.create_project(name="proj")
    session = storage.create_session(project_id=project.id)
    record = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="inherited", tags=[]),
    )

    assert record.project_id == project.id

    fetched = storage.get_memory(record.mem_id)
    assert fetched is not None
    assert fetched.project_id == project.id


def test_saves_gets_and_searches_memory(storage: PostgresStorage) -> None:
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="postgres migration fixed", tags=["postgres", "migration"]),
    )

    fetched = storage.get_memory(created.mem_id)
    results = storage.search_memories(session.id, query="postgres", memory_type=None)

    assert fetched.mem_id == created.mem_id
    assert fetched.tags == ["postgres", "migration"]
    assert [result.mem_id for result in results] == [created.mem_id]


def test_save_memory_fails_for_missing_session(storage: PostgresStorage) -> None:
    with pytest.raises(RuntimeError, match=r"^Session not found: missing-session$"):
        storage.save_memory(
            session_id="missing-session",
            memory=MemoryCreate(type=MemoryType.NOTE, content="orphan memory", tags=[]),
        )


def test_save_memory_fails_for_closed_session(storage: PostgresStorage) -> None:
    session = storage.create_session()
    storage.end_session(session.id, summary="done")

    with pytest.raises(RuntimeError, match=r"Session is closed: .*cannot save memory"):
        storage.save_memory(
            session_id=session.id,
            memory=MemoryCreate(type=MemoryType.NOTE, content="closed session write", tags=[]),
        )


def test_heartbeat_and_orphan_detection(storage: PostgresStorage) -> None:
    from datetime import UTC, datetime, timedelta

    session = storage.create_session()

    cutoff = datetime.now(UTC) - timedelta(minutes=1)
    stale = storage.list_stale_open_sessions(cutoff)
    assert len(stale) == 0

    storage.update_session_heartbeat(session.id)
    past_cutoff = datetime.now(UTC) + timedelta(minutes=5)
    stale = storage.list_stale_open_sessions(past_cutoff)
    assert len(stale) == 1
    assert stale[0].id == session.id

    orphaned = storage.orphan_session(session.id, summary="orphaned by test")
    assert orphaned.status is SessionStatus.ORPHANED
    assert orphaned.summary == "orphaned by test"


def test_preserves_utc_timestamps_on_round_trip(storage: PostgresStorage) -> None:
    from datetime import UTC

    session = storage.create_session()
    memory = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="utc timestamp", tags=[]),
    )

    fetched_session = storage.get_session(session.id)
    fetched_memory = storage.get_memory(memory.mem_id)
    search_results = storage.search_memories(session.id, query="utc", memory_type=None)

    assert fetched_session is not None
    assert fetched_memory is not None
    assert fetched_session.started_at.tzinfo == UTC
    assert fetched_session.last_heartbeat.tzinfo == UTC
    assert fetched_memory.created_at.tzinfo == UTC
    assert search_results[0].created_at.endswith("+00:00")


def test_list_recent_sessions_orders_by_started_at(storage: PostgresStorage) -> None:
    s1 = storage.create_session()
    s2 = storage.create_session()

    recent = storage.list_recent_sessions(limit=10)
    assert len(recent) >= 2
    assert recent[0].id == s2.id
    assert recent[1].id == s1.id


def test_list_sessions_by_project(storage: PostgresStorage) -> None:
    project = storage.create_project(name="proj")
    s1 = storage.create_session(project_id=project.id)
    s2 = storage.create_session(project_id=project.id)

    sessions = storage.list_sessions_by_project(project.id)
    assert len(sessions) == 2
    assert {s.id for s in sessions} == {s1.id, s2.id}


def test_list_projects_returns_all(storage: PostgresStorage) -> None:
    p1 = storage.create_project(name="alpha")
    p2 = storage.create_project(name="beta")

    projects = storage.list_projects()
    assert len(projects) >= 2
    assert {p.id for p in projects}.issuperset({p1.id, p2.id})


def test_save_memory_with_metadata(storage: PostgresStorage) -> None:
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="skill content",
            tags=["skill"],
            title="My Skill",
            content_type=ContentType.SKILL,
            metadata={"language": "python", "framework": "pytest", "version": "1.0"},
        ),
    )

    assert created.metadata == {"language": "python", "framework": "pytest", "version": "1.0"}

    fetched = storage.get_memory(created.mem_id)
    assert fetched is not None
    assert fetched.metadata == {"language": "python", "framework": "pytest", "version": "1.0"}

    results = storage.search_memories(session.id, query="skill", memory_type=None)
    assert results[0].metadata == {"language": "python", "framework": "pytest", "version": "1.0"}


def test_update_memory_metadata(storage: PostgresStorage) -> None:
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="original", tags=[], metadata={"old": "data"}),
    )

    updated = storage.update_memory(created.mem_id, MemoryUpdate(metadata={"language": "go"}))

    assert updated.metadata == {"language": "go"}


def test_update_memory_updates_fields(storage: PostgresStorage) -> None:
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="original", tags=["a"], title="orig", content_type=ContentType.NOTE),
    )

    updated = storage.update_memory(
        created.mem_id,
        MemoryUpdate(content="updated", tags=["b", "c"], title="new title", content_type=ContentType.CODE),
    )

    assert updated.content == "updated"
    assert updated.tags == ["b", "c"]
    assert updated.title == "new title"
    assert updated.content_type is ContentType.CODE
    assert updated.mem_id == created.mem_id


def test_update_memory_partial_update(storage: PostgresStorage) -> None:
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="original", tags=["a"], title="orig"),
    )

    updated = storage.update_memory(created.mem_id, MemoryUpdate(content="only content changed"))

    assert updated.content == "only content changed"
    assert updated.tags == ["a"]
    assert updated.title == "orig"


def test_update_memory_raises_for_missing(storage: PostgresStorage) -> None:
    with pytest.raises(RuntimeError, match=r"Memory not found: mem_dead"):
        storage.update_memory("mem_dead", MemoryUpdate(content="nope"))


def test_search_memories_filters_by_content_type(storage: PostgresStorage) -> None:
    session = storage.create_session()
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="def foo(): pass", tags=["python"], content_type=ContentType.CODE),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="# Heading\n\nbody", tags=["docs"], content_type=ContentType.MARKDOWN),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="plain note", tags=["misc"]),
    )

    code_results = storage.search_memories(session.id, query="", memory_type=None, content_type="code")
    markdown_results = storage.search_memories(session.id, query="", memory_type=None, content_type="markdown")
    all_results = storage.search_memories(session.id, query="", memory_type=None)

    assert len(code_results) == 1
    assert code_results[0].content_type is ContentType.CODE
    assert len(markdown_results) == 1
    assert markdown_results[0].content_type is ContentType.MARKDOWN
    assert len(all_results) == 3


def test_search_memories_by_project_filters_by_content_type(storage: PostgresStorage) -> None:
    project = storage.create_project(name="proj")
    session = storage.create_session(project_id=project.id)
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="def bar(): pass", tags=["python"], content_type=ContentType.CODE),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="## Docs", tags=["docs"], content_type=ContentType.MARKDOWN),
    )

    code_results = storage.search_memories_by_project(project.id, query="", memory_type=None, content_type="code")
    markdown_results = storage.search_memories_by_project(project.id, query="", memory_type=None, content_type="markdown")

    assert len(code_results) == 1
    assert code_results[0].content_type is ContentType.CODE
    assert len(markdown_results) == 1
    assert markdown_results[0].content_type is ContentType.MARKDOWN


def test_get_unknown_returns_none(storage: PostgresStorage) -> None:
    assert storage.get_project("nonexistent") is None
    assert storage.get_session("nonexistent") is None
    assert storage.get_memory("nonexistent") is None
