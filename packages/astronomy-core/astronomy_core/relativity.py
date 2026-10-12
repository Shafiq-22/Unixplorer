"""Travel-time models: one code path each (CLAUDE.md §9).

All models assume flat spacetime and static endpoints. Distances and speeds are astropy
Quantities; outputs are Quantities in SI-compatible units (times in Julian years for display
convenience, convertible with `.to(...)`).
"""

from __future__ import annotations

import astropy.units as u
import numpy as np

from astronomy_core.constants import JULIAN_YEAR, C
from astronomy_core.result import ModelDomainError, ModelResult

COMMON_ASSUMPTIONS: tuple[str, ...] = (
    "flat (Minkowski) spacetime: gravitational potentials along the route are ignored",
    "static endpoints: stellar and Galactic-rotation motion during the trip are ignored",
    "straight-line path between the endpoints in the chosen frame",
)


def _require(q: u.Quantity, unit: u.UnitBase, name: str) -> u.Quantity:
    if not isinstance(q, u.Quantity):
        raise TypeError(f"{name} must be an astropy Quantity, not {type(q).__name__}")
    if not q.unit.is_equivalent(unit):
        raise u.UnitsError(f"{name} has unit {q.unit}, expected something convertible to {unit}")
    if not np.isscalar(q.value) and np.ndim(q.value) != 0:
        raise ValueError(f"{name} must be a scalar Quantity")
    if not np.isfinite(q.value):
        raise ModelDomainError(f"{name} must be finite")
    return q


def _positive_distance(distance: u.Quantity) -> u.Quantity:
    _require(distance, u.m, "distance")
    if distance <= 0 * u.m:
        raise ModelDomainError("distance must be > 0")
    return distance


def _beta(speed: u.Quantity) -> float:
    return float((speed / C).to_value(u.dimensionless_unscaled))


def lorentz_factor(speed: u.Quantity) -> float:
    """γ = 1/sqrt(1 - v²/c²), defined only for massive travellers with 0 <= v < c."""
    _require(speed, u.m / u.s, "speed")
    beta = _beta(speed)
    if beta < 0:
        raise ModelDomainError("speed must be >= 0")
    if beta >= 1:
        raise ModelDomainError("γ is defined only for 0 <= v < c")
    return float(1.0 / np.sqrt(1.0 - beta * beta))


def classical_constant_speed(distance: u.Quantity, speed: u.Quantity) -> ModelResult:
    """Newtonian t = D / v. Not relativistic; any v > 0 is accepted and flagged when fast."""
    _positive_distance(distance)
    _require(speed, u.m / u.s, "speed")
    if speed <= 0 * u.m / u.s:
        raise ModelDomainError("speed must be > 0")
    beta = _beta(speed)
    warnings: list[str] = []
    if beta >= 1:
        warnings.append("v >= c: a classical (Newtonian) result has no physical meaning here")
    elif beta > 0.1:
        warnings.append("v > 0.1c: relativistic effects are significant; compare sr_inertial")
    return ModelResult(
        model_id="classical_constant_speed",
        model_version="1",
        inputs={"distance": distance, "speed": speed},
        outputs={"coordinate_time": (distance / speed).to(JULIAN_YEAR)},
        assumptions=(*COMMON_ASSUMPTIONS, "Newtonian kinematics (not relativistic)"),
        warnings=tuple(warnings),
    )


def sr_inertial(distance: u.Quantity, speed: u.Quantity) -> ModelResult:
    """Special relativity at constant speed: Δt = D/v, Δτ = Δt/γ. Massive, 0 < v < c only."""
    _positive_distance(distance)
    _require(speed, u.m / u.s, "speed")
    if speed <= 0 * u.m / u.s:
        raise ModelDomainError("speed must be > 0 for a trip of non-zero length")
    gamma = lorentz_factor(speed)  # raises for v >= c
    dt = (distance / speed).to(JULIAN_YEAR)
    return ModelResult(
        model_id="sr_inertial",
        model_version="1",
        inputs={"distance": distance, "speed": speed},
        outputs={
            "lorentz_factor": gamma,
            "coordinate_time": dt,
            "proper_time": (dt / gamma).to(JULIAN_YEAR),
        },
        assumptions=(
            *COMMON_ASSUMPTIONS,
            "massive traveller at constant speed for the whole trip (instant start and stop)",
        ),
    )


def sr_constant_proper_accel(distance: u.Quantity, acceleration: u.Quantity) -> ModelResult:
    """Constant proper acceleration a to the midpoint, then -a to rest (hyperbolic motion).

    Δτ = (2c/a)·arcosh(1 + aD/(2c²)),  Δt = (2c/a)·sinh(aΔτ/(2c)).
    """
    _positive_distance(distance)
    _require(acceleration, u.m / u.s**2, "acceleration")
    if acceleration <= 0 * u.m / u.s**2:
        raise ModelDomainError("proper acceleration must be > 0")
    a = acceleration
    x = (1 + a * distance / (2 * C**2)).to_value(u.dimensionless_unscaled)
    half_tau_rapidity = float(np.arccosh(x))  # = a·(Δτ/2)/c
    tau = (2 * C / a) * half_tau_rapidity
    t = (2 * C / a) * float(np.sinh(half_tau_rapidity))
    peak_gamma = x  # γ at the midpoint = cosh(aΔτ/2c) = 1 + aD/(2c²)
    peak_beta = float(np.tanh(half_tau_rapidity))
    return ModelResult(
        model_id="sr_constant_proper_accel",
        model_version="1",
        inputs={"distance": distance, "proper_acceleration": acceleration},
        outputs={
            "coordinate_time": t.to(JULIAN_YEAR),
            "proper_time": tau.to(JULIAN_YEAR),
            "peak_lorentz_factor": peak_gamma,
            "peak_speed": (peak_beta * C).to(u.m / u.s),
        },
        assumptions=(
            *COMMON_ASSUMPTIONS,
            "massive traveller starting and ending at rest; constant proper acceleration with "
            "a flip at the midpoint",
        ),
    )


def sr_constant_proper_accel_state(
    distance: u.Quantity, acceleration: u.Quantity, coordinate_time: u.Quantity
) -> dict[str, u.Quantity]:
    """Position, speed and elapsed proper time at a coordinate time 0 <= t <= Δt (v(t))."""
    total = sr_constant_proper_accel(distance, acceleration)
    _require(coordinate_time, u.s, "coordinate_time")
    dt_total = total.outputs["coordinate_time"]
    tau_total = total.outputs["proper_time"]
    if coordinate_time < 0 * u.s or coordinate_time > dt_total:
        raise ModelDomainError("coordinate_time must lie within [0, Δt]")
    a = acceleration
    half = dt_total / 2

    def accelerating(t: u.Quantity) -> tuple[u.Quantity, u.Quantity, u.Quantity]:
        at_c = (a * t / C).to_value(u.dimensionless_unscaled)
        root = float(np.sqrt(1.0 + at_c * at_c))
        x = (C**2 / a) * (root - 1.0)
        v = C * (at_c / root)
        tau = (C / a) * float(np.arcsinh(at_c))
        return x, v, tau

    if coordinate_time <= half:
        x, v, tau = accelerating(coordinate_time)
    else:  # the deceleration phase mirrors the acceleration phase in time
        x_m, v, tau_m = accelerating(dt_total - coordinate_time)
        x, tau = distance - x_m, tau_total - tau_m
    return {
        "position": x.to(distance.unit),
        "speed": v.to(u.m / u.s),
        "proper_time": tau.to(JULIAN_YEAR),
    }


def null_propagation(distance: u.Quantity) -> ModelResult:
    """v = c: light-travel (coordinate) time D/c. No proper time exists for a null path."""
    _positive_distance(distance)
    return ModelResult(
        model_id="null_propagation",
        model_version="1",
        inputs={"distance": distance},
        outputs={
            "coordinate_time": (distance / C).to(JULIAN_YEAR),
            "proper_time": "not defined: a null (light-like) path has no proper time",
        },
        assumptions=(*COMMON_ASSUMPTIONS, "signal travelling at exactly c in vacuum"),
    )


def hypothetical_ftl_effective(distance: u.Quantity, effective_speed: u.Quantity) -> ModelResult:
    """SPECULATIVE: t_eff = D / v_eff for v_eff > c. No γ, no proper time, no mechanism."""
    _positive_distance(distance)
    _require(effective_speed, u.m / u.s, "effective_speed")
    if _beta(effective_speed) <= 1:
        raise ModelDomainError("hypothetical_ftl_effective applies only to v_eff > c")
    return ModelResult(
        model_id="hypothetical_ftl_effective",
        model_version="1",
        status="speculative",
        inputs={"distance": distance, "effective_speed": effective_speed},
        outputs={
            "effective_coordinate_time": (distance / effective_speed).to(JULIAN_YEAR),
            "proper_time": "not defined by this model",
        },
        assumptions=(
            *COMMON_ASSUMPTIONS,
            "speculative: no known physics allows v > c; this is an arithmetic comparison only",
        ),
        warnings=(
            "Speculative: no mechanism is claimed",
            "Causality is not addressed and is not claimed to be preserved",
            "Lorentz factor and proper time do not apply and are not computed",
        ),
    )
