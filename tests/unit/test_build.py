from __future__ import annotations

import math

import pyarrow.parquet as pq

from ingestion import manifest
from ingestion.paths import Layout
from ingestion.pipeline.build import build_all, horizons_to_arrow
from tests.fixtures.synthetic import write_horizons, write_votable


def _snapshot(layout: Layout) -> None:
    path = write_votable(layout.raw / "test" / "ds" / "2026-01-01" / "result.vot")
    manifest.append(
        layout,
        manifest.Entry(
            dataset="ds",
            source="synthetic",
            service_url="https://example.invalid",
            release="r",
            query_file="data/queries/x.adql",
            retrieved_at="2026-01-01T00:00:00Z",
            files=[manifest.record_file(layout, path)],
        ),
    )


def test_build_is_byte_identical(tmp_layout: Layout) -> None:
    _snapshot(tmp_layout)
    build_all(tmp_layout)
    first = (tmp_layout.processed / "ds.parquet").read_bytes()
    (tmp_layout.processed / "ds.parquet").unlink()
    build_all(tmp_layout)
    assert (tmp_layout.processed / "ds.parquet").read_bytes() == first


def test_build_nulls_units_and_provenance(tmp_layout: Layout) -> None:
    _snapshot(tmp_layout)
    build_all(tmp_layout)
    table = pq.read_table(tmp_layout.processed / "ds.parquet")
    rows = table.to_pylist()
    # NaN and masked values become null, never 0 or NaN.
    assert rows[1]["parallax"] is None and rows[1]["phot_g_mean_mag"] is None
    # Original value and unit kept; SI companion added.
    assert rows[0]["parallax"] == 50.0
    assert table.schema.field("parallax").metadata[b"unit"] == b"mas"
    assert math.isclose(rows[0]["ra__si"], math.radians(10.0), rel_tol=1e-12)
    # No SI companion for magnitudes or epochs.
    assert "phot_g_mean_mag__si" not in table.column_names
    assert "ref_epoch__si" not in table.column_names
    assert rows[2]["source_record_id"] == "data/raw/test/ds/2026-01-01/result.vot#row=2"
    # Names are lower-cased; the raw name is kept.
    assert rows[0]["source_id"] == 1
    assert table.schema.field("source_id").metadata[b"original_name"] == b"SOURCE_ID"


def test_horizons_vectors(tmp_layout: Layout) -> None:
    path = write_horizons(tmp_layout.raw / "horizons" / "horizons_bodies" / "2026-01-01")
    row = horizons_to_arrow(path).to_pylist()[0]
    assert row["target"] == "Testbody"
    assert row["X"] == 1000.0 and row["X__si"] == 1_000_000.0
    assert row["VZ__si"] == 3000.0
    assert row["JDTDB"] == 2457389.0 and "JDTDB__si" not in row
