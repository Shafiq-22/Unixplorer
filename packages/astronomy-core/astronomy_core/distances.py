"""Distance solutions for Gaia stars (CLAUDE.md §7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import astropy.units as u
import numpy as np

from astronomy_core.result import ModelDomainError

#: Below this parallax_over_error, or for non-positive parallax, 1/parallax is refused.
MIN_PARALLAX_OVER_ERROR = 5.0

BailerJonesKind = Literal["geometric", "photogeometric"]


@dataclass(frozen=True)
class DistanceSolution:
    """A distance with asymmetric uncertainty and the method that produced it."""

    value: u.Quantity
    lower: u.Quantity  # lower bound of the stated interval (not an error bar)
    upper: u.Quantity
    interval: str
    method: str
    source: str


def bailer_jones_distance(
    median: u.Quantity | None,
    p16: u.Quantity | None,
    p84: u.Quantity | None,
    kind: BailerJonesKind,
) -> DistanceSolution | None:
    """Adopt a Bailer-Jones et al. (2021) estimate; None when the catalogue has no value."""
    if median is None or p16 is None or p84 is None:
        return None
    for name, q in (("median", median), ("p16", p16), ("p84", p84)):
        if not q.unit.is_equivalent(u.pc) or not np.isfinite(q.value):
            raise ModelDomainError(f"{name} must be a finite length")
    if not (p16 <= median <= p84):
        raise ModelDomainError("expected p16 <= median <= p84")
    return DistanceSolution(
        value=median.to(u.pc),
        lower=p16.to(u.pc),
        upper=p84.to(u.pc),
        interval="16th-84th percentile of the posterior",
        method=f"bailer_jones_2021_{kind}",
        source="Bailer-Jones et al. (2021)",
    )


def inverse_parallax_distance(parallax: u.Quantity, parallax_over_error: float) -> DistanceSolution:
    """Naive 1/parallax, refused when parallax <= 0 or parallax_over_error < 5 (CLAUDE.md §7)."""
    if not parallax.unit.is_equivalent(u.mas):
        raise u.UnitsError("parallax must be an angle")
    if parallax <= 0 * u.mas:
        raise ModelDomainError("1/parallax is undefined for non-positive parallax")
    if not parallax_over_error >= MIN_PARALLAX_OVER_ERROR:
        raise ModelDomainError(
            f"1/parallax refused: parallax_over_error {parallax_over_error} < "
            f"{MIN_PARALLAX_OVER_ERROR}"
        )
    sigma = parallax / parallax_over_error
    d = parallax.to(u.pc, equivalencies=u.parallax())
    return DistanceSolution(
        value=d,
        lower=(parallax + sigma).to(u.pc, equivalencies=u.parallax()),
        upper=(parallax - sigma).to(u.pc, equivalencies=u.parallax()),
        interval="1/(parallax ± parallax_error)",
        method="inverse_parallax",
        source="Gaia DR3 parallax",
    )
