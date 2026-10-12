from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from atlas_api.app import app
from atlas_api.db import get_engine


@pytest.fixture(scope="module")
def client(loaded_db: dict[str, Any]) -> Iterator[TestClient]:
    engine = create_engine(loaded_db["url"])
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
