"""Run every travel model for one route, side by side (CLAUDE.md §9)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import astropy.units as u
import numpy as np

from astronomy_core.constants import JULIAN_YEAR, STANDARD_GRAVITY, C
from astronomy_core.relativity import (
    classical_constant_speed,
    hypothetical_ftl_effective,
    null_propagation,
    sr_constant_proper_accel,
    sr_constant_proper_accel_state,
    sr_inertial,
)
from astronomy_core.result import ModelDomainError, ModelResult
from route_planner.geometry import RouteDistance

MODEL_IDS = (
    "classical_constant_speed",
    "sr_inertial",
    "sr_constant_proper_accel",
    "null_propagation",
    "hypothetical_ftl_effective",
)

ROUTE_ASSUMPTIONS = (
    "endpoint positions at their catalogue epochs (Gaia DR3 J2016.0; Horizons J2016.0 TDB)",
    "proper motions of the endpoints during the trip are not applied",
)


@dataclass(frozen=True)
class TravelParameters:
    """User-chosen speeds. Never clamped: out-of-domain values give a refusal, not a fudge."""

    speed_fraction_c: float  # classical_constant_speed and sr_inertial
    proper_acceleration_g: float  # sr_constant_proper_accel, in units of standard gravity
    ftl_speed_fraction_c: float  # hypothetical_ftl_effective

    @property
    def speed(self) -> u.Quantity:
        return self.speed_fraction_c * C

    @property
    def acceleration(self) -> u.Quantity:
        return self.proper_acceleration_g * STANDARD_GRAVITY

    @property
    def ftl_speed(self) -> u.Quantity:
        return self.ftl_speed_fraction_c * C


def _runner(model_id: str, p: TravelParameters) -> Callable[[u.Quantity], ModelResult]:
    return {
        "classical_constant_speed": lambda d: classical_constant_speed(d, p.speed),
        "sr_inertial": lambda d: sr_inertial(d, p.speed),
        "sr_constant_proper_accel": lambda d: sr_constant_proper_accel(d, p.acceleration),
        "null_propagation": null_propagation,
        "hypothetical_ftl_effective": lambda d: hypothetical_ftl_effective(d, p.ftl_speed),
    }[model_id]


def _time_outputs(result: ModelResult) -> dict[str, Any]:
    return {k: v for k, v in result.to_dict()["outputs"].items() if isinstance(v, dict)}


def plan(distance: RouteDistance, params: TravelParameters) -> list[dict[str, Any]]:
    """One entry per model: the full result at the adopted distance, the same outputs at the
    lower and upper distance bounds, or the refusal if the parameters are out of domain."""
    entries: list[dict[str, Any]] = []
    for model_id in MODEL_IDS:
        run = _runner(model_id, params)
        try:
            central = run(distance.value)
            low, high = run(distance.lower), run(distance.upper)
        except ModelDomainError as exc:
            entries.append({"model_id": model_id, "refused": str(exc)})
            continue
        d = central.to_dict()
        d["assumptions"] = [*d["assumptions"], *ROUTE_ASSUMPTIONS]
        d["at_distance_lower"] = _time_outputs(low)
        d["at_distance_upper"] = _time_outputs(high)
        entries.append(d)
    return entries


def trajectory(
    model_id: str, distance: u.Quantity, params: TravelParameters, samples: int
) -> dict[str, Any]:
    """Backend-computed states for the UI to interpolate between (CLAUDE.md §4).

    Each sample: coordinate time (yr), proper time (yr, or null where undefined), fraction of
    the route covered, and speed as a fraction of c.
    """
    if samples < 2:
        raise ValueError("need at least 2 samples")
    result = _runner(model_id, params)(distance)
    out = result.outputs
    total_key = (
        "effective_coordinate_time"
        if model_id == "hypothetical_ftl_effective"
        else "coordinate_time"
    )
    total = out[total_key]
    ts = np.linspace(0.0, total.to_value(JULIAN_YEAR), samples)
    rows: list[dict[str, float | None]] = []
    if model_id == "sr_constant_proper_accel":
        for t in ts:
            st = sr_constant_proper_accel_state(distance, params.acceleration, t * JULIAN_YEAR)
            rows.append(
                {
                    "coordinate_time_yr": float(t),
                    "proper_time_yr": float(st["proper_time"].to_value(JULIAN_YEAR)),
                    "fraction": float(
                        (st["position"] / distance).to_value(u.dimensionless_unscaled)
                    ),
                    "speed_c": float((st["speed"] / C).to_value(u.dimensionless_unscaled)),
                }
            )
    else:
        frac_speed = {
            "classical_constant_speed": params.speed_fraction_c,
            "sr_inertial": params.speed_fraction_c,
            "null_propagation": 1.0,
            "hypothetical_ftl_effective": params.ftl_speed_fraction_c,
        }[model_id]
        gamma = out.get("lorentz_factor") if model_id == "sr_inertial" else None
        for t in ts:
            frac = float(t / total.to_value(JULIAN_YEAR)) if total.value else 1.0
            rows.append(
                {
                    "coordinate_time_yr": float(t),
                    "proper_time_yr": float(t / gamma) if gamma else None,
                    "fraction": min(frac, 1.0),
                    "speed_c": frac_speed,
                }
            )
    return {
        "model_id": result.model_id,
        "model_version": result.model_version,
        "status": result.status,
        "proper_time_defined": model_id in ("sr_inertial", "sr_constant_proper_accel"),
        "samples": rows,
    }
