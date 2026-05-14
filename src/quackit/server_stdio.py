from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from fastmcp import FastMCP

from quackit._validation import validate_content, validate_name, validate_query, validate_tags
from quackit.bootstrap import AppContext, create_app_context
from quackit.models import ContentType, MemoryType
from quackit.service import MemoryNotFoundError, SkillNotFoundError

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolContext:
    database_path: Path
    app_context: AppContext

    @property
    def service(self):
        return self.app_context.service


def create_tool_context(database_path: Path | None = None) -> ToolContext:
    app_context = create_app_context(database_path=database_path)
    return ToolContext(
        database_path=app_context.database_path,
        app_context=app_context,
    )


def build_server(database_path: Path | None = None) -> FastMCP:
    tool_context = create_tool_context(database_path=database_path)
    orphaned = tool_context.service.run_orphan_detection()
    if orphaned:
        log.warning("Orphaned %d session(s) from previous run", len(orphaned))
    else:
        log.info("No orphaned sessions found")
    mcp = FastMCP("quackit")
    log.info("MCP server 'quackit' built with %s backend", tool_context.app_context.storage.__class__.__name__)

    @mcp.tool
    def create_project(name: str, description: str | None = None) -> dict:
        """Create a new project to group sessions and memories."""
        log.debug("Tool call: create_project(name=%s)", name)
        validate_name(name)
        return tool_context.service.create_project(name=name, description=description).model_dump(mode="json")

    @mcp.tool
    def consolidate_projects(source_ids: list[str], target_id: str) -> dict:
        """Move all sessions and memories from source projects into the target project, then delete the source projects."""
        log.debug("Tool call: consolidate_projects(source_ids=%s, target_id=%s)", source_ids, target_id)
        return tool_context.service.consolidate_projects(source_ids=source_ids, target_id=target_id).model_dump(mode="json")

    @mcp.tool
    def list_projects() -> list[dict]:
        """List all projects."""
        log.debug("Tool call: list_projects")
        return [item.model_dump(mode="json") for item in tool_context.service.list_projects()]

    @mcp.tool
    def start_session(project_id: str | None = None) -> dict:
        """Start a new memory session, optionally within a project."""
        log.debug("Tool call: start_session(project_id=%s)", project_id)
        return tool_context.service.start_session(project_id=project_id).model_dump(mode="json")

    @mcp.tool
    def list_recent_sessions(limit: int = 10) -> list[dict]:
        """List recent sessions, newest first."""
        log.debug("Tool call: list_recent_sessions(limit=%d)", limit)
        return [item.model_dump(mode="json") for item in tool_context.service.list_recent_sessions(limit=limit)]

    @mcp.tool
    def activate_session(session_id: str) -> dict:
        """Activate an existing session to save or search memories."""
        log.debug("Tool call: activate_session(session_id=%s)", session_id)
        return tool_context.service.activate_session(session_id).model_dump(mode="json")

    @mcp.tool
    def end_session(summary: str) -> dict:
        """End the active session with a summary. Stops heartbeats."""
        log.debug("Tool call: end_session(summary=%s)", summary)
        return tool_context.service.end_session(summary).model_dump(mode="json")

    @mcp.tool
    def save_memory(type: str, content: str, tags: list[str] | None = None, title: str | None = None, content_type: str | None = None, metadata: dict[str, str] | None = None) -> dict:
        """Save a memory to the active session. Type: context, summary, error_fix, or note. content_type: note, code, markdown, or skill."""
        log.debug("Tool call: save_memory(type=%s, tags=%s, title=%s, content_type=%s)", type, tags, title, content_type)
        validate_content(content)
        validated_tags = validate_tags(tags or [])
        validated_content_type = None if content_type is None else ContentType(content_type)
        return tool_context.service.save_memory(
            type=MemoryType(type),
            content=content,
            tags=validated_tags,
            title=title,
            content_type=validated_content_type,
            metadata=metadata,
        ).model_dump(mode="json")

    @mcp.tool
    def get_memory(mem_id: str) -> dict:
        """Retrieve a specific memory by its mem_id."""
        log.debug("Tool call: get_memory(mem_id=%s)", mem_id)
        return tool_context.service.get_memory(mem_id).model_dump(mode="json")

    @mcp.tool
    def update_memory(mem_id: str, content: str | None = None, tags: list[str] | None = None, title: str | None = None, content_type: str | None = None, metadata: dict[str, str] | None = None) -> dict:
        """Update a memory's fields. Only provided fields are updated."""
        log.debug("Tool call: update_memory(mem_id=%s)", mem_id)
        validated_ct = None if content_type is None else ContentType(content_type)
        return tool_context.service.update_memory(
            mem_id=mem_id,
            content=content,
            tags=tags,
            title=title,
            content_type=validated_ct,
            metadata=metadata,
        ).model_dump(mode="json")

    @mcp.tool
    def search_memory(query: str, type: str | None = None, project_scope: bool = False, content_type: str | None = None) -> list[dict]:
        """Search memories in the active session. Optionally scope to project or filter by content_type (note, code, markdown, skill)."""
        log.debug("Tool call: search_memory(query=%s, type=%s, project_scope=%s, content_type=%s)", query, type, project_scope, content_type)
        validate_query(query)
        memory_type = None if type is None else MemoryType(type)
        validated_ct = None if content_type is None else ContentType(content_type)
        return [
            item.model_dump(mode="json")
            for item in tool_context.service.search_memory(query=query, type=memory_type, project_scope=project_scope, content_type=validated_ct)
        ]

    @mcp.tool
    def list_sessions_by_project(project_id: str) -> list[dict]:
        """List all sessions belonging to a project, newest first."""
        log.debug("Tool call: list_sessions_by_project(project_id=%s)", project_id)
        return [
            item.model_dump(mode="json")
            for item in tool_context.service.list_sessions_by_project(project_id)
        ]

    @mcp.tool
    def save_skill(name: str, content: str, description: str | None = None, tags: list[str] | None = None, source: str | None = None) -> dict:
        """Save a skill with name, content, optional description, tags, and source."""
        log.debug("Tool call: save_skill(name=%s, tags=%s)", name, tags)
        return tool_context.service.save_skill(name=name, description=description, content=content, tags=tags or [], source=source).model_dump(mode="json")

    @mcp.tool
    def get_skill(skill_id: str) -> dict:
        """Retrieve a specific skill by its skill_id."""
        log.debug("Tool call: get_skill(skill_id=%s)", skill_id)
        return tool_context.service.get_skill(skill_id).model_dump(mode="json")

    @mcp.tool
    def update_skill(skill_id: str, name: str | None = None, description: str | None = None, content: str | None = None, tags: list[str] | None = None, source: str | None = None) -> dict:
        """Update a skill's fields. Only provided fields are updated."""
        log.debug("Tool call: update_skill(skill_id=%s)", skill_id)
        return tool_context.service.update_skill(
            skill_id=skill_id, name=name, description=description,
            content=content, tags=tags, source=source,
        ).model_dump(mode="json")

    @mcp.tool
    def delete_skill(skill_id: str) -> dict:
        """Delete a skill by its skill_id."""
        log.debug("Tool call: delete_skill(skill_id=%s)", skill_id)
        tool_context.service.delete_skill(skill_id)
        return {"deleted": skill_id}

    @mcp.tool
    def list_skills(query: str = "", tag: str | None = None) -> list[dict]:
        """List skills, optionally filtered by search query or tag."""
        log.debug("Tool call: list_skills(query=%s, tag=%s)", query, tag)
        return [
            item.model_dump(mode="json")
            for item in tool_context.service.list_skills(query=query, tag=tag)
        ]

    return mcp


def main() -> None:
    from quackit._logging import setup_logging
    setup_logging()
    log.info("Starting quackit MCP server (stdio)")
    build_server().run()


if __name__ == "__main__":
    main()
