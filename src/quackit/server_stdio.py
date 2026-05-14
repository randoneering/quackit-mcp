from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from quackit._validation import (
    validate_content,
    validate_limit,
    validate_name,
    validate_query,
    validate_tags,
)
from quackit.auth import OAuthConfig, build_oauth_provider
from quackit.bootstrap import AppContext, create_app_context
from quackit.models import ContentType, MemoryType

log = logging.getLogger(__name__)

MemoryTypeName = Literal["context", "summary", "error_fix", "note"]
ContentTypeName = Literal["note", "code", "markdown", "skill"]
DEFAULT_LIST_LIMIT = 100
DEFAULT_MAX_CHARS = 50_000
MAX_CONTENT_CHARS = 100_000

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, openWorldHint=False
)


def _validate_offset(offset: int) -> int:
    if offset < 0:
        raise ValueError(f"offset must be 0 or greater ({offset})")
    return offset


def _truncate_content(
    data: dict[str, Any], *, offset: int, max_chars: int
) -> dict[str, Any]:
    _validate_offset(offset)
    validate_limit(max_chars, maximum=MAX_CONTENT_CHARS)
    content = data.get("content", "")
    content_length = len(content)
    end = min(offset + max_chars, content_length)
    data["content"] = content[offset:end]
    data["content_length"] = content_length
    data["offset"] = offset
    data["truncated"] = end < content_length
    data["next_offset"] = end if end < content_length else None
    return data


def _skill_summary(skill: Any) -> dict[str, Any]:
    data = skill.model_dump(mode="json")
    content = data.pop("content", "")
    data["content_length"] = len(content)
    return data


@dataclass(slots=True)
class ToolContext:
    database_path: Path
    app_context: AppContext

    @property
    def service(self):
        return self.app_context.service

    def close(self) -> None:
        self.app_context.close()


def create_tool_context(database_path: Path | None = None) -> ToolContext:
    app_context = create_app_context(database_path=database_path)
    return ToolContext(
        database_path=app_context.database_path,
        app_context=app_context,
    )


def build_server(
    database_path: Path | None = None,
    auth_config: OAuthConfig | None = None,
) -> FastMCP:
    tool_context = create_tool_context(database_path=database_path)
    atexit.register(tool_context.close)
    orphaned = tool_context.service.run_orphan_detection()
    if orphaned:
        log.warning("Orphaned %d session(s) from previous run", len(orphaned))
    else:
        log.info("No orphaned sessions found")
    auth_provider = None if auth_config is None else build_oauth_provider(auth_config)
    mcp = FastMCP("quackit", auth=auth_provider)
    log.info(
        "MCP server 'quackit' built with %s backend",
        tool_context.app_context.storage.__class__.__name__,
    )

    @mcp.tool(annotations=WRITE)
    def create_project(name: str, description: str | None = None) -> dict:
        """Create a new project to group sessions and memories."""
        log.debug("Tool call: create_project(name=%s)", name)
        validate_name(name)
        return tool_context.service.create_project(
            name=name, description=description
        ).model_dump(mode="json")

    @mcp.tool(annotations=DESTRUCTIVE)
    def consolidate_projects(source_ids: list[str], target_id: str) -> dict:
        """Move all sessions and memories from source projects into the target project, then delete the source projects."""
        log.debug(
            "Tool call: consolidate_projects(source_ids=%s, target_id=%s)",
            source_ids,
            target_id,
        )
        return tool_context.service.consolidate_projects(
            source_ids=source_ids, target_id=target_id
        ).model_dump(mode="json")

    @mcp.tool(annotations=READ_ONLY)
    def list_projects(limit: int = DEFAULT_LIST_LIMIT) -> list[dict]:
        """List projects, bounded by limit."""
        log.debug("Tool call: list_projects(limit=%d)", limit)
        validate_limit(limit)
        return [
            item.model_dump(mode="json")
            for item in tool_context.service.list_projects()[:limit]
        ]

    @mcp.tool(annotations=WRITE)
    def start_session(project_id: str | None = None) -> dict:
        """Start a new memory session, optionally within a project."""
        log.debug("Tool call: start_session(project_id=%s)", project_id)
        return tool_context.service.start_session(project_id=project_id).model_dump(
            mode="json"
        )

    @mcp.tool(annotations=READ_ONLY)
    def list_recent_sessions(limit: int = 10) -> list[dict]:
        """List recent sessions, newest first."""
        log.debug("Tool call: list_recent_sessions(limit=%d)", limit)
        return [
            item.model_dump(mode="json")
            for item in tool_context.service.list_recent_sessions(limit=limit)
        ]

    @mcp.tool(annotations=WRITE)
    def activate_session(session_id: str) -> dict:
        """Activate an existing session to save or search memories."""
        log.debug("Tool call: activate_session(session_id=%s)", session_id)
        return tool_context.service.activate_session(session_id).model_dump(mode="json")

    @mcp.tool(annotations=WRITE)
    def end_session(summary: str) -> dict:
        """End the active session with a summary. Stops heartbeats."""
        log.debug("Tool call: end_session")
        return tool_context.service.end_session(summary).model_dump(mode="json")

    @mcp.tool(annotations=WRITE)
    def save_memory(
        type: MemoryTypeName,
        content: str,
        tags: list[str] | None = None,
        title: str | None = None,
        content_type: ContentTypeName | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict:
        """Save a memory to the active session. Type: context, summary, error_fix, or note. content_type: note, code, markdown, or skill."""
        log.debug(
            "Tool call: save_memory(type=%s, tags=%s, title=%s, content_type=%s)",
            type,
            tags,
            title,
            content_type,
        )
        validate_content(content)
        validated_tags = validate_tags(tags or [])
        validated_content_type = (
            None if content_type is None else ContentType(content_type)
        )
        return tool_context.service.save_memory(
            type=MemoryType(type),
            content=content,
            tags=validated_tags,
            title=title,
            content_type=validated_content_type,
            metadata=metadata,
        ).model_dump(mode="json")

    @mcp.tool(annotations=READ_ONLY)
    def get_memory(
        mem_id: str,
        max_chars: int = DEFAULT_MAX_CHARS,
        offset: int = 0,
    ) -> dict:
        """Retrieve a memory by mem_id. Content is paginated with max_chars and offset."""
        log.debug(
            "Tool call: get_memory(mem_id=%s, max_chars=%d, offset=%d)",
            mem_id,
            max_chars,
            offset,
        )
        return _truncate_content(
            tool_context.service.get_memory(mem_id).model_dump(mode="json"),
            max_chars=max_chars,
            offset=offset,
        )

    @mcp.tool(annotations=WRITE)
    def update_memory(
        mem_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        title: str | None = None,
        content_type: ContentTypeName | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict:
        """Update a memory's fields. Only provided fields are updated."""
        log.debug("Tool call: update_memory(mem_id=%s)", mem_id)
        if content is not None:
            validate_content(content)
        validated_tags = None if tags is None else validate_tags(tags)
        validated_ct = None if content_type is None else ContentType(content_type)
        return tool_context.service.update_memory(
            mem_id=mem_id,
            content=content,
            tags=validated_tags,
            title=title,
            content_type=validated_ct,
            metadata=metadata,
        ).model_dump(mode="json")

    @mcp.tool(annotations=READ_ONLY)
    def search_memory(
        query: str,
        type: MemoryTypeName | None = None,
        project_scope: bool = False,
        content_type: ContentTypeName | None = None,
    ) -> list[dict]:
        """Search memories in the active session. Optionally scope to project or filter by content_type (note, code, markdown, skill)."""
        log.debug(
            "Tool call: search_memory(type=%s, project_scope=%s, content_type=%s)",
            type,
            project_scope,
            content_type,
        )
        validate_query(query)
        memory_type = None if type is None else MemoryType(type)
        validated_ct = None if content_type is None else ContentType(content_type)
        return [
            item.model_dump(mode="json")
            for item in tool_context.service.search_memory(
                query=query,
                type=memory_type,
                project_scope=project_scope,
                content_type=validated_ct,
            )
        ]

    @mcp.tool(annotations=READ_ONLY)
    def list_sessions_by_project(
        project_id: str, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[dict]:
        """List sessions belonging to a project, newest first, bounded by limit."""
        log.debug(
            "Tool call: list_sessions_by_project(project_id=%s, limit=%d)",
            project_id,
            limit,
        )
        validate_limit(limit)
        return [
            item.model_dump(mode="json")
            for item in tool_context.service.list_sessions_by_project(project_id)[
                :limit
            ]
        ]

    @mcp.tool(annotations=WRITE)
    def save_skill(
        name: str,
        content: str,
        description: str | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> dict:
        """Save a skill with name, content, optional description, tags, and source."""
        log.debug("Tool call: save_skill(name=%s, tags=%s)", name, tags)
        validate_name(name)
        validate_content(content)
        validated_tags = validate_tags(tags or [])
        return tool_context.service.save_skill(
            name=name,
            description=description,
            content=content,
            tags=validated_tags,
            source=source,
        ).model_dump(mode="json")

    @mcp.tool(annotations=READ_ONLY)
    def get_skill(
        skill_id: str,
        max_chars: int = DEFAULT_MAX_CHARS,
        offset: int = 0,
    ) -> dict:
        """Retrieve a skill by skill_id. Content is paginated with max_chars and offset."""
        log.debug(
            "Tool call: get_skill(skill_id=%s, max_chars=%d, offset=%d)",
            skill_id,
            max_chars,
            offset,
        )
        return _truncate_content(
            tool_context.service.get_skill(skill_id).model_dump(mode="json"),
            max_chars=max_chars,
            offset=offset,
        )

    @mcp.tool(annotations=WRITE)
    def update_skill(
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> dict:
        """Update a skill's fields. Only provided fields are updated."""
        log.debug("Tool call: update_skill(skill_id=%s)", skill_id)
        if name is not None:
            validate_name(name)
        if content is not None:
            validate_content(content)
        validated_tags = None if tags is None else validate_tags(tags)
        return tool_context.service.update_skill(
            skill_id=skill_id,
            name=name,
            description=description,
            content=content,
            tags=validated_tags,
            source=source,
        ).model_dump(mode="json")

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_skill(skill_id: str) -> dict:
        """Delete a skill by its skill_id."""
        log.debug("Tool call: delete_skill(skill_id=%s)", skill_id)
        tool_context.service.delete_skill(skill_id)
        return {"deleted": skill_id}

    @mcp.tool(annotations=READ_ONLY)
    def list_skills(
        query: str = "",
        tag: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> list[dict]:
        """List skill summaries. Full content is omitted; call get_skill for paginated content."""
        log.debug(
            "Tool call: list_skills(query=%s, tag=%s, limit=%d)", query, tag, limit
        )
        validate_limit(limit)
        return [
            _skill_summary(item)
            for item in tool_context.service.list_skills(query=query, tag=tag)[:limit]
        ]

    return mcp


def main() -> None:
    from quackit._logging import setup_logging

    setup_logging()
    log.info("Starting quackit MCP server (stdio)")
    build_server().run()


if __name__ == "__main__":
    main()
