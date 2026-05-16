from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quackit.config import load_settings
from quackit.service import MemoryService
from quackit.storage import StorageBackend

log = logging.getLogger(__name__)

StorageFactory = Callable[[Path], StorageBackend]


@dataclass(slots=True)
class AppContext:
    database_path: Path
    storage: StorageBackend
    service: MemoryService

    def close(self) -> None:
        self.service.close()


def _create_storage(database_path: Path) -> StorageBackend:
    from quackit.storage.duckdb import DuckDBStorage

    return DuckDBStorage(database_path)


def _create_postgres_storage(_database_path: Path) -> StorageBackend:
    from quackit.storage.postgres import PostgresStorage

    settings = load_settings()
    if settings.database_url is None:
        raise ValueError("QUACKIT_DATABASE_URL (or AGENT_MEMORY_DATABASE_URL) must be set for Postgres backend")
    return PostgresStorage(settings.database_url)


def create_app_context(
    database_path: Path | str | None = None,
    storage_factory: StorageFactory | None = None,
) -> AppContext:
    settings = load_settings()
    resolved_path = settings.duckdb_path if database_path is None else Path(database_path)
    factory = storage_factory or (_create_postgres_storage if settings.database_url else _create_storage)
    storage = factory(resolved_path)
    backend_name = storage.__class__.__name__
    log.info("Initialized %s backend at %s", backend_name, resolved_path)
    service = MemoryService(storage=storage, heartbeat_interval=settings.heartbeat_interval)
    return AppContext(
        database_path=resolved_path,
        storage=storage,
        service=service,
    )
