from __future__ import annotations

from pathlib import Path

import pytest

from quackit._validation import ValidationError
from quackit.server_stdio import build_server


@pytest.fixture(autouse=True)
def _clear_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUACKIT_DATABASE_URL", raising=False)
    monkeypatch.delenv("AGENT_MEMORY_DATABASE_URL", raising=False)


def _find_tool(server, name: str):
    for key, value in server._local_provider._components.items():
        if key.startswith(f"tool:{name}"):
            return value
    return None


def test_save_memory_rejects_empty_content(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "save_memory")

    with pytest.raises(ValidationError, match="content must not be empty"):
        tool.fn(type="note", content="", tags=[])


def test_save_memory_rejects_oversized_content(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "save_memory")

    with pytest.raises(ValidationError, match="content exceeds"):
        tool.fn(type="note", content="x" * 100_001, tags=[])


def test_search_memory_rejects_oversized_query(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "search_memory")

    with pytest.raises(ValidationError, match="query exceeds"):
        tool.fn(query="x" * 501, type=None, project_scope=False)


def test_create_project_rejects_empty_name(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "create_project")

    with pytest.raises(ValidationError, match="name must not be empty"):
        tool.fn(name="", description=None)


def test_create_project_rejects_long_name(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "create_project")

    with pytest.raises(ValidationError, match="name exceeds"):
        tool.fn(name="x" * 201, description=None)


def test_save_memory_rejects_too_many_tags(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    tool = _find_tool(server, "save_memory")

    with pytest.raises(ValidationError, match="tags exceeds"):
        tool.fn(type="note", content="tag overload", tags=["x"] * 51)


def test_save_memory_rejects_tag_too_long(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    tool = _find_tool(server, "save_memory")

    with pytest.raises(ValidationError, match="tag exceeds"):
        tool.fn(type="note", content="long tag", tags=["x" * 201])


def test_end_session_without_active_session(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "end_session")

    with pytest.raises(RuntimeError, match="No active session"):
        tool.fn(summary="orphan end")


def test_save_memory_without_active_session(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "save_memory")

    with pytest.raises(RuntimeError, match="No active session"):
        tool.fn(type="note", content="no session", tags=[])


def test_search_memory_without_active_session(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "search_memory")

    with pytest.raises(RuntimeError, match="No active session"):
        tool.fn(query="anything", type=None, project_scope=False)


def test_get_memory_with_unknown_id(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    tool = _find_tool(server, "get_memory")

    with pytest.raises(RuntimeError, match="Memory not found"):
        tool.fn(mem_id="mem_deadbeef")


def test_activate_session_with_unknown_id(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "activate_session")

    with pytest.raises(RuntimeError, match="Session not found"):
        tool.fn(session_id="missing-session")


def test_start_session_with_unknown_project(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "start_session")

    with pytest.raises(RuntimeError, match="Project not found"):
        tool.fn(project_id="missing-project")


def test_save_memory_with_metadata(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    tool = _find_tool(server, "save_memory")

    result = tool.fn(type="note", content="skill content", tags=["skill"], title="My Skill", content_type="skill", metadata={"language": "python", "framework": "pytest"})

    assert result["metadata"] == {"language": "python", "framework": "pytest"}


def test_update_memory_with_metadata(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    save = _find_tool(server, "save_memory")
    saved = save.fn(type="note", content="original", tags=[])
    mem_id = saved["mem_id"]

    tool = _find_tool(server, "update_memory")
    result = tool.fn(mem_id=mem_id, metadata={"language": "rust"})

    assert result["metadata"] == {"language": "rust"}


def test_update_memory_updates_content(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    save = _find_tool(server, "save_memory")
    saved = save.fn(type="note", content="original", tags=["a"], title="orig", content_type="note")
    mem_id = saved["mem_id"]

    tool = _find_tool(server, "update_memory")
    result = tool.fn(mem_id=mem_id, content="updated", tags=["b"], title="new title", content_type="code")

    assert result["content"] == "updated"
    assert result["tags"] == ["b"]
    assert result["title"] == "new title"
    assert result["content_type"] == "code"
    assert result["mem_id"] == mem_id


def test_update_memory_partial(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    save = _find_tool(server, "save_memory")
    saved = save.fn(type="note", content="original", tags=["a"], title="orig")
    mem_id = saved["mem_id"]

    tool = _find_tool(server, "update_memory")
    result = tool.fn(mem_id=mem_id, content="only content changed")

    assert result["content"] == "only content changed"
    assert result["tags"] == ["a"]
    assert result["title"] == "orig"


def test_update_memory_rejects_unknown_mem_id(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    tool = _find_tool(server, "update_memory")

    with pytest.raises(RuntimeError, match=r"Memory not found: mem_dead"):
        tool.fn(mem_id="mem_dead", content="nope")


def test_search_memory_accepts_content_type_filter(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    save = _find_tool(server, "save_memory")
    save.fn(type="note", content="def foo(): pass", tags=[], title="func", content_type="code")
    save.fn(type="note", content="# Docs", tags=[], title="readme", content_type="markdown")
    save.fn(type="note", content="plain", tags=[])

    tool = _find_tool(server, "search_memory")
    code_results = tool.fn(query="", type=None, project_scope=False, content_type="code")
    md_results = tool.fn(query="", type=None, project_scope=False, content_type="markdown")
    skill_results = tool.fn(query="", type=None, project_scope=False, content_type="skill")

    assert len(code_results) == 1
    assert code_results[0]["content_type"] == "code"
    assert len(md_results) == 1
    assert md_results[0]["content_type"] == "markdown"
    assert len(skill_results) == 0


def test_search_memory_rejects_invalid_content_type(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool = _find_tool(server, "search_memory")

    with pytest.raises(ValueError, match="'invalid' is not a valid ContentType"):
        tool.fn(query="test", type=None, project_scope=False, content_type="invalid")


def test_save_memory_rejects_invalid_content_type(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    _find_tool(server, "start_session").fn(project_id=None)
    tool = _find_tool(server, "save_memory")

    with pytest.raises(ValueError, match="'invalid' is not a valid ContentType"):
        tool.fn(type="note", content="test", tags=[], title=None, content_type="invalid")


def test_consolidate_projects_moves_data(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    create = _find_tool(server, "create_project")
    target = create.fn(name="target")
    source = create.fn(name="source")
    start = _find_tool(server, "start_session")
    start.fn(project_id=source["id"])
    save = _find_tool(server, "save_memory")
    save.fn(type="note", content="consolidate me", tags=[])

    tool = _find_tool(server, "consolidate_projects")
    result = tool.fn(source_ids=[source["id"]], target_id=target["id"])

    assert result["id"] == target["id"]
    projects = _find_tool(server, "list_projects").fn()
    assert [p["id"] for p in projects] == [target["id"]]
    search = _find_tool(server, "search_memory")
    results = search.fn(query="consolidate", type=None, project_scope=False)
    assert len(results) == 1


def test_consolidate_projects_rejects_missing_source(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    create = _find_tool(server, "create_project")
    target = create.fn(name="target")

    tool = _find_tool(server, "consolidate_projects")
    with pytest.raises(RuntimeError, match="Source project"):
        tool.fn(source_ids=["missing"], target_id=target["id"])


def test_consolidate_projects_rejects_missing_target(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    create = _find_tool(server, "create_project")
    source = create.fn(name="source")

    tool = _find_tool(server, "consolidate_projects")
    with pytest.raises(RuntimeError, match="Project not found"):
        tool.fn(source_ids=[source["id"]], target_id="missing")
