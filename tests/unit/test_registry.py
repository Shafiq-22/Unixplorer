from __future__ import annotations

import yaml

from ingestion.datasets import DATASETS
from ingestion.paths import Layout

ALLOWED_LANDMARK_KEYS = {"key", "label", "simbad_id", "kind", "distance_sources"}


def test_every_fetchable_dataset_has_a_committed_query(repo_layout: Layout) -> None:
    for ds in DATASETS.values():
        if ds.fetch is not None:
            assert (repo_layout.queries / ds.query_file).is_file(), ds.id


def test_landmarks_hold_identifiers_only(repo_layout: Layout) -> None:
    """CLAUDE.md §8.1: landmarks.yaml lists names and identifiers; values are fetched."""
    spec = yaml.safe_load(repo_layout.landmarks.read_text())
    for lm in spec["landmarks"]:
        assert set(lm) <= ALLOWED_LANDMARK_KEYS, lm
        assert all(not isinstance(v, int | float) for v in lm.values()), lm


def test_gaia_query_is_bounded(repo_layout: Layout) -> None:
    adql = (repo_layout.queries / "gaia_dr3_nearby.adql").read_text()
    assert "WHERE parallax > 10 AND parallax_over_error > 10" in adql
    assert "{source_id_range}" in adql


def test_source_id_chunks_are_disjoint_and_exhaustive() -> None:
    from ingestion.datasets import GAIA_SOURCE_ID_SPAN, source_id_ranges

    conds = source_id_ranges("source_id", chunks=4)

    def chunk_of(sid: int) -> list[int]:
        return [
            k
            for k, c in enumerate(conds)
            if eval(c.replace("source_id", str(sid)).replace(" AND ", " and "))
        ]

    for sid in (
        0,
        1,
        GAIA_SOURCE_ID_SPAN // 4 - 1,
        GAIA_SOURCE_ID_SPAN // 4,
        GAIA_SOURCE_ID_SPAN - 1,
        GAIA_SOURCE_ID_SPAN,
        2**63 - 1,
        -1,
    ):
        assert len(chunk_of(sid)) == 1, sid
    assert "source_id <" not in conds[-1] and "source_id >=" not in conds[0]


def test_column_lookup_ignores_case() -> None:
    from ingestion.datasets import column_ci

    assert column_ci(["SOURCE_ID", "ra"], "source_id") == "SOURCE_ID"
