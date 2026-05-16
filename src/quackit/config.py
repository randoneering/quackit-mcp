from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class Settings(BaseModel):
    duckdb_path: Path = Field(default_factory=lambda: Path(".local/quackit.duckdb"))
    database_url: str | None = None
    heartbeat_interval: int = 30
    orphan_threshold_minutes: int = 5


_VALID_SCHEMES = frozenset({"postgresql", "postgres"})


def load_settings() -> Settings:
    load_dotenv()
    database_url = os.environ.get("QUACKIT_DATABASE_URL") or os.environ.get("AGENT_MEMORY_DATABASE_URL")
    if database_url:
        scheme = database_url.split("://", 1)[0]
        if scheme not in _VALID_SCHEMES:
            log.warning(
                "Unexpected QUACKIT_DATABASE_URL scheme '%s', expected postgresql://",
                scheme,
            )
        log.info("Using Postgres backend via QUACKIT_DATABASE_URL")
        return Settings(database_url=database_url)
    configured_path = os.environ.get("QUACKIT_DUCKDB_PATH") or os.environ.get("AGENT_MEMORY_DUCKDB_PATH")
    if configured_path:
        log.info("Using DuckDB backend at %s", configured_path)
        return Settings(duckdb_path=Path(configured_path))
    log.info("Using default DuckDB backend at %s", Settings().duckdb_path)
    return Settings()
