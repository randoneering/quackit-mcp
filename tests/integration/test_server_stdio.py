from pathlib import Path

import pytest

from quackit.server_stdio import build_server, create_tool_context


def _tool_functions(server) -> dict[str, object]:
    return {
        key.removeprefix("tool:").rstrip("@"): component.fn
        for key, component in server._local_provider._components.items()
        if key.startswith("tool:")
    }


def _tool_components(server) -> dict[str, object]:
    return {
        key.removeprefix("tool:").rstrip("@"): component for key, component in server._local_provider._components.items() if key.startswith("tool:")
    }


def test_create_tool_context_uses_explicit_database_path(tmp_path: Path) -> None:
    context = create_tool_context(database_path=tmp_path / "mcp.duckdb")

    assert context.database_path == tmp_path / "mcp.duckdb"
    assert context.service is not None


def test_build_server_registers_expected_tools(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool_names = sorted(key.removeprefix("tool:").rstrip("@") for key in server._local_provider._components if key.startswith("tool:"))

    assert tool_names == [
        "activate_session",
        "consolidate_projects",
        "create_project",
        "delete_skill",
        "end_session",
        "get_memory",
        "get_skill",
        "list_projects",
        "list_recent_sessions",
        "list_sessions_by_project",
        "list_skills",
        "save_memory",
        "save_skill",
        "search_memory",
        "start_session",
        "update_memory",
        "update_skill",
    ]


def test_build_server_registers_tool_annotations(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tools = _tool_components(server)

    read_only_tools = {
        "list_projects",
        "list_recent_sessions",
        "list_sessions_by_project",
        "get_memory",
        "search_memory",
        "get_skill",
        "list_skills",
    }
    write_tools = {
        "create_project",
        "start_session",
        "activate_session",
        "end_session",
        "save_memory",
        "update_memory",
        "save_skill",
        "update_skill",
    }
    destructive_tools = {"delete_skill", "consolidate_projects"}

    for name in read_only_tools:
        annotations = tools[name].annotations
        assert annotations.readOnlyHint is True
        assert annotations.openWorldHint is False

    for name in write_tools:
        annotations = tools[name].annotations
        assert annotations.readOnlyHint is False
        assert annotations.destructiveHint is False
        assert annotations.openWorldHint is False

    for name in destructive_tools:
        annotations = tools[name].annotations
        assert annotations.readOnlyHint is False
        assert annotations.destructiveHint is True
        assert annotations.openWorldHint is False


def test_memory_tools_expose_enum_input_schemas(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tools = _tool_components(server)

    save_memory_params = tools["save_memory"].parameters["properties"]
    search_memory_params = tools["search_memory"].parameters["properties"]

    assert save_memory_params["type"]["enum"] == [
        "context",
        "summary",
        "error_fix",
        "note",
    ]
    assert save_memory_params["content_type"]["anyOf"][0]["enum"] == [
        "note",
        "code",
        "markdown",
        "skill",
    ]
    assert search_memory_params["type"]["anyOf"][0]["enum"] == [
        "context",
        "summary",
        "error_fix",
        "note",
    ]


def test_list_skills_returns_bounded_summaries(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tools = _tool_functions(server)

    tools["save_skill"]("alpha", "A" * 10, description="first")
    tools["save_skill"]("bravo", "B" * 20, description="second")
    tools["save_skill"]("charlie", "C" * 30, description="third")

    result = tools["list_skills"]("", None, 2)

    assert len(result) == 2
    assert all("content" not in item for item in result)
    assert sorted(item["content_length"] for item in result) == [20, 30]


def test_list_skills_rejects_invalid_limit(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tools = _tool_functions(server)

    with pytest.raises(ValueError, match="limit must be between"):
        tools["list_skills"]("", None, 0)


def test_get_skill_paginates_large_content(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tools = _tool_functions(server)
    skill = tools["save_skill"]("large", "abcdef", description="large")

    first_page = tools["get_skill"](skill["skill_id"], max_chars=3)
    second_page = tools["get_skill"](skill["skill_id"], max_chars=3, offset=first_page["next_offset"])

    assert first_page["content"] == "abc"
    assert first_page["content_length"] == 6
    assert first_page["truncated"] is True
    assert first_page["next_offset"] == 3
    assert second_page["content"] == "def"
    assert second_page["truncated"] is False
    assert second_page["next_offset"] is None
