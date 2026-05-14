from datetime import datetime

from pydantic import ValidationError

from quackit.models import ContentType, MemoryCreate, MemoryType, SearchResult, ProjectRecord, SearchResult, build_mem_id


def test_content_type_has_expected_values() -> None:
    assert ContentType.NOTE.value == "note"
    assert ContentType.CODE.value == "code"
    assert ContentType.MARKDOWN.value == "markdown"
    assert ContentType.SKILL.value == "skill"


def test_memory_create_accepts_title_and_content_type() -> None:
    memory = MemoryCreate(
        type=MemoryType.NOTE,
        content="hello",
        tags=[],
        title="My Title",
        content_type=ContentType.CODE,
    )
    assert memory.title == "My Title"
    assert memory.content_type is ContentType.CODE


def test_memory_create_defaults_title_and_content_type_to_none() -> None:
    memory = MemoryCreate(type=MemoryType.NOTE, content="hello", tags=[])
    assert memory.title is None
    assert memory.content_type is None
    assert memory.metadata == {}


def test_memory_create_accepts_metadata() -> None:
    memory = MemoryCreate(type=MemoryType.NOTE, content="hello", tags=[], metadata={"language": "python"})
    assert memory.metadata == {"language": "python"}


def test_memory_create_accepts_valid_type() -> None:
    memory = MemoryCreate(type=MemoryType.NOTE, content="remember this", tags=["alpha"])
    assert memory.type is MemoryType.NOTE


def test_memory_create_rejects_invalid_type() -> None:
    try:
        MemoryCreate(type="bad", content="oops", tags=[])
    except ValidationError as exc:
        assert "Input should be 'context', 'summary', 'error_fix' or 'note'" in str(exc)
    else:
        raise AssertionError("ValidationError not raised")


def test_build_mem_id_has_expected_shape() -> None:
    mem_id = build_mem_id()
    assert mem_id.startswith("mem_")
    assert len(mem_id) == 12


def test_project_record_accepts_optional_description() -> None:
    project = ProjectRecord(id="proj_1", name="my project", description=None, created_at=datetime.now())
    assert project.name == "my project"
    assert project.description is None

    with_desc = ProjectRecord(id="proj_2", name="with desc", description="some description", created_at=datetime.now())
    assert with_desc.description == "some description"


def test_search_result_snippet_truncates_long_content() -> None:
    result = SearchResult.from_content(
        mem_id="mem_ab12",
        type=MemoryType.NOTE,
        content="x" * 140,
        tags=["long"],
        created_at="2026-05-08T00:00:00",
    )
    assert result.snippet.endswith("...")
    assert len(result.snippet) == 123
