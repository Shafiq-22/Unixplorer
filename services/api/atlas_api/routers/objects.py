"""Search and dossier. Read-only views of the loaded snapshot; no physics here."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Connection, text

from atlas_api.db import Conn
from atlas_api.schemas import (
    Cartesian,
    Classification,
    Distance,
    Dossier,
    Identifier,
    Measurement,
    ObjectSummary,
    ParentLink,
    Position,
    Publication,
    SearchResults,
    SourceRef,
    StateVector,
    Uncertainty,
)

router = APIRouter(tags=["objects"])

# Display name (not a scientific value): a landmark's own label from landmarks.yaml; else
# SIMBAD's main identifier without its "NAME " prefix, whitespace collapsed; else the
# catalogue primary name.
DISPLAY = (
    "CASE WHEN EXISTS (SELECT 1 FROM external_identifier lm WHERE lm.object_id = o.id "
    "AND lm.catalogue = 'atlas_landmark') THEN o.primary_name ELSE "
    "COALESCE((SELECT regexp_replace("
    "regexp_replace(dn.identifier, '^NAME ', ''), '\\s+', ' ', 'g') "
    "FROM external_identifier dn WHERE dn.object_id = o.id AND dn.catalogue = 'simbad_main_id' "
    "ORDER BY dn.id LIMIT 1), o.primary_name) END"
)
# Rank stars, landmarks and Solar System bodies before planets when match quality ties.
TYPE_RANK = "CASE WHEN o.object_type = 'exoplanet' THEN 1 ELSE 0 END"
# At equal match quality, SIMBAD proper names ("NAME ...") beat catalogue designations.
PROPER_NAME_RANK = "CASE WHEN b.label LIKE 'NAME %' THEN 0 ELSE 1 END"

HAS_3D = (
    "EXISTS (SELECT 1 FROM position_solution p3 "
    "WHERE p3.object_id = o.id AND p3.bary_x_pc IS NOT NULL)"
)


def normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip()).lower()


@router.get("/objects/search", response_model=SearchResults)
def search(
    conn: Conn,
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
) -> SearchResults:
    nq = normalize(q)
    like = "%" + nq.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = conn.execute(
        text(
            f"""
            WITH hits AS (
                SELECT a.object_id, a.alias AS label,
                       CASE WHEN a.alias_normalized = :nq
                              OR regexp_replace(a.alias_normalized, '^name ', '') = :nq THEN 0
                            WHEN regexp_replace(a.alias_normalized, '^name ', '') LIKE :prefix
                              THEN 1
                            ELSE 2 END AS rank
                FROM object_alias a WHERE a.alias_normalized LIKE :like
                UNION ALL
                SELECT o.id, o.primary_name,
                       CASE WHEN lower(o.primary_name) = :nq THEN 0
                            WHEN lower(o.primary_name) LIKE :prefix THEN 1 ELSE 2 END
                FROM celestial_object o WHERE lower(o.primary_name) LIKE :like
                UNION ALL
                SELECT e.object_id, e.catalogue || ' ' || e.identifier, 0
                FROM external_identifier e WHERE lower(e.identifier) = :nq
            ),
            best AS (
                SELECT DISTINCT ON (object_id) object_id, label, rank
                FROM hits ORDER BY object_id, rank, length(label), label
            )
            SELECT o.id, o.primary_name, o.object_type, b.label, {HAS_3D} AS has_3d,
                   {DISPLAY} AS display_name
            FROM best b JOIN celestial_object o ON o.id = b.object_id
            ORDER BY b.rank, {TYPE_RANK}, {PROPER_NAME_RANK},
                     length(regexp_replace(b.label, '^NAME ', '')), b.label,
                     o.id
            LIMIT :limit
            """
        ),
        {"nq": nq, "like": like, "prefix": like[1:], "limit": limit},
    ).all()
    return SearchResults(
        query=q,
        results=[
            ObjectSummary(
                id=r.id,
                primary_name=r.primary_name,
                display_name=r.display_name,
                object_type=r.object_type,
                matched_alias=r.label,
                has_3d_position=r.has_3d,
            )
            for r in rows
        ],
    )


def _summary(conn: Connection, object_id: int) -> ObjectSummary | None:
    r = conn.execute(
        text(
            f"SELECT o.id, o.primary_name, o.object_type, {HAS_3D} AS has_3d, "
            f"{DISPLAY} AS display_name "
            "FROM celestial_object o WHERE o.id = :id"
        ),
        {"id": object_id},
    ).first()
    if r is None:
        return None
    return ObjectSummary(
        id=r.id,
        primary_name=r.primary_name,
        display_name=r.display_name,
        object_type=r.object_type,
        has_3d_position=r.has_3d,
    )


SOURCE_SQL = """
    f.path AS f_path, s.dataset AS s_dataset, s.source AS s_archive, s.release AS s_release,
    s.retrieved_at AS s_retrieved_at
"""


def _source(r: Any, rid: str, prefix: str = "", pub: Publication | None = None) -> SourceRef:
    return SourceRef(
        source_record_id=rid,
        dataset=getattr(r, f"{prefix}s_dataset"),
        archive=getattr(r, f"{prefix}s_archive"),
        release=getattr(r, f"{prefix}s_release"),
        retrieved_at=getattr(r, f"{prefix}s_retrieved_at").isoformat(),
        publication=pub,
    )


@router.get("/objects/{object_id}", response_model=Dossier)
def dossier(object_id: int, conn: Conn) -> Dossier:
    summary = _summary(conn, object_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="object not found")
    params = {"id": object_id}
    identifiers = [
        Identifier(
            catalogue=r.catalogue, identifier=r.identifier, source_record_id=r.source_record_id
        )
        for r in conn.execute(
            text(
                "SELECT catalogue, identifier, source_record_id FROM external_identifier "
                "WHERE object_id = :id ORDER BY catalogue, identifier"
            ),
            params,
        )
    ]
    aliases = [
        r.alias
        for r in conn.execute(
            text("SELECT alias FROM object_alias WHERE object_id = :id ORDER BY alias"), params
        )
    ]
    classifications = [
        Classification(scheme=r.scheme, value=r.value, source_record_id=r.source_record_id)
        for r in conn.execute(
            text(
                "SELECT scheme, value, source_record_id FROM classification "
                "WHERE object_id = :id ORDER BY scheme, value"
            ),
            params,
        )
    ]
    measurements = []
    for r in conn.execute(
        text(f"""SELECT m.*, p.bibcode, p.citation, {SOURCE_SQL}
                 FROM measurement m
                 JOIN source_file f ON f.id = m.source_file_id
                 JOIN scientific_source s ON s.id = f.scientific_source_id
                 LEFT JOIN publication p ON p.id = m.publication_id
                 WHERE m.object_id = :id
                 ORDER BY m.quantity, m.is_default DESC NULLS LAST, m.source_record_id"""),
        params,
    ):
        pub = Publication(bibcode=r.bibcode, citation=r.citation) if r.bibcode else None
        unc = (
            Uncertainty(
                lower=r.uncertainty_lower, upper=r.uncertainty_upper, type=r.uncertainty_type
            )
            if r.uncertainty_type
            else None
        )
        measurements.append(
            Measurement(
                quantity=r.quantity,
                value=r.value,
                unit=r.unit,
                uncertainty=unc,
                state=r.state,
                method=r.method,
                solution_key=r.solution_key,
                is_default=r.is_default,
                source=_source(r, r.source_record_id, pub=pub),
            )
        )
    positions = []
    for r in conn.execute(
        text(f"""SELECT ps.*, pb.bibcode, pb.citation, {SOURCE_SQL},
                        ds.dataset AS d_s_dataset, ds.source AS d_s_archive,
                        ds.release AS d_s_release, ds.retrieved_at AS d_s_retrieved_at
                 FROM position_solution ps
                 JOIN source_file f ON f.id = ps.source_file_id
                 JOIN scientific_source s ON s.id = f.scientific_source_id
                 LEFT JOIN source_file df ON df.id = ps.distance_source_file_id
                 LEFT JOIN scientific_source ds ON ds.id = df.scientific_source_id
                 LEFT JOIN publication pb ON pb.id = ps.publication_id
                 WHERE ps.object_id = :id AND ps.is_adopted
                 ORDER BY ps.id"""),
        params,
    ):
        pub = Publication(bibcode=r.bibcode, citation=r.citation) if r.bibcode else None
        distance = (
            Distance(
                value_pc=r.distance_pc,
                lower_pc=r.distance_lower_pc,
                upper_pc=r.distance_upper_pc,
                interval=r.distance_interval,
                method=r.distance_method,
                state=r.distance_state,
                source=_source(r, r.distance_source_record_id, prefix="d_"),
            )
            if r.distance_pc is not None
            else None
        )
        sv = (
            StateVector(
                x_km=r.x_km,
                y_km=r.y_km,
                z_km=r.z_km,
                vx_km_s=r.vx_km_s,
                vy_km_s=r.vy_km_s,
                vz_km_s=r.vz_km_s,
            )
            if r.x_km is not None
            else None
        )
        cart = (
            Cartesian(x_pc=r.bary_x_pc, y_pc=r.bary_y_pc, z_pc=r.bary_z_pc, method=r.derived_method)
            if r.bary_x_pc is not None
            else None
        )
        positions.append(
            Position(
                id=r.id,
                kind=r.kind,
                frame=r.frame,
                epoch=r.epoch,
                ra_deg=r.ra_deg,
                dec_deg=r.dec_deg,
                ra_error_mas=r.ra_error_mas,
                dec_error_mas=r.dec_error_mas,
                position_state=r.position_state,
                position_method=r.position_method,
                distance_state=r.distance_state,
                distance=distance,
                state_vector=sv,
                cartesian=cart,
                source=_source(r, r.source_record_id, pub=pub),
            )
        )
    parent_row = conn.execute(
        text("SELECT parent_object_id, parent_link_reason FROM celestial_object WHERE id = :id"),
        params,
    ).first()
    parent = None
    if parent_row is not None and parent_row.parent_object_id is not None:
        ps = _summary(conn, parent_row.parent_object_id)
        if ps is not None:
            parent = ParentLink(object=ps, reason=parent_row.parent_link_reason or "")
    children = [
        ObjectSummary(
            id=r.id,
            primary_name=r.primary_name,
            display_name=r.display_name,
            object_type=r.object_type,
            has_3d_position=r.has_3d,
        )
        for r in conn.execute(
            text(
                f"SELECT o.id, o.primary_name, o.object_type, {HAS_3D} AS has_3d, "
                f"{DISPLAY} AS display_name "
                "FROM celestial_object o WHERE o.parent_object_id = :id ORDER BY o.primary_name"
            ),
            params,
        )
    ]
    return Dossier(
        object=summary,
        identifiers=identifiers,
        aliases=aliases,
        classifications=classifications,
        measurements=measurements,
        positions=positions,
        parent=parent,
        children=children,
    )
