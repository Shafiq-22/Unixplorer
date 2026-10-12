"""Endpoint geometry and route distance with its uncertainty range.

An endpoint is either a fixed point (e.g. a Horizons state vector) or a point anywhere on a
line-of-sight segment between the lower and upper bounds of its distance interval. The route
distance range is the exact minimum and maximum of |A - B| over those segments.
"""

from __future__ import annotations

from dataclasses import dataclass

import astropy.units as u
import numpy as np


@dataclass(frozen=True)
class Endpoint:
    name: str
    #: Adopted position (ICRS axes, barycentric), parsecs.
    position_pc: np.ndarray
    #: Positions at the lower and upper bounds of the distance interval along the line of
    #: sight; equal to position_pc when the endpoint has no distance interval.
    lower_pc: np.ndarray
    upper_pc: np.ndarray
    distance_method: str

    @classmethod
    def fixed(cls, name: str, xyz: u.Quantity, method: str) -> Endpoint:
        p = np.asarray(xyz.to_value(u.pc), dtype=np.float64)
        return cls(name, p, p, p, method)

    @classmethod
    def along_sight_line(
        cls, name: str, xyz: u.Quantity, lower: u.Quantity, upper: u.Quantity, method: str
    ) -> Endpoint:
        """A star at `xyz` whose distance lies in [lower, upper] along its direction from the
        barycentre (the line of sight of an ICRS position)."""
        p = np.asarray(xyz.to_value(u.pc), dtype=np.float64)
        r = float(np.linalg.norm(p))
        if r == 0:
            raise ValueError("cannot define a line of sight for a point at the origin")
        unit = p / r
        return cls(name, p, unit * lower.to_value(u.pc), unit * upper.to_value(u.pc), method)


def _segment_distance(p0: np.ndarray, p1: np.ndarray, q0: np.ndarray, q1: np.ndarray) -> float:
    """Exact minimum distance between segments p0-p1 and q0-q1 (degenerate segments allowed).

    Standard closest-points algorithm (clamped parameters on both segments).
    """
    d1, d2, r = p1 - p0, q1 - q0, p0 - q0
    a, e, f = float(d1 @ d1), float(d2 @ d2), float(d2 @ r)
    eps = 1e-300
    if a <= eps and e <= eps:
        return float(np.linalg.norm(r))
    if a <= eps:
        s, t = 0.0, min(max(f / e, 0.0), 1.0)
    else:
        c = float(d1 @ r)
        if e <= eps:
            t, s = 0.0, min(max(-c / a, 0.0), 1.0)
        else:
            b = float(d1 @ d2)
            denom = a * e - b * b
            s = min(max((b * f - c * e) / denom, 0.0), 1.0) if denom > eps else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, min(max(-c / a, 0.0), 1.0)
            elif t > 1.0:
                t, s = 1.0, min(max((b - c) / a, 0.0), 1.0)
    return float(np.linalg.norm((p0 + d1 * s) - (q0 + d2 * t)))


@dataclass(frozen=True)
class RouteDistance:
    value: u.Quantity
    lower: u.Quantity
    upper: u.Quantity
    method: str


def route_distance(a: Endpoint, b: Endpoint) -> RouteDistance:
    """Distance between adopted positions, with the exact range over both distance intervals."""
    value = float(np.linalg.norm(a.position_pc - b.position_pc))
    # Maximum of a convex function over a box is at a vertex: check the four corner pairs.
    upper = max(
        float(np.linalg.norm(pa - pb))
        for pa in (a.lower_pc, a.upper_pc)
        for pb in (b.lower_pc, b.upper_pc)
    )
    lower = _segment_distance(a.lower_pc, a.upper_pc, b.lower_pc, b.upper_pc)
    return RouteDistance(
        value=value * u.pc,
        lower=lower * u.pc,
        upper=upper * u.pc,
        method=(
            "straight line between adopted positions (ICRS axes, barycentric); range = exact "
            "min/max over each endpoint's distance interval along its line of sight, "
            "directions held fixed"
        ),
    )
