"""Routes and traversals. Geometry and physics come from route_planner / astronomy_core."""

from __future__ import annotations

import json
from importlib.metadata import version
from typing import Any

import astropy.units as u
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Connection, text

from astronomy_core.frames import frame_metadata
from atlas_api.db import Conn
from atlas_api.routers.objects import _summary
from atlas_api.schemas import (
    ModelEntry,
    RouteDistanceOut,
    RouteEndpoint,
    RouteRequest,
    RouteResult,
    Trajectory,
    TrajectorySample,
    Traversal,
    TraversalCreate,
    TraversalUpdate,
)
from route_planner.geometry import Endpoint, route_distance
from route_planner.plan import MODEL_IDS, TravelParameters, plan, trajectory

router = APIRouter(tags=["routes"])

CODE_VERSION = f"universe-atlas {version('universe-atlas')}"


def _endpoint(conn: Connection, object_id: int) -> tuple[Endpoint, RouteEndpoint]:
    summary = _summary(conn, object_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"object {object_id} not found")
    r = conn.execute(
        text("""SELECT id, kind, epoch, position_method, distance_method, bary_x_pc, bary_y_pc,
                       bary_z_pc, distance_lower_pc, distance_upper_pc
                FROM position_solution
                WHERE object_id = :id AND is_adopted AND bary_x_pc IS NOT NULL
                ORDER BY id LIMIT 1"""),
        {"id": object_id},
    ).first()
    if r is None:
        raise HTTPException(
            status_code=422,
            detail=f"{summary.display_name} has no distance solution: sky view only, no route",
        )
    xyz = np.array([r.bary_x_pc, r.bary_y_pc, r.bary_z_pc]) * u.pc
    if r.kind == "sky" and r.distance_lower_pc is not None and r.distance_upper_pc is not None:
        ep = Endpoint.along_sight_line(
            summary.display_name,
            xyz,
            r.distance_lower_pc * u.pc,
            r.distance_upper_pc * u.pc,
            r.distance_method,
        )
    else:
        ep = Endpoint.fixed(summary.display_name, xyz, r.position_method)
    return ep, RouteEndpoint(
        object=summary,
        position_id=r.id,
        epoch=r.epoch,
        position_method=r.position_method,
        distance_method=r.distance_method,
    )


def _params(req: RouteRequest) -> TravelParameters:
    return TravelParameters(
        req.speed_fraction_c, req.proper_acceleration_g, req.ftl_speed_fraction_c
    )


@router.post("/routes", response_model=RouteResult, status_code=201)
def create_route(req: RouteRequest, conn: Conn) -> RouteResult:
    if req.origin_id == req.destination_id:
        raise HTTPException(status_code=422, detail="origin and destination are the same object")
    a, a_out = _endpoint(conn, req.origin_id)
    b, b_out = _endpoint(conn, req.destination_id)
    dist = route_distance(a, b)
    models = plan(dist, _params(req))
    frame = frame_metadata()
    stored = {
        "parameters": req.model_dump(),
        "distance": {
            "value_pc": dist.value.to_value(u.pc),
            "lower_pc": dist.lower.to_value(u.pc),
            "upper_pc": dist.upper.to_value(u.pc),
            "method": dist.method,
        },
        "origin": a_out.model_dump(),
        "destination": b_out.model_dump(),
        "models": models,
    }
    route_id = conn.execute(
        text("""INSERT INTO route_calculation (origin_position_id, destination_position_id,
                    distance_m, frame_metadata, model_results, code_version)
                VALUES (:o, :d, :m, :f, :r, :v) RETURNING id"""),
        {
            "o": a_out.position_id,
            "d": b_out.position_id,
            "m": dist.value.to_value(u.m),
            "f": json.dumps(frame),
            "r": json.dumps(stored),
            "v": CODE_VERSION,
        },
    ).scalar_one()
    conn.commit()
    return _route_result(route_id, stored, frame, CODE_VERSION)


def _route_result(
    route_id: int, stored: dict[str, Any], frame: dict[str, Any], code_version: str
) -> RouteResult:
    return RouteResult(
        id=route_id,
        origin=RouteEndpoint(**stored["origin"]),
        destination=RouteEndpoint(**stored["destination"]),
        distance=RouteDistanceOut(**stored["distance"]),
        parameters=RouteRequest(**stored["parameters"]),
        frame=frame,
        models=[ModelEntry(**m) for m in stored["models"]],
        code_version=code_version,
    )


def _load_route(conn: Connection, route_id: int) -> tuple[dict[str, Any], dict[str, Any], str]:
    r = conn.execute(
        text(
            "SELECT model_results, frame_metadata, code_version FROM route_calculation "
            "WHERE id = :id"
        ),
        {"id": route_id},
    ).first()
    if r is None:
        raise HTTPException(status_code=404, detail="route not found")
    return r.model_results, r.frame_metadata, r.code_version


@router.get("/routes/{route_id}", response_model=RouteResult)
def get_route(route_id: int, conn: Conn) -> RouteResult:
    stored, frame, cv = _load_route(conn, route_id)
    return _route_result(route_id, stored, frame, cv)


@router.get("/routes/{route_id}/trajectory", response_model=Trajectory)
def get_trajectory(
    route_id: int,
    conn: Conn,
    model_id: str = Query(),
    samples: int = Query(default=200, ge=2, le=2000),
) -> Trajectory:
    if model_id not in MODEL_IDS:
        raise HTTPException(status_code=422, detail=f"unknown model_id {model_id!r}")
    stored, _, _ = _load_route(conn, route_id)
    entry = next(m for m in stored["models"] if m["model_id"] == model_id)
    if "refused" in entry:
        raise HTTPException(status_code=422, detail=f"{model_id} refused: {entry['refused']}")
    params = _params(RouteRequest(**stored["parameters"]))
    traj = trajectory(model_id, stored["distance"]["value_pc"] * u.pc, params, samples)
    return Trajectory(
        route_id=route_id,
        model_id=traj["model_id"],
        model_version=traj["model_version"],
        status=traj["status"],
        proper_time_defined=traj["proper_time_defined"],
        samples=[TrajectorySample(**s) for s in traj["samples"]],
    )


# --------------------------------------------------------------------------- traversals

# Allowed status changes. Anything else is a 409.
TRANSITIONS = {
    "planned": {"running", "cancelled"},
    "running": {"paused", "cancelled", "arrived"},
    "paused": {"running", "cancelled"},
    "cancelled": set(),
    "arrived": set(),
}


def _traversal(conn: Connection, tid: int) -> Traversal:
    r = conn.execute(
        text("""SELECT t.id, t.route_calculation_id, t.model_id, t.status, t.progress
                FROM traversal_session t WHERE t.id = :id"""),
        {"id": tid},
    ).first()
    if r is None:
        raise HTTPException(status_code=404, detail="traversal not found")
    return Traversal(
        id=r.id,
        route_id=r.route_calculation_id,
        model_id=r.model_id,
        status=r.status,
        coordinate_time_yr=float(r.progress.get("t_yr", 0.0)),
    )


@router.post("/traversals", response_model=Traversal, status_code=201)
def create_traversal(req: TraversalCreate, conn: Conn) -> Traversal:
    stored, _, _ = _load_route(conn, req.route_id)
    entry = next((m for m in stored["models"] if m["model_id"] == req.model_id), None)
    if entry is None:
        raise HTTPException(status_code=422, detail=f"unknown model_id {req.model_id!r}")
    if "refused" in entry:
        raise HTTPException(status_code=422, detail=f"{req.model_id} refused: {entry['refused']}")
    tid = conn.execute(
        text("""INSERT INTO traversal_session (route_calculation_id, model_id, parameters, status,
                    progress) VALUES (:r, :m, :p, 'running', :g) RETURNING id"""),
        {
            "r": req.route_id,
            "m": req.model_id,
            "p": json.dumps(stored["parameters"]),
            "g": json.dumps({"t_yr": 0.0}),
        },
    ).scalar_one()
    conn.commit()
    return _traversal(conn, tid)


@router.get("/traversals/{traversal_id}", response_model=Traversal)
def get_traversal(traversal_id: int, conn: Conn) -> Traversal:
    return _traversal(conn, traversal_id)


@router.patch("/traversals/{traversal_id}", response_model=Traversal)
def update_traversal(traversal_id: int, req: TraversalUpdate, conn: Conn) -> Traversal:
    current = _traversal(conn, traversal_id)
    if req.status != current.status and req.status not in TRANSITIONS[current.status]:
        raise HTTPException(
            status_code=409, detail=f"cannot go from {current.status} to {req.status}"
        )
    t = current.coordinate_time_yr if req.coordinate_time_yr is None else req.coordinate_time_yr
    conn.execute(
        text("""UPDATE traversal_session SET status = :s, progress = :g, updated_at = now()
                WHERE id = :id"""),
        {"s": req.status, "g": json.dumps({"t_yr": t}), "id": traversal_id},
    )
    conn.commit()
    return _traversal(conn, traversal_id)
