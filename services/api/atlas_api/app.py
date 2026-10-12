"""FastAPI application. No physics here: routers call astronomy_core (CLAUDE.md §4, §14)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import Engine, text

from astronomy_core.frames import frame_metadata
from atlas_api.db import get_engine
from atlas_api.routers import objects, routes, stars
from atlas_api.schemas import DatabaseInfo, FrameInfo, Health, SnapshotInfo

API_VERSION = "0.1.0"

app = FastAPI(
    title="Universe Atlas API",
    version=API_VERSION,
    description="Milky Way edition: search, dossiers, star tiles, routes and traversals.",
)
app.include_router(objects.router)
app.include_router(stars.router)
app.include_router(routes.router)


@app.get("/health", response_model=Health)
def health(engine: Annotated[Engine, Depends(get_engine)]) -> Health:
    meta = frame_metadata()
    frame = FrameInfo(
        galactocentric_defaults=meta["galactocentric_defaults"],
        astropy_version=meta["astropy_version"],
    )
    try:
        with engine.connect() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            row = conn.execute(
                text(
                    "SELECT id, finished_at, snapshot FROM ingestion_job "
                    "WHERE status = 'complete' ORDER BY finished_at DESC LIMIT 1"
                )
            ).first()
    except Exception as exc:  # report the failure class only, never the URL or message
        return Health(
            status="degraded",
            api_version=API_VERSION,
            database=DatabaseInfo(
                reachable=False, migration_revision=None, error=type(exc).__name__
            ),
            snapshot=None,
            frame=frame,
        )
    snapshot = (
        SnapshotInfo(
            ingestion_job_id=row.id,
            finished_at=row.finished_at.isoformat(),
            datasets={str(k): str(v) for k, v in row.snapshot.items()},
        )
        if row is not None
        else None
    )
    return Health(
        status="ok" if snapshot is not None else "degraded",
        api_version=API_VERSION,
        database=DatabaseInfo(reachable=True, migration_revision=revision),
        snapshot=snapshot,
        frame=frame,
    )
