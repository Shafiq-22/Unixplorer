"""Frames and distances (CLAUDE.md §7, §10)."""

from __future__ import annotations

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import Galactocentric, SkyCoord, galactocentric_frame_defaults

from astronomy_core.distances import bailer_jones_distance, inverse_parallax_distance
from astronomy_core.frames import (
    GALACTOCENTRIC_DEFAULTS,
    frame_metadata,
    galactocentric_frame,
    icrs_position,
    separation_3d,
)
from astronomy_core.result import ModelDomainError


def test_frame_is_pinned_to_v4_0() -> None:
    meta = frame_metadata()
    assert meta["galactocentric_defaults"] == GALACTOCENTRIC_DEFAULTS == "v4.0"
    # CLAUDE.md §7 documents v4.0 as R0 = 8.122 kpc, z_sun = 20.8 pc.
    assert meta["galcen_distance"]["value"] == pytest.approx(8.122, rel=1e-12)
    assert meta["z_sun"]["value"] == pytest.approx(20.8, rel=1e-12)
    frame = galactocentric_frame()
    with galactocentric_frame_defaults.set("v4.0"):
        ref = Galactocentric()
    for attr in ("galcen_distance", "z_sun", "roll"):
        assert getattr(frame, attr) == getattr(ref, attr)


def test_frame_ignores_changes_to_astropy_session_default() -> None:
    with galactocentric_frame_defaults.set("pre-v4.0"):
        frame = galactocentric_frame()
    assert frame.galcen_distance.to_value(u.kpc) == pytest.approx(8.122, rel=1e-12)


def _pair() -> tuple[SkyCoord, SkyCoord]:
    # Arbitrary test positions (not catalogue values).
    a = icrs_position(10 * u.deg, -20 * u.deg, 3.0 * u.pc)
    b = icrs_position(200 * u.deg, 45 * u.deg, 750.0 * u.pc)
    return a, b


def test_heliocentric_and_galactocentric_distances_agree() -> None:
    a, b = _pair()
    helio = separation_3d(a, b, frame="heliocentric").to_value(u.pc)
    galcen = separation_3d(a, b, frame="galactocentric").to_value(u.pc)
    assert galcen == pytest.approx(helio, rel=1e-9)


def test_sgr_a_icrs_to_galactocentric_matches_astropy() -> None:
    """Sgr A*'s position (the frame's own galcen_coord) at R0 lands at the frame origin."""
    frame = galactocentric_frame()
    centre = frame.galcen_coord
    c = SkyCoord(ra=centre.ra, dec=centre.dec, distance=frame.galcen_distance, frame="icrs")
    xyz = c.transform_to(frame).cartesian.xyz.to_value(u.pc)
    assert np.allclose(xyz, 0.0, atol=1e-6)  # micro-parsec tolerance on an 8 kpc transform
    with galactocentric_frame_defaults.set("v4.0"):
        direct = c.transform_to(Galactocentric()).cartesian.xyz.to_value(u.pc)
    assert np.allclose(xyz, direct, rtol=0, atol=1e-9)


def test_no_3d_position_without_distance() -> None:
    with pytest.raises(ValueError, match="sky view only"):
        icrs_position(10 * u.deg, 20 * u.deg, None)  # type: ignore[arg-type]


def test_inverse_parallax_guard() -> None:
    with pytest.raises(ModelDomainError):
        inverse_parallax_distance(-1 * u.mas, 10.0)
    with pytest.raises(ModelDomainError):
        inverse_parallax_distance(10 * u.mas, 4.9)
    d = inverse_parallax_distance(100 * u.mas, 50.0)
    assert d.value.to_value(u.pc) == pytest.approx(10.0, rel=1e-12)
    assert d.lower < d.value < d.upper


def test_bailer_jones_keeps_asymmetric_interval_and_unknown() -> None:
    d = bailer_jones_distance(10 * u.pc, 9.5 * u.pc, 10.7 * u.pc, "geometric")
    assert d is not None and d.method == "bailer_jones_2021_geometric"
    assert (d.value - d.lower) != (d.upper - d.value)
    assert bailer_jones_distance(None, None, None, "photogeometric") is None
    with pytest.raises(ModelDomainError):
        bailer_jones_distance(10 * u.pc, 11 * u.pc, 12 * u.pc, "geometric")
