from pathlib import Path

import pytest

from quackit.models import ContentType, MemoryType, SessionStatus
from quackit.service import MemoryNotFoundError
from quackit.service import MemoryService
from quackit.storage.duckdb import DuckDBStorage


def test_start_session_sets_active_session(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    session = service.start_session()

    assert session.status is SessionStatus.OPEN
    assert service._session_state.require_session_id() == session.id


def test_list_recent_sessions_rejects_invalid_limit(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    with pytest.raises(ValueError, match="limit must be between"):
        service.list_recent_sessions(limit=0)


def test_save_memory_requires_active_session(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    try:
        service.save_memory(type=MemoryType.NOTE, content="missing session", tags=[])
    except RuntimeError as exc:
        assert "No active session" in str(exc)
    else:
        raise AssertionError("RuntimeError not raised")


def test_activate_save_search_and_end_session(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    first = service.start_session()
    service.save_memory(
        type=MemoryType.NOTE, content="first session note", tags=["one"]
    )
    second = service.start_session()
    service.save_memory(
        type=MemoryType.ERROR_FIX, content="second session fix", tags=["two"]
    )

    service.activate_session(first.id)
    results = service.search_memory(query="session")
    ended = service.end_session(summary="wrapped first")

    assert [result.tags for result in results] == [["one"]]
    assert ended.status is SessionStatus.CLOSED
    assert ended.summary == "wrapped first"


def test_activate_closed_session_raises(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    session = service.start_session()
    service.end_session(summary="done")

    with pytest.raises(RuntimeError, match=r"Session is closed: .*start a new session"):
        service.activate_session(session.id)


def test_create_project_and_start_session_with_project(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    project = service.create_project(name="test-project", description="a test")
    session = service.start_session(project_id=project.id)

    assert session.project_id == project.id


def test_start_session_with_unknown_project_raises(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    with pytest.raises(RuntimeError, match=r"Project not found: missing"):
        service.start_session(project_id="missing")


def test_save_memory_with_metadata(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    created = service.save_memory(
        type=MemoryType.NOTE,
        content="skill: tdd",
        tags=["skill"],
        title="TDD",
        content_type=ContentType.SKILL,
        metadata={"language": "python", "framework": "pytest"},
    )

    assert created.metadata == {"language": "python", "framework": "pytest"}

    fetched = service.get_memory(created.mem_id)
    assert fetched.metadata == {"language": "python", "framework": "pytest"}


def test_update_memory_with_metadata(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    created = service.save_memory(type=MemoryType.NOTE, content="original", tags=[])

    updated = service.update_memory(
        mem_id=created.mem_id, metadata={"language": "rust"}
    )

    assert updated.metadata == {"language": "rust"}


def test_update_memory_updates_content(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    created = service.save_memory(
        type=MemoryType.NOTE, content="original", tags=["a"], title="orig"
    )

    updated = service.update_memory(
        mem_id=created.mem_id,
        content="updated",
        tags=["b"],
        title="new title",
        content_type=ContentType.CODE,
    )

    assert updated.content == "updated"
    assert updated.tags == ["b"]
    assert updated.title == "new title"
    assert updated.content_type is ContentType.CODE


def test_update_memory_validates_content(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    created = service.save_memory(type=MemoryType.NOTE, content="original", tags=[])

    with pytest.raises(ValueError, match="content must not be empty"):
        service.update_memory(mem_id=created.mem_id, content="")


def test_update_memory_validates_tags(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    created = service.save_memory(type=MemoryType.NOTE, content="original", tags=[])

    with pytest.raises(ValueError, match="tags exceeds"):
        service.update_memory(mem_id=created.mem_id, tags=[str(i) for i in range(51)])


def test_update_memory_partial(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    created = service.save_memory(
        type=MemoryType.NOTE, content="original", tags=["a"], title="orig"
    )

    updated = service.update_memory(mem_id=created.mem_id, content="only content")

    assert updated.content == "only content"
    assert updated.tags == ["a"]
    assert updated.title == "orig"


def test_update_memory_raises_for_unknown(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()

    with pytest.raises(MemoryNotFoundError, match=r"Memory not found: mem_dead"):
        service.update_memory(mem_id="mem_dead", content="nope")


def test_update_memory_requires_active_session(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    with pytest.raises(RuntimeError, match=r"No active session"):
        service.update_memory(mem_id="mem_any", content="nope")


def test_search_memory_filters_by_content_type(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    service.save_memory(
        type=MemoryType.NOTE,
        content="def foo(): pass",
        tags=["python"],
        title="func",
        content_type=ContentType.CODE,
    )
    service.save_memory(
        type=MemoryType.NOTE,
        content="# Docs",
        tags=["docs"],
        title="readme",
        content_type=ContentType.MARKDOWN,
    )
    service.save_memory(type=MemoryType.NOTE, content="plain note", tags=["misc"])

    code_results = service.search_memory(query="", content_type=ContentType.CODE)
    md_results = service.search_memory(query="", content_type=ContentType.MARKDOWN)
    skill_results = service.search_memory(query="", content_type=ContentType.SKILL)
    all_results = service.search_memory(query="")

    assert len(code_results) == 1
    assert code_results[0].content_type is ContentType.CODE
    assert len(md_results) == 1
    assert md_results[0].content_type is ContentType.MARKDOWN
    assert len(skill_results) == 0
    assert len(all_results) == 3


def test_search_memory_applies_default_limit(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    for i in range(105):
        service.save_memory(
            type=MemoryType.NOTE, content=f"limited memory {i}", tags=[]
        )

    results = service.search_memory(query="limited")

    assert len(results) == 100


def test_search_memory_with_project_scope(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    project = service.create_project(name="proj")
    session = service.start_session(project_id=project.id)
    service.save_memory(type=MemoryType.NOTE, content="project memory", tags=["proj"])

    results = service.search_memory(query="project", project_scope=True)
    assert len(results) == 1
    assert results[0].tags == ["proj"]


def test_save_skill_validates_payload(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    with pytest.raises(ValueError, match="name must not be empty"):
        service.save_skill(name="", content="content")


def test_update_skill_validates_payload(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    skill = service.save_skill(name="skill", content="content")

    with pytest.raises(ValueError, match="content must not be empty"):
        service.update_skill(skill_id=skill.skill_id, content="")


def test_close_stops_heartbeat(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    service = MemoryService(storage=storage, heartbeat_interval=60)
    service.start_session()

    service.close()

    assert service._heartbeat_manager is None


def test_orphan_detection_uses_count_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    service = MemoryService(storage=storage)
    session = storage.create_session()

    monkeypatch.setattr(storage, "list_stale_open_sessions", lambda since: [session])
    monkeypatch.setattr(storage, "count_memories", lambda session_id: 7)

    def fail_search(*args, **kwargs):
        raise AssertionError("search_memories should not be used for counts")

    monkeypatch.setattr(storage, "search_memories", fail_search)

    orphans = service.run_orphan_detection()

    assert orphans[0].summary == "Orphaned session with 7 memories"
