from pathlib import Path

from quackit.server_stdio import build_server, create_tool_context


def test_create_tool_context_uses_explicit_database_path(tmp_path: Path) -> None:
    context = create_tool_context(database_path=tmp_path / "mcp.duckdb")

    assert context.database_path == tmp_path / "mcp.duckdb"
    assert context.service is not None


def test_build_server_registers_expected_tools(tmp_path: Path) -> None:
    server = build_server(database_path=tmp_path / "mcp.duckdb")
    tool_names = sorted(
        key.removeprefix("tool:").rstrip("@")
        for key in server._local_provider._components
        if key.startswith("tool:")
    )

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
