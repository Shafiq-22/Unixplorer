"""CLAUDE.md §10 physics regression suite (release-blocking).

Closed forms are asserted at rel=1e-9 against the formula with the distance as an input.
The §10 table values are then checked at the precision the table quotes them.
"""

from __future__ import annotations

import math

import astropy.units as u
import pytest

from astronomy_core.constants import JULIAN_YEAR, STANDARD_GRAVITY, C
from astronomy_core.relativity import (
    classical_constant_speed,
    hypothetical_ftl_effective,
    lorentz_factor,
    null_propagation,
    sr_constant_proper_accel,
    sr_constant_proper_accel_state,
    sr_inertial,
)
from astronomy_core.result import ModelDomainError

PROXIMA = 1.3012 * u.pc  # §10 input distance, not a measurement
SGR_A = 8.122 * u.kpc  # §10 input distance, not a measurement
G = STANDARD_GRAVITY


def yr(q: u.Quantity) -> float:
    return float(q.to_value(JULIAN_YEAR))


def test_standard_gravity_and_year() -> None:
    assert STANDARD_GRAVITY.to_value(u.m / u.s**2) == 9.80665
    assert (1 * JULIAN_YEAR).to_value(u.d) == 365.25
    assert C.to_value(u.m / u.s) == 299_792_458


@pytest.mark.parametrize(
    ("beta", "expected", "rel"),
    [(0.0, 1.0, 1e-12), (0.6, 1.25, 1e-12), (0.8, 5 / 3, 1e-12), (0.99, 7.0888, 1e-4)],
)
def test_lorentz_factor(beta: float, expected: float, rel: float) -> None:
    assert lorentz_factor(beta * C) == pytest.approx(expected, rel=rel)


@pytest.mark.parametrize("beta", [1.0, 2.0])
def test_sr_inertial_rejects_v_at_or_above_c(beta: float) -> None:
    with pytest.raises(ModelDomainError):
        sr_inertial(SGR_A, beta * C)


def test_sr_inertial_matches_formula_and_table() -> None:
    r = sr_inertial(SGR_A, 0.99 * C)
    dt = (SGR_A / (0.99 * C)).to(JULIAN_YEAR)
    gamma = 1 / math.sqrt(1 - 0.99**2)
    assert yr(r.outputs["coordinate_time"]) == pytest.approx(yr(dt), rel=1e-9)
    assert yr(r.outputs["proper_time"]) == pytest.approx(yr(dt) / gamma, rel=1e-9)
    # §10: Δt ≈ 26 758 yr, Δτ ≈ 3 775 yr (quoted to the nearest year)
    assert yr(r.outputs["coordinate_time"]) == pytest.approx(26_758, abs=0.5)
    assert yr(r.outputs["proper_time"]) == pytest.approx(3_775, abs=0.5)


def _accel_formula(distance: u.Quantity) -> tuple[float, float]:
    x = float((1 + G * distance / (2 * C**2)).to_value(u.dimensionless_unscaled))
    tau = (2 * C / G) * math.acosh(x)
    t = (2 * C / G) * math.sinh(math.acosh(x))
    return yr(tau), yr(t)


@pytest.mark.parametrize(
    ("distance", "tau_table", "tau_abs", "t_table", "t_abs", "light_table", "light_abs"),
    [
        (PROXIMA, 3.541, 5e-4, 5.870, 5e-4, 4.244, 5e-4),
        (SGR_A, 19.79, 5e-3, 26_492, 0.5, 26_490, 0.5),
    ],
)
def test_constant_proper_accel_1g(
    distance: u.Quantity,
    tau_table: float,
    tau_abs: float,
    t_table: float,
    t_abs: float,
    light_table: float,
    light_abs: float,
) -> None:
    r = sr_constant_proper_accel(distance, 1 * G)
    tau_f, t_f = _accel_formula(distance)
    assert yr(r.outputs["proper_time"]) == pytest.approx(tau_f, rel=1e-9)
    assert yr(r.outputs["coordinate_time"]) == pytest.approx(t_f, rel=1e-9)
    # Table values at the precision quoted in §10.
    assert yr(r.outputs["proper_time"]) == pytest.approx(tau_table, abs=tau_abs)
    assert yr(r.outputs["coordinate_time"]) == pytest.approx(t_table, abs=t_abs)
    light = null_propagation(distance).outputs["coordinate_time"]
    assert yr(light) == pytest.approx(light_table, abs=light_abs)
    # Physical sanity: the ship never beats light in coordinate time.
    assert r.outputs["coordinate_time"] > light


def test_constant_proper_accel_is_not_d_over_v() -> None:
    r = sr_constant_proper_accel(PROXIMA, 1 * G)
    peak = r.outputs["peak_speed"]
    assert r.outputs["coordinate_time"] > (PROXIMA / peak).to(JULIAN_YEAR)


def test_constant_proper_accel_state_is_continuous_and_symmetric() -> None:
    total = sr_constant_proper_accel(PROXIMA, 1 * G)
    dt = total.outputs["coordinate_time"]
    start = sr_constant_proper_accel_state(PROXIMA, 1 * G, 0 * u.s)
    mid = sr_constant_proper_accel_state(PROXIMA, 1 * G, dt / 2)
    end = sr_constant_proper_accel_state(PROXIMA, 1 * G, dt)
    assert start["position"].to_value(u.pc) == pytest.approx(0.0, abs=1e-12)
    assert mid["position"].to_value(u.pc) == pytest.approx(PROXIMA.to_value(u.pc) / 2, rel=1e-9)
    assert end["position"].to_value(u.pc) == pytest.approx(PROXIMA.to_value(u.pc), rel=1e-9)
    assert yr(end["proper_time"]) == pytest.approx(yr(total.outputs["proper_time"]), rel=1e-9)
    assert mid["speed"].to_value(u.m / u.s) == pytest.approx(
        total.outputs["peak_speed"].to_value(u.m / u.s), rel=1e-9
    )
    assert end["speed"].to_value(u.m / u.s) == pytest.approx(0.0, abs=1e-3)
    q1 = sr_constant_proper_accel_state(PROXIMA, 1 * G, dt / 4)
    q3 = sr_constant_proper_accel_state(PROXIMA, 1 * G, 3 * dt / 4)
    assert q1["speed"].to_value(u.m / u.s) == pytest.approx(
        q3["speed"].to_value(u.m / u.s), rel=1e-9
    )


def test_null_propagation_has_no_proper_time() -> None:
    r = null_propagation(SGR_A)
    assert yr(r.outputs["coordinate_time"]) == pytest.approx(yr(SGR_A / C), rel=1e-12)
    assert isinstance(r.outputs["proper_time"], str)
    assert "not defined" in r.outputs["proper_time"]


def test_ftl_effective_2c_has_no_gamma() -> None:
    d = 1 * u.pc
    r = hypothetical_ftl_effective(d, 2 * C)
    assert yr(r.outputs["effective_coordinate_time"]) == pytest.approx(yr(d / (2 * C)), rel=1e-12)
    assert r.status == "speculative"
    flat = repr(r.to_dict()).lower()
    assert "lorentz" not in str(list(r.outputs)).lower() and "gamma" not in flat
    assert r.outputs["proper_time"] == "not defined by this model"


def test_ftl_effective_sgr_a_10c() -> None:
    r = hypothetical_ftl_effective(SGR_A, 10 * C)
    assert yr(r.outputs["effective_coordinate_time"]) == pytest.approx(2_649, abs=0.5)


@pytest.mark.parametrize("beta", [0.5, 1.0])
def test_ftl_refuses_v_at_or_below_c(beta: float) -> None:
    with pytest.raises(ModelDomainError):
        hypothetical_ftl_effective(SGR_A, beta * C)


def test_classical_is_not_labelled_relativistic() -> None:
    r = classical_constant_speed(PROXIMA, 0.5 * C)
    assert r.model_id == "classical_constant_speed"
    assert any("Newtonian" in a for a in r.assumptions)
    assert any("relativistic effects" in w for w in r.warnings)
    assert "proper_time" not in r.outputs and "lorentz_factor" not in r.outputs


def test_bare_floats_are_rejected() -> None:
    with pytest.raises(TypeError):
        sr_inertial(8122.0, 0.5 * C)  # type: ignore[arg-type]


def test_every_result_names_its_model_and_assumptions() -> None:
    results = [
        classical_constant_speed(PROXIMA, 1000 * u.km / u.s),
        sr_inertial(PROXIMA, 0.5 * C),
        sr_constant_proper_accel(PROXIMA, 1 * G),
        null_propagation(PROXIMA),
        hypothetical_ftl_effective(PROXIMA, 3 * C),
    ]
    for r in results:
        d = r.to_dict()
        assert d["model_id"] and d["model_version"] and d["assumptions"]
        assert any("flat" in a for a in d["assumptions"])
        assert any("static endpoints" in a for a in d["assumptions"])
