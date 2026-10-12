"""Pydantic response models: the API's public contract (exported to packages/shared-types)."""

from __future__ import annotations

from typing import Any, Literal

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


# ----------------------------------------------------------------------------- objects


class Publication(BaseModel):
    bibcode: str
    citation: str | None


class SourceRef(BaseModel):
    """Where a value came from: raw file + row, the archive, release and retrieval time."""

    source_record_id: str = Field(description="<raw file path>#row=<0-based row>")
    dataset: str
    archive: str
    release: str
    retrieved_at: str
    publication: Publication | None = None


class Uncertainty(BaseModel):
    lower: float | None
    upper: float | None
    type: str = Field(
        description="symmetric_1sigma | asymmetric_offsets | interval_bounds_p16_p84 | "
        "upper_limit | lower_limit"
    )


class Measurement(BaseModel):
    quantity: str
    value: float | None
    unit: str
    uncertainty: Uncertainty | None
    state: str
    method: str
    solution_key: str | None
    is_default: bool | None
    source: SourceRef


class Distance(BaseModel):
    value_pc: float
    lower_pc: float | None
    upper_pc: float | None
    interval: str | None
    method: str
    state: str
    source: SourceRef


class Cartesian(BaseModel):
    """Derived ICRS Cartesian position (origin: Solar System barycentre), parsecs."""

    x_pc: float
    y_pc: float
    z_pc: float
    state: Literal["derived"] = "derived"
    method: str


class StateVector(BaseModel):
    x_km: float
    y_km: float
    z_km: float
    vx_km_s: float
    vy_km_s: float
    vz_km_s: float


class Position(BaseModel):
    id: int
    kind: Literal["sky", "state_vector"]
    frame: str
    epoch: str
    ra_deg: float | None
    dec_deg: float | None
    ra_error_mas: float | None
    dec_error_mas: float | None
    position_state: str
    position_method: str
    distance_state: str
    distance: Distance | None = Field(description="null: sky view only, not a 3D position")
    state_vector: StateVector | None
    cartesian: Cartesian | None
    source: SourceRef


class ObjectSummary(BaseModel):
    id: int
    primary_name: str = Field(description="catalogue name (e.g. Gaia DR3 designation)")
    display_name: str = Field(description="SIMBAD main identifier when known, else primary_name")
    object_type: str
    has_3d_position: bool
    matched_alias: str | None = None


class Identifier(BaseModel):
    catalogue: str
    identifier: str
    source_record_id: str


class Classification(BaseModel):
    scheme: str
    value: str
    source_record_id: str


class ParentLink(BaseModel):
    object: ObjectSummary
    reason: str


class Dossier(BaseModel):
    object: ObjectSummary
    identifiers: list[Identifier]
    aliases: list[str]
    classifications: list[Classification]
    measurements: list[Measurement]
    positions: list[Position]
    parent: ParentLink | None
    children: list[ObjectSummary]


class SearchResults(BaseModel):
    query: str
    results: list[ObjectSummary]


# ------------------------------------------------------------------------------- tiles


class TileStar(BaseModel):
    id: int
    x_pc: float
    y_pc: float
    z_pc: float
    phot_g_mean_mag: float | None


class StarTile(BaseModel):
    level: int
    ix: int
    iy: int
    iz: int
    bounds_pc: list[float] | None = Field(
        description="[xmin, ymin, zmin, xmax, ymax, zmax]; null for the level-0 root tile"
    )
    frame: str
    complete: bool = Field(description="true when every star in the cell is included")
    total_in_cell: int
    stars: list[TileStar]


# ------------------------------------------------------------------------------ routes


class QuantityValue(BaseModel):
    value: float
    unit: str


ModelOutput = QuantityValue | float | str


class ModelEntry(BaseModel):
    """One model's result (CLAUDE.md §9), or its refusal when the inputs are out of domain."""

    model_id: str
    model_version: str | None = None
    status: Literal["physical", "speculative"] | None = None
    inputs: dict[str, ModelOutput] | None = None
    outputs: dict[str, ModelOutput] | None = None
    assumptions: list[str] = []
    warnings: list[str] = []
    at_distance_lower: dict[str, QuantityValue] | None = None
    at_distance_upper: dict[str, QuantityValue] | None = None
    refused: str | None = Field(default=None, description="why the model refused these inputs")


class RouteRequest(BaseModel):
    origin_id: int
    destination_id: int
    speed_fraction_c: float = Field(gt=0, description="for classical and sr_inertial; not clamped")
    proper_acceleration_g: float = Field(default=1.0, gt=0)
    ftl_speed_fraction_c: float = Field(default=10.0, gt=0, description="speculative model only")


class RouteEndpoint(BaseModel):
    object: ObjectSummary
    position_id: int
    epoch: str
    position_method: str
    distance_method: str | None


class RouteDistanceOut(BaseModel):
    value_pc: float
    lower_pc: float
    upper_pc: float
    # The same distances in astronomical units (astropy conversion), for planetary routes.
    value_au: float
    lower_au: float
    upper_au: float
    method: str


class RouteResult(BaseModel):
    id: int
    origin: RouteEndpoint
    destination: RouteEndpoint
    distance: RouteDistanceOut
    parameters: RouteRequest
    frame: dict[str, Any]
    models: list[ModelEntry]
    code_version: str


class TrajectorySample(BaseModel):
    coordinate_time_yr: float
    proper_time_yr: float | None
    fraction: float
    speed_c: float


class Trajectory(BaseModel):
    route_id: int
    model_id: str
    model_version: str
    status: Literal["physical", "speculative"]
    proper_time_defined: bool
    samples: list[TrajectorySample]


TraversalStatus = Literal["planned", "running", "paused", "cancelled", "arrived"]


class TraversalCreate(BaseModel):
    route_id: int
    model_id: str


class TraversalUpdate(BaseModel):
    status: TraversalStatus
    coordinate_time_yr: float | None = Field(default=None, ge=0)


class Traversal(BaseModel):
    id: int
    route_id: int
    model_id: str
    status: TraversalStatus
    coordinate_time_yr: float


# ------------------------------------------------------------------------ solar system


class DistanceFromSun(BaseModel):
    value_au: float
    value_km: float
    state: Literal["derived"] = "derived"
    method: str


class SolarSystemBody(BaseModel):
    object: ObjectSummary
    position: Position
    distance_from_sun: DistanceFromSun | None


class SolarSystem(BaseModel):
    epoch: str = Field(description="as stated by JPL Horizons for the snapshot")
    frame: str
    bodies: list[SolarSystemBody]
