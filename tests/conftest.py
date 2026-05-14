from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def duckdb_path(tmp_path: Path) -> Path:
    return tmp_path / "memory.duckdb"
