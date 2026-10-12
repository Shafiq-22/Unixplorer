"""Schema for CLAUDE.md §6 (design: docs/decisions/0002-database-schema.md).

Provenance rule (§5): every scientific value row carries `source_file_id` + `source_row`
(a raw file listed in data/manifest.yaml and a 0-based row in it) and the matching
`source_record_id` text "<raw path>#row=<n>". All three are NOT NULL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

VALUE_STATES = (
    "measured",
    "published_estimate",
    "derived",
    "model_predicted",
    "inferred",
    "illustrative",
    "unknown",
    "conflicting",
    "invalid",
    "below_detection",
    "not_applicable",
)
_STATE_SQL = ", ".join(f"'{s}'" for s in VALUE_STATES)

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Cube(UserDefinedType[str]):
    """PostgreSQL `cube` (contrib extension): a GiST-indexable point or box in 3D."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "cube"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {dict[str, Any]: JSONB}


# --------------------------------------------------------------------------- provenance


class IngestionJob(Base):
    __tablename__ = "ingestion_job"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    command: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # running | complete | failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # dataset -> retrieved_at
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("status IN ('running', 'complete', 'failed')", name="status"),
    )


class ScientificSource(Base):
    """One manifest entry (one fetch of one dataset) that rows were loaded from."""

    __tablename__ = "scientific_source"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    service_url: Mapped[str] = mapped_column(Text)
    release: Mapped[str] = mapped_column(Text)
    query_file: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    license_or_credit: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("dataset", "retrieved_at"),)


class SourceFile(Base):
    """A raw file listed in data/manifest.yaml. Value rows reference it by id + row."""

    __tablename__ = "source_file"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scientific_source_id: Mapped[int] = mapped_column(ForeignKey("scientific_source.id"))
    path: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(BigInteger)
    rows: Mapped[int] = mapped_column(Integer)


class ProvenanceEvent(Base):
    """Loads, cross-matches and merges. Rows created by a cross-match point back here so
    the match can be reversed (delete rows with that provenance_event_id)."""

    __tablename__ = "provenance_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingestion_job_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_job.id"))
    event_type: Mapped[str] = mapped_column(String(40))  # load | crossmatch | merge
    dataset: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("event_type", "dataset", "reason"),)


class Publication(Base):
    __tablename__ = "publication"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bibcode: Mapped[str] = mapped_column(Text, unique=True)
    # Display reference exactly as the archive gave it (e.g. "Bonomo et al. 2023").
    citation: Mapped[str | None] = mapped_column(Text)


# ------------------------------------------------------------------------------ objects


class CelestialObject(Base):
    __tablename__ = "celestial_object"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Stable load key, e.g. "gaia_dr3:4472832130942575872", "horizons:Mars". Makes loads idempotent.
    natural_key: Mapped[str] = mapped_column(Text, unique=True)
    object_type: Mapped[str] = mapped_column(String(40))
    primary_name: Mapped[str] = mapped_column(Text)
    # e.g. a planet's host star, when the archive's own identifier links them.
    parent_object_id: Mapped[int | None] = mapped_column(ForeignKey("celestial_object.id"))
    parent_link_reason: Mapped[str | None] = mapped_column(Text)
    created_by_job_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_job.id"))
    __table_args__ = (Index("ix_celestial_object_parent_object_id", "parent_object_id"),)


class _Sourced:
    """Columns every scientific row carries (§5: no value without a raw-file link)."""

    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_file.id"))
    source_row: Mapped[int] = mapped_column(Integer)
    source_record_id: Mapped[str] = mapped_column(Text)


class ExternalIdentifier(_Sourced, Base):
    __tablename__ = "external_identifier"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    object_id: Mapped[int] = mapped_column(
        ForeignKey("celestial_object.id", ondelete="CASCADE"), index=True
    )
    catalogue: Mapped[str] = mapped_column(String(40))  # gaia_dr3 | simbad_oid | horizons | ...
    identifier: Mapped[str] = mapped_column(Text)
    provenance_event_id: Mapped[int | None] = mapped_column(ForeignKey("provenance_event.id"))
    __table_args__ = (UniqueConstraint("catalogue", "identifier"),)


class ObjectAlias(_Sourced, Base):
    __tablename__ = "object_alias"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("celestial_object.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(Text)
    # Whitespace-collapsed, lower-case form for search ("M  45" -> "m 45").
    alias_normalized: Mapped[str] = mapped_column(Text, index=True)
    catalogue: Mapped[str] = mapped_column(String(40))
    provenance_event_id: Mapped[int | None] = mapped_column(ForeignKey("provenance_event.id"))
    __table_args__ = (
        UniqueConstraint("object_id", "alias"),
        Index(
            "ix_object_alias_alias_trgm",
            "alias_normalized",
            postgresql_using="gin",
            postgresql_ops={"alias_normalized": "gin_trgm_ops"},
        ),
    )


class Classification(_Sourced, Base):
    __tablename__ = "classification"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("celestial_object.id", ondelete="CASCADE"))
    scheme: Mapped[str] = mapped_column(String(40))  # simbad_otype | bj2021_flag | ...
    value: Mapped[str] = mapped_column(Text)
    provenance_event_id: Mapped[int | None] = mapped_column(ForeignKey("provenance_event.id"))
    __table_args__ = (UniqueConstraint("object_id", "scheme", "value"),)


class Measurement(_Sourced, Base):
    """One value of one quantity from one source row. Alternatives are separate rows."""

    __tablename__ = "measurement"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("celestial_object.id", ondelete="CASCADE"))
    quantity: Mapped[str] = mapped_column(String(60))
    value: Mapped[float | None] = mapped_column(Double)  # null when state is unknown
    unit: Mapped[str] = mapped_column(Text)  # unit exactly as the archive gave it
    uncertainty_lower: Mapped[float | None] = mapped_column(Double)
    uncertainty_upper: Mapped[float | None] = mapped_column(Double)
    # symmetric_1sigma | asymmetric_offsets | interval_bounds_p16_p84 | upper_limit | lower_limit
    uncertainty_type: Mapped[str | None] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(30))
    method: Mapped[str] = mapped_column(Text)
    solution_key: Mapped[str | None] = mapped_column(Text)  # e.g. the reference of a ps solution
    is_default: Mapped[bool | None] = mapped_column(Boolean)  # archive's own default flag
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("publication.id"))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("object_id", "quantity", "source_file_id", "source_row"),
        CheckConstraint(f"state IN ({_STATE_SQL})", name="state"),
        CheckConstraint(
            "value IS NOT NULL OR state IN ('unknown', 'not_applicable')", name="null_value"
        ),
        CheckConstraint("value IS NULL OR value = value", name="no_nan"),  # NaN != NaN
    )


class PositionSolution(_Sourced, Base):
    """A sky position (ICRS RA/Dec at an epoch) with an optional distance, or a state vector.

    A row with no distance is sky-view only (§5). The distance can come from a different
    source file than the position; it carries its own source columns.
    """

    __tablename__ = "position_solution"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("celestial_object.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))  # sky | state_vector
    frame: Mapped[str] = mapped_column(Text)
    epoch: Mapped[str] = mapped_column(Text)
    ra_deg: Mapped[float | None] = mapped_column(Double)
    dec_deg: Mapped[float | None] = mapped_column(Double)
    ra_error_mas: Mapped[float | None] = mapped_column(Double)
    dec_error_mas: Mapped[float | None] = mapped_column(Double)
    position_method: Mapped[str] = mapped_column(Text)
    position_state: Mapped[str] = mapped_column(String(30))
    distance_pc: Mapped[float | None] = mapped_column(Double)
    distance_lower_pc: Mapped[float | None] = mapped_column(Double)
    distance_upper_pc: Mapped[float | None] = mapped_column(Double)
    distance_interval: Mapped[str | None] = mapped_column(Text)
    distance_method: Mapped[str | None] = mapped_column(Text)
    distance_state: Mapped[str] = mapped_column(String(30))
    distance_source_file_id: Mapped[int | None] = mapped_column(ForeignKey("source_file.id"))
    distance_source_row: Mapped[int | None] = mapped_column(Integer)
    distance_source_record_id: Mapped[str | None] = mapped_column(Text)
    x_km: Mapped[float | None] = mapped_column(Double)
    y_km: Mapped[float | None] = mapped_column(Double)
    z_km: Mapped[float | None] = mapped_column(Double)
    vx_km_s: Mapped[float | None] = mapped_column(Double)
    vy_km_s: Mapped[float | None] = mapped_column(Double)
    vz_km_s: Mapped[float | None] = mapped_column(Double)
    is_adopted: Mapped[bool] = mapped_column(Boolean, default=True)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("publication.id"))
    # Derived (state "derived"): ICRS Cartesian position, origin at the Solar System
    # barycentre, in parsecs, computed by astronomy_core from this row's own position and
    # distance (or state vector). NULL for sky-only rows. `bary_xyz` is the same point as a
    # cube for GiST-indexed octree tile queries.
    bary_x_pc: Mapped[float | None] = mapped_column(Double)
    bary_y_pc: Mapped[float | None] = mapped_column(Double)
    bary_z_pc: Mapped[float | None] = mapped_column(Double)
    bary_xyz: Mapped[str | None] = mapped_column(Cube)
    derived_method: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("object_id", "kind", "source_file_id", "source_row"),
        Index("ix_position_solution_bary_xyz", "bary_xyz", postgresql_using="gist"),
        CheckConstraint(
            "(bary_x_pc IS NULL) = (derived_method IS NULL)", name="derived_has_method"
        ),
        CheckConstraint("kind IN ('sky', 'state_vector')", name="kind"),
        CheckConstraint(f"position_state IN ({_STATE_SQL})", name="position_state"),
        CheckConstraint(f"distance_state IN ({_STATE_SQL})", name="distance_state"),
        CheckConstraint(
            "distance_pc IS NULL OR (distance_source_file_id IS NOT NULL "
            "AND distance_source_row IS NOT NULL AND distance_source_record_id IS NOT NULL)",
            name="distance_sourced",
        ),
        CheckConstraint(
            "(distance_pc IS NULL) = (distance_state IN ('unknown', 'not_applicable'))",
            name="distance_state_matches",
        ),
    )


# ------------------------------------------------------------------- routes (used from M2)


class SavedRoute(Base):
    __tablename__ = "saved_route"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    origin_object_id: Mapped[int] = mapped_column(ForeignKey("celestial_object.id"))
    destination_object_id: Mapped[int] = mapped_column(ForeignKey("celestial_object.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RouteCalculation(Base):
    """A reproducible route: positions used, frame metadata (§7) and every model result (§9)."""

    __tablename__ = "route_calculation"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    saved_route_id: Mapped[int | None] = mapped_column(ForeignKey("saved_route.id"))
    origin_position_id: Mapped[int] = mapped_column(ForeignKey("position_solution.id"))
    destination_position_id: Mapped[int] = mapped_column(ForeignKey("position_solution.id"))
    distance_m: Mapped[float] = mapped_column(Double)
    frame_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model_results: Mapped[dict[str, Any]] = mapped_column(JSONB)
    code_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TraversalSession(Base):
    __tablename__ = "traversal_session"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    route_calculation_id: Mapped[int] = mapped_column(ForeignKey("route_calculation.id"))
    model_id: Mapped[str] = mapped_column(String(60))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'running', 'paused', 'cancelled', 'arrived')", name="status"
        ),
    )
