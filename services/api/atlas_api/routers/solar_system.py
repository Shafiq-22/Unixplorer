"""The Solar System at the snapshot epoch (CLAUDE.md §11 M3). Reads Horizons rows only."""

from __future__ import annotations

import astropy.units as u
import numpy as np
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from astronomy_core.frames import separation
from atlas_api.db import Conn
from atlas_api.routers.objects import _summary, positions_for
from atlas_api.schemas import DistanceFromSun, SolarSystem, SolarSystemBody

router = APIRouter(tags=["solar-system"])

SEPARATION_METHOD = "astronomy_core.frames.separation of barycentric positions (same epoch)"


@router.get("/solar-system", response_model=SolarSystem)
def solar_system(conn: Conn) -> SolarSystem:
    ids = [
        r.id
        for r in conn.execute(
            text(
                "SELECT id FROM celestial_object WHERE object_type = 'solar_system_body' "
                "ORDER BY id"
            )
        )
    ]
    if not ids:
        raise HTTPException(status_code=404, detail="no Solar System bodies loaded")
    bodies = []
    for oid in ids:
        summary = _summary(conn, oid)
        positions = [p for p in positions_for(conn, oid) if p.kind == "state_vector"]
        if summary is None or not positions or positions[0].cartesian is None:
            continue
        bodies.append((summary, positions[0]))
    sun = next((p for s, p in bodies if s.display_name == "Sun"), None)
    sun_xyz = (
        np.array([sun.cartesian.x_pc, sun.cartesian.y_pc, sun.cartesian.z_pc]) * u.pc
        if sun is not None and sun.cartesian is not None
        else None
    )
    out = []
    for summary, pos in bodies:
        assert pos.cartesian is not None
        dist = None
        if sun_xyz is not None and summary.display_name != "Sun":
            xyz = np.array([pos.cartesian.x_pc, pos.cartesian.y_pc, pos.cartesian.z_pc]) * u.pc
            d = separation(xyz, sun_xyz)
            dist = DistanceFromSun(
                value_au=d.to_value(u.AU), value_km=d.to_value(u.km), method=SEPARATION_METHOD
            )
        out.append(SolarSystemBody(object=summary, position=pos, distance_from_sun=dist))
    out.sort(key=lambda b: -1.0 if b.distance_from_sun is None else b.distance_from_sun.value_au)
    epochs = {b.position.epoch for b in out}
    frames = {b.position.frame for b in out}
    return SolarSystem(
        epoch=epochs.pop() if len(epochs) == 1 else "mixed epochs: " + "; ".join(sorted(epochs)),
        frame=frames.pop() if len(frames) == 1 else "mixed frames",
        bodies=out,
    )
