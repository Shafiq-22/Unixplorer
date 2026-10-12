"""Database URL handling. The URL comes from the environment, never from code."""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine

DEFAULT_URL_ENV = "DATABASE_URL"


def database_url() -> str:
    url = os.environ.get(DEFAULT_URL_ENV)
    if not url:
        raise RuntimeError(
            f"{DEFAULT_URL_ENV} is not set (see .env.example), "
            "e.g. postgresql+psycopg://atlas:atlas@localhost:5432/atlas"
        )
    return url


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True, future=True)
