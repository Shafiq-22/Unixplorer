from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ingestion.paths import Layout

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_layout() -> Layout:
    """The real repository snapshot (read-only use)."""
    return Layout(REPO)


@pytest.fixture
def tmp_layout(tmp_path: Path) -> Layout:
    """An empty snapshot tree with the real query files and landmarks list."""
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "processed").mkdir()
    shutil.copytree(REPO / "data" / "queries", tmp_path / "data" / "queries")
    (tmp_path / "ingestion").mkdir()
    shutil.copy(REPO / "ingestion" / "landmarks.yaml", tmp_path / "ingestion" / "landmarks.yaml")
    (tmp_path / "pyproject.toml").write_text("")
    return Layout(tmp_path)
