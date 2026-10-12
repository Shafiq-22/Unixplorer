"""M2 API against the loaded snapshot (needs TEST_DATABASE_URL)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from atlas_db.models import VALUE_STATES

pytestmark = pytest.mark.db


def _first(client: TestClient, q: str) -> dict:
    results = client.get("/objects/search", params={"q": q}).json()["results"]
    assert results, q
    return results[0]


@pytest.mark.parametrize(
    ("q", "name"),
    [
        ("proxima", "Proxima Centauri"),
        ("Barnard", "Barnard's star"),
        ("sun", "Sun"),
        ("pleiades", "Pleiades"),
    ],
)
def test_search_finds_common_names_first(client: TestClient, q: str, name: str) -> None:
    assert _first(client, q)["display_name"] == name


def test_dossier_every_value_has_unit_state_and_source(client: TestClient) -> None:
    d = client.get(f"/objects/{_first(client, 'proxima')['id']}").json()
    assert d["measurements"]
    for m in d["measurements"]:
        assert isinstance(m["unit"], str)
        assert m["state"] in VALUE_STATES
        assert m["method"]
        path, _, row = m["source"]["source_record_id"].partition("#row=")
        assert path.startswith("data/raw/") and row.isdigit()
        assert m["source"]["release"] and m["source"]["retrieved_at"]
    [pos] = d["positions"]
    assert pos["distance"]["method"] == "bailer_jones_2021_geometric"
    assert pos["cartesian"]["state"] == "derived"
    assert {c["display_name"] for c in d["children"]} >= {"Proxima Cen b"}


def test_sky_only_object_has_no_3d_position_and_no_route(client: TestClient) -> None:
    sgr = _first(client, "sgr a")
    assert sgr["has_3d_position"] is False
    d = client.get(f"/objects/{sgr['id']}").json()
    assert all(p["distance"] is None and p["cartesian"] is None for p in d["positions"])
    sun = _first(client, "sun")["id"]
    r = client.post(
        "/routes", json={"origin_id": sun, "destination_id": sgr["id"], "speed_fraction_c": 0.5}
    )
    assert r.status_code == 422 and "sky view only" in r.json()["detail"]


def test_tiles_lod_and_partition(client: TestClient) -> None:
    root = client.get("/stars/tiles/0/0/0/0", params={"limit": 500}).json()
    mags = [s["phot_g_mean_mag"] for s in root["stars"] if s["phot_g_mean_mag"] is not None]
    assert len(root["stars"]) == 500 and not root["complete"]
    assert mags == sorted(mags)  # brightest first
    totals = sum(
        client.get(f"/stars/tiles/1/{i}/{j}/{k}", params={"limit": 1}).json()["total_in_cell"]
        for i in (0, 1)
        for j in (0, 1)
        for k in (0, 1)
    )
    # Level-1 cells partition the root cube; a star exactly on a shared face is counted twice.
    assert root["total_in_cell"] <= totals <= root["total_in_cell"] + 10
    assert client.get("/stars/tiles/7/0/0/0").status_code == 422
    assert client.get("/stars/tiles/1/2/0/0").status_code == 422


def test_route_sun_to_proxima(client: TestClient) -> None:
    sun, prox = _first(client, "sun")["id"], _first(client, "proxima")["id"]
    r = client.post(
        "/routes",
        json={
            "origin_id": sun,
            "destination_id": prox,
            "speed_fraction_c": 0.5,
            "proper_acceleration_g": 1.0,
            "ftl_speed_fraction_c": 10.0,
        },
    )
    assert r.status_code == 201
    route = r.json()
    d = route["distance"]
    assert d["lower_pc"] <= d["value_pc"] <= d["upper_pc"]
    assert [m["model_id"] for m in route["models"]] == [
        "classical_constant_speed",
        "sr_inertial",
        "sr_constant_proper_accel",
        "null_propagation",
        "hypothetical_ftl_effective",
    ]
    assert route["frame"]["galactocentric_defaults"] == "v4.0"
    assert client.get(f"/routes/{route['id']}").json() == route  # persisted, reproducible
    traj = client.get(
        f"/routes/{route['id']}/trajectory",
        params={"model_id": "sr_constant_proper_accel", "samples": 50},
    ).json()
    fr = [s["fraction"] for s in traj["samples"]]
    assert fr[0] == 0 and fr[-1] == pytest.approx(1.0, rel=1e-9)
    assert all(b >= a for a, b in zip(fr, fr[1:], strict=False))


def test_traversal_pause_resume_cancel(client: TestClient) -> None:
    sun, prox = _first(client, "sun")["id"], _first(client, "proxima")["id"]
    route = client.post(
        "/routes", json={"origin_id": sun, "destination_id": prox, "speed_fraction_c": 0.5}
    ).json()
    t = client.post("/traversals", json={"route_id": route["id"], "model_id": "sr_inertial"}).json()
    assert t["status"] == "running"
    steps = [("paused", 200), ("running", 200), ("cancelled", 200), ("running", 409)]
    for status, code in steps:
        assert client.patch(f"/traversals/{t['id']}", json={"status": status}).status_code == code
    refused = client.post(
        "/routes", json={"origin_id": sun, "destination_id": prox, "speed_fraction_c": 1.0}
    ).json()
    r = client.post("/traversals", json={"route_id": refused["id"], "model_id": "sr_inertial"})
    assert r.status_code == 422
