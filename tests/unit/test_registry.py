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
