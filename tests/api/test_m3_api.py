"""M3 API: Solar System at the snapshot epoch and routes from Earth (needs TEST_DATABASE_URL)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingestion.connectors import horizons

pytestmark = pytest.mark.db
REPO = Path(__file__).resolve().parents[2]


def test_solar_system_epoch_and_provenance_come_from_horizons(client: TestClient) -> None:
    ss = client.get("/solar-system").json()
    raw = json.loads((REPO / "data/raw/horizons/horizons_bodies/2026-10-12/mars.json").read_text())
    header = horizons.header_fields(raw)
    assert header["start_time"] is not None
    assert header["start_time"] in ss["epoch"]  # shown verbatim
    names = [b["object"]["display_name"] for b in ss["bodies"]]
    assert names[0] == "Sun" and {"Earth", "Moon", "Mars", "Pluto"} <= set(names)
    mars = next(b for b in ss["bodies"] if b["object"]["display_name"] == "Mars")
    assert f"target: {header['target_ephemeris']}" in mars["position"]["position_method"]
    assert mars["distance_from_sun"]["state"] == "derived"
    dists = [b["distance_from_sun"]["value_au"] for b in ss["bodies"][1:]]
    assert dists == sorted(dists)


def test_route_from_earth_reports_au(client: TestClient) -> None:
    def first(q: str) -> int:
        return int(client.get("/objects/search", params={"q": q}).json()["results"][0]["id"])

    earth, mars, prox = first("earth"), first("mars"), first("proxima")
    to_mars = client.post(
        "/routes", json={"origin_id": earth, "destination_id": mars, "speed_fraction_c": 0.5}
    ).json()
    d = to_mars["distance"]
    # Fixed endpoints (state vectors): no distance range.
    assert d["lower_au"] == d["value_au"] == d["upper_au"]
    assert d["value_au"] == pytest.approx(d["value_pc"] * 648000 / 3.141592653589793, rel=1e-12)
    to_prox = client.post(
        "/routes", json={"origin_id": earth, "destination_id": prox, "speed_fraction_c": 0.5}
    ).json()
    assert to_prox["origin"]["object"]["display_name"] == "Earth"
    assert to_prox["distance"]["lower_pc"] < to_prox["distance"]["upper_pc"]
