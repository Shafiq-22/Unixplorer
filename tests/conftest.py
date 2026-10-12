from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

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


TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def loaded_db(repo_layout: Layout) -> Iterator[dict[str, Any]]:
    """A disposable database (TEST_DATABASE_URL): schema dropped, migrated, snapshot loaded
    twice (the second load checks idempotency). Shared by every db test in the session."""
    if not TEST_DB_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    if not (repo_layout.processed / "gaia_dr3_nearby.parquet").exists():
        pytest.skip("data/processed not built (run `atlas data build`)")
    import psycopg
    from alembic import command
    from alembic.config import Config

    from ingestion.dbload import psycopg_url, run_load

    with psycopg.connect(psycopg_url(TEST_DB_URL), autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DB_URL
    try:
        command.upgrade(Config(str(repo_layout.root / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    first = run_load(repo_layout, TEST_DB_URL, command="pytest first load")
    second = run_load(repo_layout, TEST_DB_URL, command="pytest second load")
    yield {"url": TEST_DB_URL, "first": first, "second": second}
