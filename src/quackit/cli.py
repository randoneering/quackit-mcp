from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from quackit._validation import validate_content, validate_name, validate_query, validate_tags
from quackit.bootstrap import create_app_context
from quackit.models import ContentType, MemoryType

log = logging.getLogger(__name__)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def _dump(data: dict[str, Any] | list[dict[str, Any]]) -> None:
    print(json.dumps(_to_jsonable(data), indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quackit", description="Session-scoped agent memory MCP server")
    parser.add_argument("--database-path", type=Path, required=True, help="Path to DuckDB database file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start-session", help="Start a new memory session")
    start_parser.add_argument("--project-id", help="Optional project ID to associate session with")

    list_parser = subparsers.add_parser("list-sessions", help="List recent sessions")
    list_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    activate_parser = subparsers.add_parser("activate-session", help="Activate an existing session")
    activate_parser.add_argument("session_id", help="Session ID to activate")

    save_parser = subparsers.add_parser("save-memory", help="Save a memory in the active session")
    save_parser.add_argument("--session-id", required=True, help="Session ID to save memory to")
    save_parser.add_argument("--type", choices=[member.value for member in MemoryType], required=True, help="Memory type (context|summary|error_fix|note)")
    save_parser.add_argument("--content", required=True, help="Memory content")
    save_parser.add_argument("--title", help="Optional title for the memory")
    save_parser.add_argument("--content-type", choices=[member.value for member in ContentType], help="Content format hint (note|code|markdown|skill)")
    save_parser.add_argument("--tag", action="append", default=[], help="Tag to attach (repeatable)")
    save_parser.add_argument("--metadata", type=json.loads, default=None, help="JSON dict of structured metadata (e.g. '{\"language\":\"python\",\"framework\":\"pytest\"}')")

    search_parser = subparsers.add_parser("search-memory", help="Search memories in the active session")
    search_parser.add_argument("query", help="Search query text")
    search_parser.add_argument("--session-id", required=True, help="Session ID to search within")
    search_parser.add_argument("--type", choices=[member.value for member in MemoryType], help="Filter by memory type")
    search_parser.add_argument("--content-type", choices=[member.value for member in ContentType], help="Filter by content type (note|code|markdown|skill)")
    search_parser.add_argument("--project-scope", action="store_true", default=False, help="Search across entire project")

    update_parser = subparsers.add_parser("update-memory", help="Update a memory's fields")
    update_parser.add_argument("mem_id", help="Memory ID to update")
    update_parser.add_argument("--session-id", required=True, help="Session ID owning the memory")
    update_parser.add_argument("--content", help="New content")
    update_parser.add_argument("--title", help="New title")
    update_parser.add_argument("--content-type", choices=[member.value for member in ContentType], help="New content type")
    update_parser.add_argument("--tag", action="append", default=[], help="Replace tags with this list (repeatable) — provide --tag to set tags, omit to leave unchanged")
    update_parser.add_argument("--metadata", type=json.loads, default=None, help="JSON dict of structured metadata (e.g. '{\"language\":\"python\",\"framework\":\"pytest\"}') — provide to set, omit to leave unchanged")

    get_parser = subparsers.add_parser("get-memory", help="Get a specific memory by mem_id")
    get_parser.add_argument("mem_id", help="Memory ID to retrieve")

    end_parser = subparsers.add_parser("end-session", help="End the active session with a summary")
    end_parser.add_argument("--session-id", required=True, help="Session ID to end")
    end_parser.add_argument("--summary", required=True, help="Summary of the session")

    create_project_parser = subparsers.add_parser("create-project", help="Create a new project")
    create_project_parser.add_argument("name", help="Project name")
    create_project_parser.add_argument("--description", help="Optional project description")

    consolidate_parser = subparsers.add_parser("consolidate-projects", help="Consolidate multiple projects into one")
    consolidate_parser.add_argument("--source-ids", nargs="+", required=True, help="Project IDs to consolidate from")
    consolidate_parser.add_argument("--target-id", required=True, help="Project ID to consolidate into")

    subparsers.add_parser("list-projects", help="List all projects")

    list_sessions_parser = subparsers.add_parser("list-sessions-by-project", help="List sessions for a project")
    list_sessions_parser.add_argument("project_id", help="Project ID to list sessions for")

    save_skill_parser = subparsers.add_parser("save-skill", help="Save a skill")
    save_skill_parser.add_argument("--name", required=True, help="Skill name")
    save_skill_parser.add_argument("--description", help="Short description")
    save_skill_parser.add_argument("--content", required=True, help="Skill instructions/content")
    save_skill_parser.add_argument("--tag", action="append", default=[], help="Tag to attach (repeatable)")
    save_skill_parser.add_argument("--source", help="Optional source path")

    get_skill_parser = subparsers.add_parser("get-skill", help="Get a skill by ID")
    get_skill_parser.add_argument("skill_id", help="Skill ID to retrieve")

    update_skill_parser = subparsers.add_parser("update-skill", help="Update a skill's fields")
    update_skill_parser.add_argument("skill_id", help="Skill ID to update")
    update_skill_parser.add_argument("--name", help="New name")
    update_skill_parser.add_argument("--description", help="New description")
    update_skill_parser.add_argument("--content", help="New content")
    update_skill_parser.add_argument("--tag", action="append", default=None, help="Replace tags with this list (repeatable)")
    update_skill_parser.add_argument("--source", help="New source path")

    delete_skill_parser = subparsers.add_parser("delete-skill", help="Delete a skill")
    delete_skill_parser.add_argument("skill_id", help="Skill ID to delete")

    list_skills_parser = subparsers.add_parser("list-skills", help="List skills")
    list_skills_parser.add_argument("--query", default="", help="Search query")
    list_skills_parser.add_argument("--tag", help="Filter by tag")

    serve_parser = subparsers.add_parser("serve", help="Start the MCP server")
    serve_parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http", "streamable-http"],
        default="stdio",
        help="MCP transport protocol (default: stdio)",
    )
    serve_parser.add_argument("--host", default=None, help="Host to bind (SSE/HTTP only)")
    serve_parser.add_argument("--port", type=int, default=None, help="Port to bind (SSE/HTTP only)")

    return parser


def main() -> int:
    from quackit._logging import setup_logging
    setup_logging()
    args = build_parser().parse_args()
    context = create_app_context(database_path=args.database_path)
    service = context.service
    log.info("CLI command: %s", args.command)

    try:
        if args.command == "start-session":
            _dump(service.start_session(project_id=args.project_id).model_dump())
            return 0

        if args.command == "list-sessions":
            _dump([item.model_dump() for item in service.list_recent_sessions(limit=args.limit)])
            return 0

        if args.command == "activate-session":
            _dump(service.activate_session(args.session_id).model_dump())
            return 0

        if args.command == "save-memory":
            validate_content(args.content)
            validate_tags(args.tag)
            service.activate_session(args.session_id)
            content_type = None if args.content_type is None else ContentType(args.content_type)
            _dump(
                service.save_memory(
                    type=MemoryType(args.type),
                    content=args.content,
                    tags=args.tag,
                    title=args.title,
                    content_type=content_type,
                    metadata=args.metadata,
                ).model_dump()
            )
            return 0

        if args.command == "search-memory":
            validate_query(args.query)
            service.activate_session(args.session_id)
            memory_type = None if args.type is None else MemoryType(args.type)
            content_type = None if args.content_type is None else ContentType(args.content_type)
            _dump([item.model_dump() for item in service.search_memory(query=args.query, type=memory_type, content_type=content_type, project_scope=args.project_scope)])
            return 0

        if args.command == "update-memory":
            service.activate_session(args.session_id)
            content_type = None if args.content_type is None else ContentType(args.content_type)
            tags = args.tag if args.tag else None
            _dump(
                service.update_memory(
                    mem_id=args.mem_id,
                    content=args.content,
                    tags=tags,
                    title=args.title,
                    content_type=content_type,
                    metadata=args.metadata,
                ).model_dump()
            )
            return 0

        if args.command == "get-memory":
            _dump(service.get_memory(args.mem_id).model_dump())
            return 0

        if args.command == "end-session":
            service.activate_session(args.session_id)
            _dump(service.end_session(summary=args.summary).model_dump())
            return 0

        if args.command == "create-project":
            validate_name(args.name)
            _dump(service.create_project(name=args.name, description=args.description).model_dump())
            return 0

        if args.command == "consolidate-projects":
            _dump(service.consolidate_projects(source_ids=args.source_ids, target_id=args.target_id).model_dump())
            return 0

        if args.command == "list-projects":
            _dump([item.model_dump() for item in service.list_projects()])
            return 0

        if args.command == "list-sessions-by-project":
            _dump([item.model_dump() for item in service.list_sessions_by_project(args.project_id)])
            return 0

        if args.command == "save-skill":
            _dump(
                service.save_skill(
                    name=args.name,
                    description=args.description,
                    content=args.content,
                    tags=args.tag,
                    source=args.source,
                ).model_dump()
            )
            return 0

        if args.command == "get-skill":
            _dump(service.get_skill(args.skill_id).model_dump())
            return 0

        if args.command == "update-skill":
            tags = args.tag if args.tag else None
            _dump(
                service.update_skill(
                    skill_id=args.skill_id,
                    name=args.name,
                    description=args.description,
                    content=args.content,
                    tags=tags,
                    source=args.source,
                ).model_dump()
            )
            return 0

        if args.command == "delete-skill":
            service.delete_skill(args.skill_id)
            _dump({"deleted": args.skill_id})
            return 0

        if args.command == "list-skills":
            _dump([item.model_dump() for item in service.list_skills(query=args.query, tag=args.tag)])
            return 0

        if args.command == "serve":
            from quackit.server_stdio import build_server
            kwargs: dict[str, object] = {}
            if args.host is not None:
                kwargs["host"] = args.host
            if args.port is not None:
                kwargs["port"] = args.port
            build_server(database_path=args.database_path).run(transport=args.transport, **kwargs)
            return 0

        raise RuntimeError(f"Unknown command: {args.command}")
    except Exception:
        log.exception("Command '%s' failed", args.command)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
