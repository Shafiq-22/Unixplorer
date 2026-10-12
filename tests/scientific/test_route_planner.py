"""Route geometry and side-by-side planning (CLAUDE.md §9, §10)."""

from __future__ import annotations

import astropy.units as u
import numpy as np
import pytest

from astronomy_core.constants import JULIAN_YEAR
from astronomy_core.relativity import sr_constant_proper_accel
from route_planner.geometry import Endpoint, _segment_distance, route_distance
from route_planner.plan import MODEL_IDS, TravelParameters, plan, trajectory

RNG = np.random.default_rng(20261012)  # fixed seed: deterministic test geometry


def _brute(p0: np.ndarray, p1: np.ndarray, q0: np.ndarray, q1: np.ndarray, n: int = 401) -> float:
    s = np.linspace(0, 1, n)[:, None]
    a = p0 + (p1 - p0) * s
    b = q0 + (q1 - q0) * s
    return float(np.min(np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)))


@pytest.mark.parametrize("trial", range(40))
def test_segment_distance_matches_brute_force(trial: int) -> None:
    p0, p1, q0, q1 = (RNG.normal(size=3) * 10 for _ in range(4))
    exact = _segment_distance(p0, p1, q0, q1)
    brute = _brute(p0, p1, q0, q1)
    # Brute force samples a 401x401 grid, so it can only overestimate the true minimum,
    # by at most about one grid step times the segment lengths.
    step = (np.linalg.norm(p1 - p0) + np.linalg.norm(q1 - q0)) / 400
    assert exact <= brute + 1e-12
    assert brute - exact <= step


def test_fixed_endpoints_have_no_range() -> None:
    a = Endpoint.fixed("A", np.array([1.0, 2.0, 3.0]) * u.pc, "test")
    b = Endpoint.fixed("B", np.array([4.0, 6.0, 3.0]) * u.pc, "test")
    d = route_distance(a, b)
    assert d.value.to_value(u.pc) == pytest.approx(5.0, rel=1e-12)
    assert d.lower == d.value and d.upper == d.value


def test_from_origin_range_is_the_distance_interval() -> None:
    origin = Endpoint.fixed("origin", np.zeros(3) * u.pc, "test")
    star = Endpoint.along_sight_line(
        "star", np.array([0.0, 3.0, 4.0]) * u.pc, 4.9 * u.pc, 5.2 * u.pc, "test"
    )
    d = route_distance(origin, star)
    assert d.value.to_value(u.pc) == pytest.approx(5.0, rel=1e-12)
    assert d.lower.to_value(u.pc) == pytest.approx(4.9, rel=1e-12)
    assert d.upper.to_value(u.pc) == pytest.approx(5.2, rel=1e-12)


def test_plan_runs_every_model_side_by_side() -> None:
    d = route_distance(
        Endpoint.fixed("Sun", np.zeros(3) * u.pc, "test"),
        Endpoint.along_sight_line("P", np.array([1.3, 0, 0]) * u.pc, 1.29 * u.pc, 1.31 * u.pc, "t"),
    )
    entries = plan(d, TravelParameters(0.5, 1.0, 10.0))
    assert [e["model_id"] for e in entries] == list(MODEL_IDS)
    assert not any("refused" in e for e in entries)
    accel = next(e for e in entries if e["model_id"] == "sr_constant_proper_accel")
    lo = accel["at_distance_lower"]["proper_time"]["value"]
    hi = accel["at_distance_upper"]["proper_time"]["value"]
    assert lo < accel["outputs"]["proper_time"]["value"] < hi
    assert any("proper motions" in a for a in accel["assumptions"])


@pytest.mark.parametrize(
    ("speed", "ftl", "refused"),
    [
        (1.0, 10.0, {"sr_inertial"}),
        (2.0, 10.0, {"sr_inertial"}),
        (0.5, 1.0, {"hypothetical_ftl_effective"}),
        (0.5, 0.5, {"hypothetical_ftl_effective"}),
    ],
)
def test_out_of_domain_is_refused_not_clamped(speed: float, ftl: float, refused: set[str]) -> None:
    d = route_distance(
        Endpoint.fixed("A", np.zeros(3) * u.pc, "t"),
        Endpoint.fixed("B", np.array([1.0, 0, 0]) * u.pc, "t"),
    )
    entries = plan(d, TravelParameters(speed, 1.0, ftl))
    assert {e["model_id"] for e in entries if "refused" in e} == refused
    classical = next(e for e in entries if e["model_id"] == "classical_constant_speed")
    assert classical["inputs"]["speed"]["value"] == pytest.approx(speed * 299_792_458, rel=1e-12)


def test_accel_trajectory_matches_model_endpoints() -> None:
    dist = 1.3012 * u.pc
    params = TravelParameters(0.5, 1.0, 10.0)
    traj = trajectory("sr_constant_proper_accel", dist, params, 101)
    s = traj["samples"]
    total = sr_constant_proper_accel(dist, params.acceleration)
    assert s[0]["fraction"] == pytest.approx(0.0, abs=1e-12)
    assert s[-1]["fraction"] == pytest.approx(1.0, rel=1e-9)
    assert s[-1]["proper_time_yr"] == pytest.approx(
        total.outputs["proper_time"].to_value(JULIAN_YEAR), rel=1e-9
    )
    fractions = [x["fraction"] for x in s]
    assert all(b >= a for a, b in zip(fractions, fractions[1:], strict=False))
    assert max(x["speed_c"] for x in s) < 1.0


@pytest.mark.parametrize(
    "model_id", ["null_propagation", "hypothetical_ftl_effective", "classical_constant_speed"]
)
def test_models_without_proper_time_report_none(model_id: str) -> None:
    traj = trajectory(model_id, 1 * u.pc, TravelParameters(0.5, 1.0, 10.0), 5)
    assert traj["proper_time_defined"] is False
    assert all(x["proper_time_yr"] is None for x in traj["samples"])
    assert traj["samples"][-1]["fraction"] == pytest.approx(1.0, rel=1e-12)
