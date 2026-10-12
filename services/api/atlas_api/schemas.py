"""Pydantic response models: the API's public contract (exported to packages/shared-types)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FrameInfo(BaseModel):
    galactocentric_defaults: str = Field(description="astropy Galactocentric parameter set")
    astropy_version: str


class SnapshotInfo(BaseModel):
    ingestion_job_id: int
    finished_at: str
    datasets: dict[str, str] = Field(description="dataset -> manifest retrieved_at (UTC)")


class DatabaseInfo(BaseModel):
    reachable: bool
    migration_revision: str | None
    error: str | None = Field(
        default=None, description="error class only; never connection details"
    )


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    api_version: str
    database: DatabaseInfo
    snapshot: SnapshotInfo | None = Field(description="latest complete `atlas db load`, if any")
    frame: FrameInfo
