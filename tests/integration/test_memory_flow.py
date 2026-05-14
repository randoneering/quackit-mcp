from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke_test.py"

from datetime import datetime, UTC, timedelta

from quackit.models import ContentType, MemoryType, SessionStatus
from quackit.service import MemoryNotFoundError, MemoryService, ProjectNotFoundError, SessionNotFoundError
from quackit.storage.duckdb import DuckDBStorage


def test_save_memory_with_metadata(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    created = service.save_memory(
        type=MemoryType.NOTE,
        content="test skill",
        tags=["skill"],
        title="Test Skill",
        content_type=ContentType.SKILL,
        metadata={"language": "python", "framework": "pytest", "version": "1.0"},
    )

    assert created.metadata == {"language": "python", "framework": "pytest", "version": "1.0"}

    fetched = service.get_memory(created.mem_id)
    assert fetched.metadata == {"language": "python", "framework": "pytest", "version": "1.0"}

    results = service.search_memory(query="test")
    assert results[0].metadata == {"language": "python", "framework": "pytest", "version": "1.0"}


def test_save_memory_with_title_and_content_type(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    created = service.save_memory(
        type=MemoryType.NOTE,
        content="## Heading\n\nbody text",
        tags=["docs"],
        title="Readme Draft",
        content_type=ContentType.MARKDOWN,
    )

    assert created.title == "Readme Draft"
    assert created.content_type is ContentType.MARKDOWN

    fetched = service.get_memory(created.mem_id)
    assert fetched.title == "Readme Draft"
    assert fetched.content_type is ContentType.MARKDOWN

    results = service.search_memory(query="Heading")
    assert results[0].title == "Readme Draft"
    assert results[0].content_type is ContentType.MARKDOWN


def test_full_memory_flow(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    session = service.start_session()
    created = service.save_memory(
        type=MemoryType.CONTEXT,
        content="repo uses duckdb backend first",
        tags=["architecture", "duckdb"],
    )

    fetched = service.get_memory(created.mem_id)
    results = service.search_memory(query="duckdb")
    ended = service.end_session(summary="seeded first memory")

    assert fetched.content == "repo uses duckdb backend first"
    assert [result.mem_id for result in results] == [created.mem_id]
    assert ended.id == session.id


def test_list_recent_sessions_orders_newest_first(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    first = service.start_session()
    service.end_session(summary="first")
    second = service.start_session()

    sessions = service.list_recent_sessions()

    assert sessions[0].id == second.id
    assert any(item.id == first.id for item in sessions)


def test_activate_unknown_session_raises(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    try:
        service.activate_session("missing-session")
    except SessionNotFoundError as exc:
        assert "Session not found" in str(exc)
    else:
        raise AssertionError("SessionNotFoundError not raised")


def test_get_unknown_memory_raises(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()

    try:
        service.get_memory("mem_dead")
    except MemoryNotFoundError as exc:
        assert "Memory not found" in str(exc)
    else:
        raise AssertionError("MemoryNotFoundError not raised")


def test_project_memory_flow(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    project = service.create_project(name="my-project", description="test project")

    session = service.start_session(project_id=project.id)
    created = service.save_memory(
        type=MemoryType.CONTEXT,
        content="project-level decision",
        tags=["decision", "project"],
    )

    fetched = service.get_memory(created.mem_id)
    project_results = service.search_memory(query="decision", project_scope=True)
    session_results = service.search_memory(query="decision")
    ended = service.end_session(summary="project work done")

    assert fetched.project_id == project.id
    assert len(project_results) == 1
    assert len(session_results) == 1
    assert ended.project_id == project.id


def test_project_scope_returns_empty_when_no_project(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.start_session()
    service.save_memory(type=MemoryType.NOTE, content="no project", tags=[])

    results = service.search_memory(query="no project", project_scope=True)
    assert results == []


def test_get_unknown_project_raises(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    with pytest.raises(ProjectNotFoundError, match=r"Project not found: missing"):
        service.get_project("missing")


def test_list_projects_returns_all(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    service.create_project(name="a")
    service.create_project(name="b")

    projects = service.list_projects()
    assert len(projects) == 2


def test_orphan_detection_marks_stale_session(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    storage.update_session_heartbeat(session.id)
    stale_since = datetime.now(UTC) + timedelta(seconds=1)
    import time
    time.sleep(0.01)

    stale = storage.list_stale_open_sessions(stale_since)
    assert len(stale) == 1
    assert stale[0].id == session.id

    summary = "Orphaned session with 0 memories"
    orphaned = storage.orphan_session(session.id, summary)
    assert orphaned.status is SessionStatus.ORPHANED
    assert orphaned.summary == summary


def test_service_orphan_detection_reclaims_stale_sessions(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    service = MemoryService(storage=storage)
    session = service.start_session()

    service.save_memory(type=MemoryType.NOTE, content="lost work", tags=[])
    service._stop_heartbeat()
    import time
    time.sleep(0.01)

    orphans = service.run_orphan_detection(threshold_minutes=0)
    assert len(orphans) == 1
    assert orphans[0].status is SessionStatus.ORPHANED
    assert "1 memories" in orphans[0].summary


def test_service_consolidate_projects(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    target = service.create_project(name="target")
    source = service.create_project(name="source")
    session = service.start_session(project_id=source.id)
    service.save_memory(type=MemoryType.NOTE, content="move me", tags=[])

    result = service.consolidate_projects(source_ids=[source.id], target_id=target.id)

    assert result.id == target.id
    assert result.name == "target"
    with pytest.raises(RuntimeError, match="Project not found"):
        service.get_project(source.id)
    results = service.search_memory(query="move", project_scope=True)
    assert len(results) == 1


def test_service_consolidate_projects_raises_for_missing_source(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    target = service.create_project(name="target")

    with pytest.raises(RuntimeError, match="Source project"):
        service.consolidate_projects(source_ids=["missing"], target_id=target.id)


def test_service_consolidate_projects_raises_for_missing_target(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))

    with pytest.raises(RuntimeError, match="Project not found"):
        service.consolidate_projects(source_ids=["any"], target_id="missing")


def test_service_consolidate_projects_raises_when_target_in_sources(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    target = service.create_project(name="target")

    with pytest.raises(RuntimeError, match="target project cannot be in source_ids"):
        service.consolidate_projects(source_ids=[target.id], target_id=target.id)


def test_service_consolidate_projects_raises_for_empty_sources(tmp_path: Path) -> None:
    service = MemoryService(storage=DuckDBStorage(tmp_path / "memory.duckdb"))
    target = service.create_project(name="target")

    with pytest.raises(RuntimeError, match="source_ids must not be empty"):
        service.consolidate_projects(source_ids=[], target_id=target.id)


def test_heartbeat_updates_session(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    original_hb = storage.get_session(session.id).last_heartbeat

    import time
    time.sleep(0.01)
    storage.update_session_heartbeat(session.id)
    updated_hb = storage.get_session(session.id).last_heartbeat

    assert updated_hb > original_hb


def test_smoke_script_runs_happy_path(tmp_path: Path) -> None:
    database_path = tmp_path / "smoke.duckdb"
    result = subprocess.run(
        [
            sys.executable,
            str(SMOKE_SCRIPT),
            "--database-path",
            str(database_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "smoke test passed" in result.stdout
