"""CLAUDE.md §8.6 checks against the committed snapshot in data/."""

from __future__ import annotations

import pyarrow.parquet as pq
import pytest
from astropy.io.votable import parse_single_table

from ingestion import manifest
from ingestion.datasets import column_ci, normalize_id
from ingestion.paths import Layout
from ingestion.verify import verify


def test_manifest_verifies(repo_layout: Layout) -> None:
    checks, unlisted = verify(repo_layout)
    assert [c for c in checks if not c.ok] == []
    assert unlisted == []


@pytest.mark.snapshot
# Exact SIMBAD NAME aliases. A substring match is too loose ("Barnard" also hits the
# unrelated "Barnard  13A" alias of HD 4732).
@pytest.mark.parametrize("name", ["NAME Proxima Centauri", "NAME Barnard's star"])
def test_spot_check_parallax_matches_raw(repo_layout: Layout, name: str) -> None:
    entries = manifest.load(repo_layout)
    gaia = manifest.latest_complete(entries, "gaia_dr3_nearby")
    simbad = repo_layout.processed / "simbad_ids.parquet"
    gaia_pq = repo_layout.processed / "gaia_dr3_nearby.parquet"
    if gaia is None or not simbad.exists() or not gaia_pq.exists():
        pytest.skip("gaia_dr3_nearby / simbad_ids not downloaded and built yet")

    ids = pq.read_table(simbad, columns=["query_id", "alias"]).to_pylist()
    hits = {r["query_id"] for r in ids if normalize_id(r["alias"] or "") == normalize_id(name)}
    assert len(hits) == 1, f"expected one Gaia source aliased {name!r}, got {hits}"
    source_id = int(hits.pop().removeprefix("Gaia DR3 "))

    row = next(r for r in pq.read_table(gaia_pq).to_pylist() if r["source_id"] == source_id)
    path, _, idx = row["source_record_id"].partition("#row=")
    raw = parse_single_table(str(repo_layout.root / path)).array
    names = list(raw.dtype.names)
    assert int(raw[column_ci(names, "source_id")][int(idx)]) == source_id
    # exact, no tolerance
    assert row["parallax"] == float(raw[column_ci(names, "parallax")][int(idx)])
