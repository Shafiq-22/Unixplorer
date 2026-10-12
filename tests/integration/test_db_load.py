"""`atlas db load` against a real Postgres (CLAUDE.md §8.4, §8.6).

Needs TEST_DATABASE_URL pointing at a disposable database: the schema is dropped and
recreated. Skipped when it is unset.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
import pyarrow.parquet as pq
import pytest
from astropy.io.votable import parse_single_table

from ingestion.datasets import column_ci
from ingestion.dbload import psycopg_url
from ingestion.paths import Layout

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set"),
]


@pytest.fixture(scope="module")
def loaded(loaded_db: dict[str, Any]) -> dict[str, Any]:
    return loaded_db


def _q(sql: str, *params: Any) -> list[tuple[Any, ...]]:
    assert URL
    with psycopg.connect(psycopg_url(URL)) as conn:
        return conn.execute(sql, params).fetchall()


def test_counts_match_snapshot(loaded: dict[str, Any], repo_layout: Layout) -> None:
    n_gaia = pq.read_metadata(repo_layout.processed / "gaia_dr3_nearby.parquet").num_rows
    assert (
        _q("SELECT count(*) FROM external_identifier WHERE catalogue = 'gaia_dr3'")[0][0] == n_gaia
    )
    assert (
        _q(
            "SELECT count(*) FROM position_solution ps JOIN external_identifier e "
            "ON e.object_id = ps.object_id AND e.catalogue = 'gaia_dr3'"
        )[0][0]
        == n_gaia
    )


def test_second_load_adds_nothing(loaded: dict[str, Any]) -> None:
    for ds, s in loaded["second"]["stats"].items():
        for key in (
            "objects",
            "identifiers",
            "aliases",
            "classifications",
            "measurements",
            "positions",
        ):
            assert s.get(key, 0) == 0, (ds, key)


def test_every_value_row_is_manifest_traceable(loaded: dict[str, Any]) -> None:
    for table in (
        "measurement",
        "position_solution",
        "external_identifier",
        "object_alias",
        "classification",
    ):
        bad = _q(f"""SELECT count(*) FROM {table} t JOIN source_file f ON f.id = t.source_file_id
                     WHERE t.source_record_id <> f.path || '#row=' || t.source_row
                        OR t.source_row < 0 OR t.source_row >= f.rows""")[0][0]
        assert bad == 0, table


def test_no_nan_and_unknown_means_null(loaded: dict[str, Any]) -> None:
    assert _q("SELECT count(*) FROM measurement WHERE value = 'NaN'::float8")[0][0] == 0
    assert (
        _q("SELECT count(*) FROM measurement WHERE value IS NULL AND state <> 'unknown'")[0][0] == 0
    )


@pytest.mark.parametrize("name", ["NAME Proxima Centauri", "NAME Barnard's star"])
def test_spot_check_db_parallax_equals_raw(
    loaded: dict[str, Any], repo_layout: Layout, name: str
) -> None:
    rows = _q(
        """SELECT m.value, m.source_record_id FROM object_alias a
           JOIN measurement m ON m.object_id = a.object_id AND m.quantity = 'parallax'
           WHERE a.alias = %s""",
        name,
    )
    assert len(rows) == 1
    value, rid = rows[0]
    path, _, idx = rid.partition("#row=")
    raw = parse_single_table(str(repo_layout.root / path)).array
    assert value == float(raw[column_ci(list(raw.dtype.names), "parallax")][int(idx)])  # exact


def test_landmarks_are_sky_only_until_literature_distances(loaded: dict[str, Any]) -> None:
    rows = _q("""SELECT o.primary_name, p.distance_pc, p.distance_state FROM celestial_object o
                 JOIN external_identifier e ON e.object_id = o.id AND e.catalogue = 'atlas_landmark'
                 JOIN position_solution p ON p.object_id = o.id""")
    assert len(rows) == 10
    assert all(d is None and s == "unknown" for _, d, s in rows)


def test_crossmatch_is_reversible(loaded: dict[str, Any]) -> None:
    [(event_id, n)] = _q("""SELECT e.id, count(a.id) FROM provenance_event e
                            JOIN object_alias a ON a.provenance_event_id = e.id
                            WHERE e.event_type = 'crossmatch' GROUP BY e.id""")
    assert n > 0
    unattributed = _q(
        "SELECT count(*) FROM external_identifier WHERE catalogue = 'simbad_oid' "
        "AND provenance_event_id IS NULL AND object_id IN (SELECT object_id FROM "
        "external_identifier WHERE catalogue = 'gaia_dr3')"
    )[0][0]
    assert unattributed == 0


def test_alternative_exoplanet_solutions_kept(loaded: dict[str, Any]) -> None:
    [(n_rows, n_default)] = _q("""SELECT count(*), count(*) FILTER (WHERE is_default)
                                  FROM measurement WHERE quantity = 'pl_orbper'""")
    assert n_rows > n_default > 0
