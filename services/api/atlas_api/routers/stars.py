"""Octree tiles of star positions with brightness LOD (CLAUDE.md §12: never ship the catalogue).

The root cube spans ±ROOT_HALF_PC around the Solar System barycentre on ICRS axes. Level L
splits it into 2^L cells per axis. A tile holds the brightest `limit` stars in its cell
(Gaia G, nulls last), so coarse tiles show the brightest stars and finer tiles fill in.
Level 0 has no spatial filter, so a star outside the root cube still appears there.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Connection, text

from atlas_api.db import Conn
from atlas_api.schemas import StarTile, TileStar

router = APIRouter(tags=["stars"])

ROOT_HALF_PC = 128.0
MAX_LEVEL = 6
FRAME = "ICRS axes, origin at the Solar System barycentre, parsecs (derived)"


def cell_bounds(level: int, ix: int, iy: int, iz: int) -> list[float]:
    n = 2**level
    size = 2 * ROOT_HALF_PC / n
    lo = [-ROOT_HALF_PC + i * size for i in (ix, iy, iz)]
    return [*lo, *(v + size for v in lo)]


# Tiles are immutable for a given loaded snapshot: cache by (snapshot job id, tile, limit).
_CACHE: dict[tuple[int, int, int, int, int, int], StarTile] = {}
_CACHE_MAX = 2048


def _snapshot_job(conn: Connection) -> int:
    job = conn.execute(
        text("SELECT max(id) FROM ingestion_job WHERE status = 'complete'")
    ).scalar_one()
    return int(job or 0)


def _query_tile(conn: Connection, level: int, ix: int, iy: int, iz: int, limit: int) -> StarTile:
    bounds: list[float] | None
    if level == 0:
        where, params, bounds = "", {}, None
    else:
        bounds = cell_bounds(level, ix, iy, iz)
        where = "AND p.bary_xyz <@ cube(ARRAY[:x0, :y0, :z0], ARRAY[:x1, :y1, :z1])"
        params = dict(zip(("x0", "y0", "z0", "x1", "y1", "z1"), bounds, strict=True))
    total = conn.execute(
        text(
            "SELECT count(*) FROM position_solution p WHERE p.kind = 'sky' "
            f"AND p.bary_x_pc IS NOT NULL {where}"
        ),
        params,
    ).scalar_one()
    rows = conn.execute(
        text(f"""SELECT p.object_id, p.bary_x_pc, p.bary_y_pc, p.bary_z_pc, m.value AS g
                 FROM position_solution p
                 LEFT JOIN measurement m ON m.object_id = p.object_id
                      AND m.quantity = 'phot_g_mean_mag'
                 WHERE p.kind = 'sky' AND p.bary_x_pc IS NOT NULL {where}
                 ORDER BY m.value ASC NULLS LAST, p.object_id
                 LIMIT :limit"""),
        {**params, "limit": limit},
    ).all()
    return StarTile(
        level=level,
        ix=ix,
        iy=iy,
        iz=iz,
        bounds_pc=bounds,
        frame=FRAME,
        complete=len(rows) >= total,
        total_in_cell=total,
        stars=[
            TileStar(
                id=r.object_id,
                x_pc=r.bary_x_pc,
                y_pc=r.bary_y_pc,
                z_pc=r.bary_z_pc,
                phot_g_mean_mag=r.g,
            )
            for r in rows
        ],
    )


@router.get("/stars/tiles/{level}/{ix}/{iy}/{iz}", response_model=StarTile)
def tile(
    level: int,
    ix: int,
    iy: int,
    iz: int,
    conn: Conn,
    limit: int = Query(default=3000, ge=1, le=10000),
) -> StarTile:
    if not 0 <= level <= MAX_LEVEL:
        raise HTTPException(status_code=422, detail=f"level must be 0..{MAX_LEVEL}")
    n = 2**level
    if not all(0 <= i < n for i in (ix, iy, iz)):
        raise HTTPException(status_code=422, detail=f"cell index out of range for level {level}")
    key = (_snapshot_job(conn), level, ix, iy, iz, limit)
    cached = _CACHE.get(key)
    if cached is None:
        cached = _query_tile(conn, level, ix, iy, iz, limit)
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = cached
    return cached
