"""Coordinate frames with pinned Galactocentric parameters (CLAUDE.md §7).

The galactocentric frame is built from astropy's named parameter set `GALACTOCENTRIC_DEFAULTS`
and every result records that name and the astropy version, so a change in astropy's
"latest" defaults cannot silently move the galaxy.
"""

from __future__ import annotations

from typing import Any

import astropy
import astropy.units as u
from astropy.coordinates import (
    ICRS,
    CartesianRepresentation,
    Galactocentric,
    SkyCoord,
    galactocentric_frame_defaults,
)
from astropy.time import Time

GALACTOCENTRIC_DEFAULTS = "v4.0"


def galactocentric_frame() -> Galactocentric:
    """A Galactocentric frame with every parameter set explicitly from the pinned defaults."""
    params = galactocentric_frame_defaults.get_from_registry(GALACTOCENTRIC_DEFAULTS)
    return Galactocentric(**params["parameters"])


def frame_metadata() -> dict[str, Any]:
    """What to store with every route_calculation so it can be reproduced."""
    reg = galactocentric_frame_defaults.get_from_registry(GALACTOCENTRIC_DEFAULTS)
    p = reg["parameters"]
    return {
        "galactocentric_defaults": GALACTOCENTRIC_DEFAULTS,
        "astropy_version": astropy.__version__,
        "galcen_distance": {"value": float(p["galcen_distance"].to_value(u.kpc)), "unit": "kpc"},
        "z_sun": {"value": float(p["z_sun"].to_value(u.pc)), "unit": "pc"},
        "references": {k: v for k, v in reg["references"].items() if v is not None},
    }


def icrs_position(
    ra: u.Quantity, dec: u.Quantity, distance: u.Quantity, obstime: Time | None = None
) -> SkyCoord:
    """A 3D ICRS position. Requires a distance: RA/Dec alone is not a 3D position (§5)."""
    if distance is None:
        raise ValueError("no distance solution: sky view only, not a 3D position")
    return SkyCoord(ICRS(ra=ra, dec=dec, distance=distance), obstime=obstime)


def heliocentric_cartesian(coord: SkyCoord) -> CartesianRepresentation:
    """ICRS axes centred on the Sun (strictly the solar-system barycentre for ICRS)."""
    return coord.icrs.cartesian


def galactocentric_cartesian(coord: SkyCoord) -> CartesianRepresentation:
    return coord.transform_to(galactocentric_frame()).cartesian


def separation_3d(a: SkyCoord, b: SkyCoord, *, frame: str = "heliocentric") -> u.Quantity:
    """Straight-line distance between two 3D positions in the chosen frame."""
    to_cart = heliocentric_cartesian if frame == "heliocentric" else galactocentric_cartesian
    if frame not in ("heliocentric", "galactocentric"):
        raise ValueError(f"unknown frame {frame!r}")
    d = to_cart(a) - to_cart(b)
    return d.norm()


#: Identifies the derivation stored with derived Cartesian positions.
CARTESIAN_METHOD = "astronomy_core.frames.icrs_barycentric_xyz v1"


def icrs_barycentric_xyz(
    ra: u.Quantity, dec: u.Quantity, distance: u.Quantity
) -> tuple[u.Quantity, u.Quantity, u.Quantity]:
    """Vectorised ICRS Cartesian coordinates (origin: Solar System barycentre, ICRS axes).

    Arrays in, arrays out, so a whole catalogue converts in one call. Every element needs a
    distance; positions without one stay sky-only and must not be passed here (§5).
    """
    if distance is None:
        raise ValueError("no distance solution: sky view only, not a 3D position")
    rep = SkyCoord(ra=ra, dec=dec, distance=distance, frame="icrs").cartesian
    return rep.x.to(u.pc), rep.y.to(u.pc), rep.z.to(u.pc)


def state_vector_xyz(
    x: u.Quantity, y: u.Quantity, z: u.Quantity
) -> tuple[u.Quantity, u.Quantity, u.Quantity]:
    """Horizons ICRF barycentric state-vector position, as parsecs on the same ICRS axes."""
    return x.to(u.pc), y.to(u.pc), z.to(u.pc)


def separation(a: u.Quantity, b: u.Quantity) -> u.Quantity:
    """Euclidean distance between two Cartesian positions (length-3 Quantities)."""
    import numpy as np

    d = np.asarray((a - b).to_value(u.pc), dtype=np.float64)
    if d.shape != (3,):
        raise ValueError("positions must be length-3 Cartesian vectors")
    return float(np.sqrt(d @ d)) * u.pc
