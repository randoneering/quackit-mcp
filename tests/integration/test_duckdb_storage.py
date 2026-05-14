from datetime import UTC
from pathlib import Path

import pytest

from quackit.models import (
    ContentType,
    MemoryCreate,
    MemoryType,
    MemoryUpdate,
    ProjectRecord,
    SessionStatus,
    SkillCreate,
)
from quackit.storage.duckdb import DuckDBStorage


def test_storage_bootstraps_schema_and_creates_session(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()

    assert session.status is SessionStatus.OPEN
    assert session.id
    assert session.project_id is None


def test_storage_create_project(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    project = storage.create_project(name="test", description="desc")

    assert project.name == "test"
    assert project.description == "desc"

    fetched = storage.get_project(project.id)
    assert fetched is not None
    assert fetched.name == "test"


def test_storage_session_with_project_id(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    project = storage.create_project(name="proj")
    session = storage.create_session(project_id=project.id)

    assert session.project_id == project.id

    fetched = storage.get_session(session.id)
    assert fetched is not None
    assert fetched.project_id == project.id


def test_storage_search_memories_by_project(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    project = storage.create_project(name="proj")
    session = storage.create_session(project_id=project.id)
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE, content="project memory", tags=["proj"]
        ),
    )

    results = storage.search_memories_by_project(
        project.id, query="project", memory_type=None
    )
    assert len(results) == 1
    assert results[0].tags == ["proj"]


def test_storage_memory_inherits_project_id_from_session(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
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


def test_storage_saves_gets_and_searches_memory(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="postgres migration fixed",
            tags=["postgres", "migration"],
        ),
    )

    fetched = storage.get_memory(created.mem_id)
    results = storage.search_memories(session.id, query="postgres", memory_type=None)

    assert fetched.mem_id == created.mem_id
    assert fetched.tags == ["postgres", "migration"]
    assert [result.mem_id for result in results] == [created.mem_id]


def test_save_memory_fails_for_missing_session(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")

    with pytest.raises(RuntimeError, match=r"^Session not found: missing-session$"):
        storage.save_memory(
            session_id="missing-session",
            memory=MemoryCreate(type=MemoryType.NOTE, content="orphan memory", tags=[]),
        )


def test_save_memory_fails_for_closed_session(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    storage.end_session(session.id, summary="done")

    with pytest.raises(RuntimeError, match=r"Session is closed: .*cannot save memory"):
        storage.save_memory(
            session_id=session.id,
            memory=MemoryCreate(
                type=MemoryType.NOTE, content="closed session write", tags=[]
            ),
        )


def test_search_memory_empty_query_returns_all(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="first", tags=["a"]),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.CONTEXT, content="second", tags=["b"]),
    )

    results = storage.search_memories(session.id, query="", memory_type=None)
    assert len(results) == 2


def test_search_memory_default_limit(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    for i in range(105):
        storage.save_memory(
            session_id=session.id,
            memory=MemoryCreate(type=MemoryType.NOTE, content=f"limited {i}", tags=[]),
        )

    results = storage.search_memories(session.id, query="limited", memory_type=None)

    assert len(results) == 100


def test_count_memories_returns_session_count(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    other = storage.create_session()
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="first", tags=[]),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="second", tags=[]),
    )
    storage.save_memory(
        session_id=other.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="other", tags=[]),
    )

    assert storage.count_memories(session.id) == 2


def test_search_memory_with_percent_in_query(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE, content="50% completion rate", tags=[]
        ),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE, content="fifty percent done", tags=[]
        ),
    )

    results_percent = storage.search_memories(session.id, query="%", memory_type=None)
    results_fifty = storage.search_memories(session.id, query="fifty", memory_type=None)

    assert len(results_percent) == 2
    assert len(results_fifty) == 1


def test_search_memory_with_underscore_in_query(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="item_1 status", tags=[]),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="itemX1 status", tags=[]),
    )

    results = storage.search_memories(session.id, query="item_1", memory_type=None)
    assert len(results) == 2


def test_search_memory_with_special_regex_chars(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE, content="price is $10.99 (incl. tax)", tags=["dollar"]
        ),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE, content="price is [discounted]", tags=[]
        ),
    )

    results_dollar = storage.search_memories(
        session.id, query="$10.99", memory_type=None
    )
    results_bracket = storage.search_memories(
        session.id, query="[discounted]", memory_type=None
    )

    assert len(results_dollar) == 1
    assert len(results_bracket) == 1


def test_storage_consolidate_projects_moves_sessions_and_memories(
    tmp_path: Path,
) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    target = storage.create_project(name="target")
    source = storage.create_project(name="source")
    session = storage.create_session(project_id=source.id)
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="move me", tags=[]),
    )

    result = storage.consolidate_projects(source_ids=[source.id], target_id=target.id)

    assert result.id == target.id
    assert storage.get_project(source.id) is None
    moved_session = storage.get_session(session.id)
    assert moved_session is not None
    assert moved_session.project_id == target.id
    results = storage.search_memories_by_project(
        target.id, query="move", memory_type=None
    )
    assert len(results) == 1


def test_storage_consolidate_projects_raises_for_missing_source(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    target = storage.create_project(name="target")

    with pytest.raises(RuntimeError, match="Source project"):
        storage.consolidate_projects(source_ids=["missing-source"], target_id=target.id)


def test_storage_consolidate_projects_raises_for_missing_target(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")

    with pytest.raises(RuntimeError, match="Target project not found"):
        storage.consolidate_projects(source_ids=["any"], target_id="missing-target")


def test_storage_consolidate_projects_handles_empty_source(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    target = storage.create_project(name="target")
    empty_source = storage.create_project(name="empty")

    result = storage.consolidate_projects(
        source_ids=[empty_source.id], target_id=target.id
    )

    assert result.id == target.id
    assert storage.get_project(empty_source.id) is None


def test_storage_consolidate_projects_multiple_sources(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    target = storage.create_project(name="target")
    src_a = storage.create_project(name="a")
    src_b = storage.create_project(name="b")
    ses_a = storage.create_session(project_id=src_a.id)
    ses_b = storage.create_session(project_id=src_b.id)
    storage.save_memory(
        session_id=ses_a.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="from a", tags=[]),
    )
    storage.save_memory(
        session_id=ses_b.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="from b", tags=[]),
    )

    storage.consolidate_projects(source_ids=[src_a.id, src_b.id], target_id=target.id)

    assert storage.get_project(src_a.id) is None
    assert storage.get_project(src_b.id) is None
    assert (
        len(storage.search_memories_by_project(target.id, query="", memory_type=None))
        == 2
    )


def test_storage_save_memory_with_title_and_content_type(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="def foo(): pass",
            tags=["python"],
            title="Foo function",
            content_type=ContentType.CODE,
        ),
    )

    assert created.title == "Foo function"
    assert created.content_type is ContentType.CODE

    fetched = storage.get_memory(created.mem_id)
    assert fetched is not None
    assert fetched.title == "Foo function"
    assert fetched.content_type is ContentType.CODE

    results = storage.search_memories(session.id, query="foo", memory_type=None)
    assert results[0].title == "Foo function"
    assert results[0].content_type is ContentType.CODE

    results_by_project = (
        storage.search_memories_by_project(
            session.project_id, query="foo", memory_type=None
        )
        if session.project_id
        else []
    )
    if session.project_id:
        assert results_by_project[0].content_type is ContentType.CODE


def test_storage_save_memory_with_metadata(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
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

    assert created.metadata == {
        "language": "python",
        "framework": "pytest",
        "version": "1.0",
    }

    fetched = storage.get_memory(created.mem_id)
    assert fetched is not None
    assert fetched.metadata == {
        "language": "python",
        "framework": "pytest",
        "version": "1.0",
    }

    results = storage.search_memories(session.id, query="skill", memory_type=None)
    assert results[0].metadata == {
        "language": "python",
        "framework": "pytest",
        "version": "1.0",
    }


def test_storage_update_memory_metadata(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE, content="original", tags=[], metadata={"old": "data"}
        ),
    )

    updated = storage.update_memory(
        created.mem_id, MemoryUpdate(metadata={"language": "go"})
    )

    assert updated.metadata == {"language": "go"}


def test_storage_update_memory_metadata_partial(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="original",
            tags=["keep"],
            metadata={"old": "data"},
        ),
    )

    updated = storage.update_memory(
        created.mem_id, MemoryUpdate(content="new content only")
    )

    assert updated.metadata == {"old": "data"}
    assert updated.content == "new content only"
    assert updated.tags == ["keep"]


def test_update_memory_updates_fields(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="original",
            tags=["a"],
            title="orig",
            content_type=ContentType.NOTE,
        ),
    )

    updated = storage.update_memory(
        created.mem_id,
        MemoryUpdate(
            content="updated",
            tags=["b", "c"],
            title="new title",
            content_type=ContentType.CODE,
        ),
    )

    assert updated.content == "updated"
    assert updated.tags == ["b", "c"]
    assert updated.title == "new title"
    assert updated.content_type is ContentType.CODE
    assert updated.mem_id == created.mem_id

    fetched = storage.get_memory(created.mem_id)
    assert fetched is not None
    assert fetched.content == "updated"


def test_update_memory_partial_update(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE, content="original", tags=["a"], title="orig"
        ),
    )

    updated = storage.update_memory(
        created.mem_id, MemoryUpdate(content="only content changed")
    )

    assert updated.content == "only content changed"
    assert updated.tags == ["a"]
    assert updated.title == "orig"


def test_update_memory_no_op_returns_existing(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    created = storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="stay", tags=[]),
    )

    updated = storage.update_memory(created.mem_id, MemoryUpdate())

    assert updated.content == "stay"
    assert updated.mem_id == created.mem_id


def test_update_memory_raises_for_missing(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    with pytest.raises(RuntimeError, match=r"Memory not found: mem_dead"):
        storage.update_memory("mem_dead", MemoryUpdate(content="nope"))


def test_search_memories_filters_by_content_type(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    session = storage.create_session()
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="def foo(): pass",
            tags=["python"],
            content_type=ContentType.CODE,
        ),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="# Heading\n\nbody",
            tags=["docs"],
            content_type=ContentType.MARKDOWN,
        ),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(type=MemoryType.NOTE, content="plain note", tags=["misc"]),
    )

    code_results = storage.search_memories(
        session.id, query="", memory_type=None, content_type="code"
    )
    markdown_results = storage.search_memories(
        session.id, query="", memory_type=None, content_type="markdown"
    )
    skill_results = storage.search_memories(
        session.id, query="", memory_type=None, content_type="skill"
    )
    all_results = storage.search_memories(session.id, query="", memory_type=None)

    assert len(code_results) == 1
    assert code_results[0].content_type is ContentType.CODE
    assert len(markdown_results) == 1
    assert markdown_results[0].content_type is ContentType.MARKDOWN
    assert len(skill_results) == 0
    assert len(all_results) == 3


def test_search_memories_by_project_filters_by_content_type(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    project = storage.create_project(name="proj")
    session = storage.create_session(project_id=project.id)
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="def bar(): pass",
            tags=["python"],
            content_type=ContentType.CODE,
        ),
    )
    storage.save_memory(
        session_id=session.id,
        memory=MemoryCreate(
            type=MemoryType.NOTE,
            content="## Docs",
            tags=["docs"],
            content_type=ContentType.MARKDOWN,
        ),
    )

    code_results = storage.search_memories_by_project(
        project.id, query="", memory_type=None, content_type="code"
    )
    markdown_results = storage.search_memories_by_project(
        project.id, query="", memory_type=None, content_type="markdown"
    )

    assert len(code_results) == 1
    assert code_results[0].content_type is ContentType.CODE
    assert len(markdown_results) == 1
    assert markdown_results[0].content_type is ContentType.MARKDOWN


def test_storage_save_and_get_skill(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    created = storage.save_skill(
        SkillCreate(
            name="test-skill",
            description="A test",
            content="print('hello')",
            tags=["python", "test"],
            source="/tmp/test.py",
        ),
    )

    assert created.name == "test-skill"
    assert created.description == "A test"
    assert created.content == "print('hello')"
    assert created.tags == ["python", "test"]
    assert created.source == "/tmp/test.py"
    assert created.skill_id.startswith("sk_")

    fetched = storage.get_skill(created.skill_id)
    assert fetched is not None
    assert fetched.name == "test-skill"
    assert fetched.tags == ["python", "test"]


def test_storage_get_skill_returns_none_for_missing(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    assert storage.get_skill("sk_nonexistent") is None


def test_storage_update_skill(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    from quackit.models import SkillUpdate

    created = storage.save_skill(
        SkillCreate(name="original", content="original content", tags=["a"])
    )
    updated = storage.update_skill(
        created.skill_id, SkillUpdate(name="updated", content="new content", tags=["b"])
    )

    assert updated.name == "updated"
    assert updated.content == "new content"
    assert updated.tags == ["b"]
    assert updated.skill_id == created.skill_id


def test_storage_update_skill_partial(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    from quackit.models import SkillUpdate

    created = storage.save_skill(
        SkillCreate(
            name="original", content="content", tags=["keep"], description="desc"
        )
    )
    updated = storage.update_skill(created.skill_id, SkillUpdate(name="new name"))

    assert updated.name == "new name"
    assert updated.content == "content"
    assert updated.tags == ["keep"]
    assert updated.description == "desc"


def test_storage_update_skill_raises_for_missing(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    from quackit.models import SkillUpdate

    with pytest.raises(RuntimeError, match=r"Skill not found"):
        storage.update_skill("sk_dead", SkillUpdate(name="nope"))


def test_storage_delete_skill(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    created = storage.save_skill(SkillCreate(name="delete-me", content="bye"))
    storage.delete_skill(created.skill_id)
    assert storage.get_skill(created.skill_id) is None


def test_storage_list_skills(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
    s1 = storage.save_skill(SkillCreate(name="alpha", content="aaa", tags=["python"]))
    s2 = storage.save_skill(SkillCreate(name="beta", content="bbb", tags=["go"]))
    s3 = storage.save_skill(
        SkillCreate(name="gamma", content="ccc", tags=["python", "cli"])
    )

    all_skills = storage.list_skills()
    assert len(all_skills) == 3

    query_results = storage.list_skills(query="alpha")
    assert len(query_results) == 1
    assert query_results[0].skill_id == s1.skill_id

    tag_results = storage.list_skills(tag="python")
    assert len(tag_results) == 2

    no_results = storage.list_skills(query="zzzzz")
    assert len(no_results) == 0


def test_storage_preserves_utc_timestamps_on_round_trip(tmp_path: Path) -> None:
    storage = DuckDBStorage(tmp_path / "memory.duckdb")
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
