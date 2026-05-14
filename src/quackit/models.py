from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from secrets import token_hex

from pydantic import BaseModel, Field


class MemoryType(StrEnum):
    CONTEXT = "context"
    SUMMARY = "summary"
    ERROR_FIX = "error_fix"
    NOTE = "note"


class ContentType(StrEnum):
    NOTE = "note"
    CODE = "code"
    MARKDOWN = "markdown"
    SKILL = "skill"


class SessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    ORPHANED = "orphaned"


class MemoryCreate(BaseModel):
    type: MemoryType
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    title: str | None = None
    content_type: ContentType | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    title: str | None = None
    content_type: ContentType | None = None
    metadata: dict[str, str] | None = None


class ProjectRecord(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime


class SessionRecord(BaseModel):
    id: str
    status: SessionStatus
    summary: str | None
    project_id: str | None = None
    started_at: datetime
    ended_at: datetime | None
    last_heartbeat: datetime


class MemoryRecord(BaseModel):
    id: str
    mem_id: str
    session_id: str
    project_id: str | None = None
    type: MemoryType
    content: str
    tags: list[str]
    title: str | None = None
    content_type: ContentType | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime


class SkillRecord(BaseModel):
    skill_id: str
    name: str
    description: str | None = None
    content: str
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    created_at: datetime
    updated_at: datetime


class SkillCreate(BaseModel):
    name: str
    description: str | None = None
    content: str
    tags: list[str] = Field(default_factory=list)
    source: str | None = None


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    source: str | None = None


class SearchResult(BaseModel):
    mem_id: str
    type: MemoryType
    snippet: str
    tags: list[str]
    title: str | None = None
    content_type: ContentType | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: str

    @classmethod
    def from_content(
        cls,
        mem_id: str,
        type: MemoryType,
        content: str,
        tags: list[str],
        created_at: str,
        title: str | None = None,
        content_type: ContentType | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "SearchResult":
        snippet = content if len(content) <= 120 else f"{content[:120]}..."
        return cls(
            mem_id=mem_id,
            type=type,
            snippet=snippet,
            tags=tags,
            title=title,
            content_type=content_type,
            metadata=metadata or {},
            created_at=created_at,
        )


def build_mem_id() -> str:
    return f"mem_{token_hex(8)}"


def build_skill_id() -> str:
    return f"sk_{token_hex(8)}"
