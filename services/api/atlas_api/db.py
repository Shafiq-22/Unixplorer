"""Shared database dependency."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Connection, Engine

from atlas_db.session import make_engine


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return make_engine()


def get_engine() -> Iterator[Engine]:
    yield _engine()


def get_conn(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[Connection]:
    with engine.connect() as conn:
        yield conn


Conn = Annotated[Connection, Depends(get_conn)]
