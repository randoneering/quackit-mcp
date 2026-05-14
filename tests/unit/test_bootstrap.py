import importlib
import sys
from pathlib import Path
from types import SimpleNamespace


class FakeStorage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path


def test_create_app_context_uses_explicit_database_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sys.modules.pop("duckdb", None)
    bootstrap = importlib.import_module("quackit.bootstrap")
    bootstrap = importlib.reload(bootstrap)
    captured_path: Path | None = None

    def fake_storage_factory(database_path: Path) -> FakeStorage:
        nonlocal captured_path
        captured_path = database_path
        return FakeStorage(database_path)

    monkeypatch.setattr(
        bootstrap,
        "load_settings",
        lambda: SimpleNamespace(duckdb_path=tmp_path / "ignored.duckdb", heartbeat_interval=30),
    )

    context = bootstrap.create_app_context(
        database_path=tmp_path / "custom.duckdb",
        storage_factory=fake_storage_factory,
    )

    assert isinstance(context, bootstrap.AppContext)
    assert context.database_path == tmp_path / "custom.duckdb"
    assert isinstance(context.storage, FakeStorage)
    assert context.storage.database_path == tmp_path / "custom.duckdb"
    assert context.service._storage is context.storage
    assert captured_path == tmp_path / "custom.duckdb"
    assert "duckdb" not in sys.modules


def test_create_app_context_uses_settings_path(monkeypatch, tmp_path: Path) -> None:
    bootstrap = importlib.import_module("quackit.bootstrap")
    configured_path = tmp_path / "configured.duckdb"

    monkeypatch.setattr(
        bootstrap,
        "load_settings",
        lambda: SimpleNamespace(duckdb_path=configured_path, heartbeat_interval=30),
    )

    context = bootstrap.create_app_context(storage_factory=FakeStorage)

    assert context.database_path == configured_path
    assert isinstance(context.storage, FakeStorage)
    assert context.storage.database_path == configured_path
    assert context.service._storage is context.storage
