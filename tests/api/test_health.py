from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from atlas_api.app import app
from atlas_api.db import get_engine


def test_health_reports_unreachable_db_without_leaking_details() -> None:
    secret_url = "postgresql+psycopg://atlas:s3cr3t@127.0.0.1:1/nowhere"
    app.dependency_overrides[get_engine] = lambda: create_engine(
        secret_url, connect_args={"connect_timeout": 1}
    )
    try:
        body = TestClient(app).get("/health").json()
    finally:
        app.dependency_overrides.clear()
    assert body["status"] == "degraded"
    assert body["database"]["reachable"] is False
    assert "s3cr3t" not in str(body) and "nowhere" not in str(body)
    assert body["frame"]["galactocentric_defaults"] == "v4.0"


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
def test_health_against_database(loaded_db: dict[str, Any]) -> None:
    url = os.environ["TEST_DATABASE_URL"]
    app.dependency_overrides[get_engine] = lambda: create_engine(url)
    try:
        body = TestClient(app).get("/health").json()
    finally:
        app.dependency_overrides.clear()
    assert body["database"]["reachable"] is True
    assert body["database"]["migration_revision"] == "0002"
    assert body["status"] == "ok" and body["snapshot"] is not None
